"""Jobs, candidates, applications and matching (the core recruiting service)."""
from __future__ import annotations

import json
import re

from .. import db
from ..adapters.embedder import get_embedder
from ..adapters.vectorstore import get_store
from ..core import matching, ml
from ..core.jdcheck import jd_check
from ..core.parsing import parse_cv, parse_jd

STAGES = ["Applied", "Screening", "Shortlisted", "Interview", "Selected", "Rejected"]


class NotFound(LookupError):
    pass


# ================================================================= jobs
def _job_row(j: dict) -> dict:
    sk = db.rows("SELECT skill, kind FROM job_skills WHERE job_id=? ORDER BY rowid", (j["id"],))
    j["must"] = [s["skill"] for s in sk if s["kind"] == "must"]
    j["nice"] = [s["skill"] for s in sk if s["kind"] == "nice"]
    j["short"] = re.split(r" / | – | - |\(", j["title"])[0].strip()
    c = db.rows("SELECT stage, COUNT(*) n FROM applications WHERE job_id=? GROUP BY stage", (j["id"],))
    j["stage_counts"] = {s: 0 for s in STAGES} | {r["stage"]: r["n"] for r in c}
    j["applicants"] = sum(j["stage_counts"].values())
    return j


def get_job(job_id: int) -> dict:
    j = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not j:
        raise NotFound(f"Job {job_id} not found")
    return _job_row(j)


def list_jobs(status: str | None = None, q: str | None = None) -> list[dict]:
    sql, p = "SELECT * FROM jobs WHERE 1=1", []
    if status:
        sql += " AND status=?"
        p.append(status)
    if q:
        sql += " AND (title LIKE ? OR location LIKE ?)"
        p += [f"%{q}%", f"%{q}%"]
    return [_job_row(j) for j in db.rows(sql + " ORDER BY id DESC", p)]


def find_job(text: str) -> dict | None:
    """Fuzzy find a job by words in its title or location."""
    t = text.lower()
    best, bs = None, 0
    for j in list_jobs():
        words = [w for w in re.findall(r"[a-z]+", j["title"].lower()) if len(w) > 2 and w not in ("and", "the")]
        s = sum(1 for w in words if re.search(rf"\b{w}", t))
        if j["location"] and j["location"].split(",")[0].lower() in t:
            s += 0.5
        if s > bs:
            best, bs = j, s
    return best if bs >= 1 else None


def _set_skills(job_id: int, must: list[str], nice: list[str]) -> None:
    db.run("DELETE FROM job_skills WHERE job_id=?", (job_id,))
    for s in dict.fromkeys(must):
        db.run("INSERT OR IGNORE INTO job_skills VALUES(?,?,?)", (job_id, s, "must"))
    for s in dict.fromkeys(nice):
        if s not in must:
            db.run("INSERT OR IGNORE INTO job_skills VALUES(?,?,?)", (job_id, s, "nice"))


def create_job(text: str, by: str, source: str = "Upload", file_name: str | None = None,
               title: str | None = None) -> dict:
    p = parse_jd(text, title)
    jid = db.run("INSERT INTO jobs(title,location,description,min_years,qualification,status,source,file_name,"
                 "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (p["title"], p["location"], p["description"], p["min_years"], p["qualification"], "Open",
                  source, file_name, db.now(), db.now()))
    _set_skills(jid, p["must"], p["nice"])
    index_job(jid)
    db.log("Job created", p["title"], by, job_id=jid, entity="job", entity_id=jid)
    return get_job(jid)


def update_job(job_id: int, by: str, **fields) -> dict:
    j = get_job(job_id)
    allowed = {k: v for k, v in fields.items()
               if k in ("title", "location", "min_years", "qualification", "status", "description") and v is not None}
    if allowed:
        sets = ", ".join(f"{k}=?" for k in allowed)
        db.run(f"UPDATE jobs SET {sets}, updated_at=? WHERE id=?", (*allowed.values(), db.now(), job_id))
    if fields.get("must") is not None or fields.get("nice") is not None:
        _set_skills(job_id, fields.get("must") if fields.get("must") is not None else j["must"],
                    fields.get("nice") if fields.get("nice") is not None else j["nice"])
    index_job(job_id)
    db.log("Job updated", ", ".join(k for k, v in fields.items() if v is not None), by, job_id=job_id,
           entity="job", entity_id=job_id)
    return get_job(job_id)


def delete_job(job_id: int, by: str) -> None:
    j = get_job(job_id)
    db.run("DELETE FROM jobs WHERE id=?", (job_id,))
    get_store().delete(f"job:{job_id}")
    db.log("Job deleted", j["title"], by)


def job_check(job_id: int) -> list[dict]:
    j = get_job(job_id)
    return jd_check(j["description"], j["must"], j["location"])


def index_job(job_id: int) -> None:
    j = get_job(job_id)
    get_store().upsert(f"job:{job_id}", f"{j['title']}\n{j['description']}",
                       {"type": "JD", "title": j["title"], "ref_id": job_id})


# ================================================================= candidates
def _cand_row(c: dict, full: bool = True) -> dict:
    c["roles"] = json.loads(c.pop("roles_json") or "[]")
    c["initials"] = "".join(w[0] for w in c["name"].split()[:2]).upper()
    if full:
        c["skills"] = db.rows("SELECT skill, status, evidence FROM candidate_skills WHERE candidate_id=? ORDER BY rowid",
                              (c["id"],))
        c["applications"] = db.rows(
            "SELECT a.id, a.job_id, a.stage, j.title job_title, m.score FROM applications a JOIN jobs j ON j.id=a.job_id "
            "LEFT JOIN match_results m ON m.application_id=a.id WHERE a.candidate_id=? ORDER BY a.id", (c["id"],))
        c["family"] = ml.job_family(c["cv_text"])[:2]
    return c


def get_candidate(cid: int) -> dict:
    c = db.one("SELECT * FROM candidates WHERE id=?", (cid,))
    if not c:
        raise NotFound(f"Candidate {cid} not found")
    return _cand_row(c)


def list_candidates(q: str | None = None, skill: str | None = None, city: str | None = None,
                    job_id: int | None = None, stage: str | None = None, min_years: float | None = None,
                    edu_level: str | None = None) -> list[dict]:
    sql, p = "SELECT DISTINCT c.* FROM candidates c LEFT JOIN applications a ON a.candidate_id=c.id WHERE 1=1", []
    if q:
        sql += " AND (c.name LIKE ? OR c.headline LIKE ? OR c.cv_text LIKE ?)"
        p += [f"%{q}%"] * 3
    if city:
        sql += " AND c.location LIKE ?"
        p.append(f"%{city}%")
    if job_id:
        sql += " AND a.job_id=?"
        p.append(job_id)
    if stage:
        sql += " AND a.stage=?"
        p.append(stage)
    if min_years is not None:
        sql += " AND c.years>=?"
        p.append(min_years)
    if edu_level:
        sql += " AND c.edu_level=?"
        p.append(edu_level)
    if skill:
        sql += " AND c.id IN (SELECT candidate_id FROM candidate_skills WHERE skill LIKE ?)"
        p.append(f"%{skill}%")
    return [_cand_row(c) for c in db.rows(sql + " ORDER BY c.id DESC", p)]


def find_candidate(text: str) -> dict | None:
    """Find a candidate whose first or full name appears in text."""
    t = text.lower()
    best = None
    for c in db.rows("SELECT id, name FROM candidates"):
        full = c["name"].lower()
        first = full.split()[0]
        if full in t:
            return get_candidate(c["id"])
        if re.search(rf"\b{re.escape(first)}\b", t) and best is None:
            best = c["id"]
    return get_candidate(best) if best else None


def find_duplicate(name: str, email: str = "") -> dict | None:
    if email:
        d = db.one("SELECT id, name FROM candidates WHERE lower(email)=lower(?)", (email,))
        if d:
            return d
    return db.one("SELECT id, name FROM candidates WHERE lower(name)=lower(?)", (name.strip(),))


def preview_cv(text: str) -> dict:
    p = parse_cv(text)
    dup = find_duplicate(p["name"], p["email"])
    return {**p, "duplicate": dup}


def create_candidate(text: str, by: str, source: str = "Upload", file_name: str | None = None,
                     job_id: int | None = None, allow_duplicate: bool = False) -> dict:
    p = parse_cv(text)
    dup = find_duplicate(p["name"], p["email"])
    if dup and not allow_duplicate:
        raise ValueError(f"Possible duplicate of {dup['name']} (id {dup['id']}).")
    cid = db.run("INSERT INTO candidates(name,email,phone,location,headline,summary,education,edu_level,years,"
                 "roles_json,cv_text,file_name,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (p["name"], p["email"], p["phone"], p["location"], p["headline"], p["summary"], p["education"],
                  p["edu_level"], p["years"], json.dumps(p["roles"]), p["cv_text"], file_name, source, db.now()))
    for s, v in p["skills"].items():
        db.run("INSERT OR IGNORE INTO candidate_skills VALUES(?,?,?,?)", (cid, s, v["status"], v["evidence"]))
    get_store().upsert(f"cand:{cid}", p["cv_text"], {"type": "CV", "title": p["name"], "ref_id": cid})
    db.log("Candidate added", f"{p['name']} ({source})", by, candidate_id=cid, entity="candidate", entity_id=cid)
    if source != "Portal":  # portal sign-ups make their own account with their own password
        from . import portal
        portal.ensure_account(cid)
    if job_id:
        apply(job_id, cid, by)
    return get_candidate(cid)


def delete_candidate(cid: int, by: str) -> None:
    c = get_candidate(cid)
    db.run("DELETE FROM candidates WHERE id=?", (cid,))
    get_store().delete(f"cand:{cid}")
    db.log("Candidate deleted", c["name"], by)


# ================================================================= applications
def get_app(app_id: int) -> dict:
    a = db.one("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise NotFound(f"Application {app_id} not found")
    return a


def app_for(job_id: int, cid: int) -> dict | None:
    return db.one("SELECT * FROM applications WHERE job_id=? AND candidate_id=?", (job_id, cid))


def apply(job_id: int, cid: int, by: str, stage: str = "Applied") -> dict:
    get_job(job_id)
    get_candidate(cid)
    a = app_for(job_id, cid)
    if a:
        return a
    aid = db.run("INSERT INTO applications(job_id,candidate_id,stage,created_at,updated_at) VALUES(?,?,?,?,?)",
                 (job_id, cid, stage, db.now(), db.now()))
    compute_job(job_id)
    db.log("Added to job", get_job(job_id)["title"], by, candidate_id=cid, job_id=job_id, entity="application",
           entity_id=aid)
    return get_app(aid)


def set_stage(app_id: int, stage: str, by: str) -> dict:
    if stage not in STAGES:
        raise ValueError(f"Stage must be one of {', '.join(STAGES)}")
    a = get_app(app_id)
    if a["stage"] == stage:
        return a
    db.run("UPDATE applications SET stage=?, updated_at=? WHERE id=?", (stage, db.now(), app_id))
    db.log("Stage changed", f"{a['stage']} → {stage}", by, candidate_id=a["candidate_id"], job_id=a["job_id"],
           entity="application", entity_id=app_id)
    return get_app(app_id)


def remove_app(app_id: int, by: str) -> None:
    a = get_app(app_id)
    db.run("DELETE FROM applications WHERE id=?", (app_id,))
    db.log("Removed from job", "", by, candidate_id=a["candidate_id"], job_id=a["job_id"])


# ================================================================= matching
def weights() -> dict:
    return db.get_setting("weights", matching.DEFAULT_WEIGHTS)


def _corpus() -> list[str]:
    return [r["description"] for r in db.rows("SELECT description FROM jobs")] + \
           [r["cv_text"] for r in db.rows("SELECT cv_text FROM candidates")]


def score_texts(job: dict, cands: list[dict]) -> list[dict]:
    """Score any list of candidate dicts (need id/name/cv_text/years) against a job dict."""
    if not cands:
        return []
    emb = get_embedder()
    sims = matching.text_similarities(job["description"], [c["cv_text"] for c in cands],
                                      _corpus() + [job["description"]], emb)
    w = weights()
    from . import criteria
    rules = criteria.list_for(job.get("id"), active_only=True)
    criteria.prefetch_ai(rules, cands)
    out = []
    for c, s in zip(cands, sims):
        r = {"candidate_id": c.get("id"), "name": c["name"], "headline": c.get("headline", ""),
             "location": c.get("location", ""), **matching.score(job, c, s, w)}
        out.append(criteria.apply(job, c, r, rules))
    # people who meet every "must" rule first, then by score
    return sorted(out, key=lambda x: (not x["meets_criteria"], -x["score"]))


def compute_job(job_id: int, scope: str = "pool") -> list[dict]:
    """Rank candidates for a job. scope = pool (applied) | all | suggested (not applied)."""
    job = get_job(job_id)
    apps = {a["candidate_id"]: a for a in db.rows("SELECT * FROM applications WHERE job_id=?", (job_id,))}
    cands = db.rows("SELECT * FROM candidates")
    if scope == "pool":
        cands = [c for c in cands if c["id"] in apps]
    elif scope == "suggested":
        cands = [c for c in cands if c["id"] not in apps]
    res = score_texts(job, cands)
    old = {m["application_id"]: m for m in db.rows(
        "SELECT m.application_id, m.score, m.details_json FROM match_results m JOIN applications a "
        "ON a.id=m.application_id WHERE a.job_id=?", (job_id,))}
    writes = []
    for r in res:
        a = apps.get(r["candidate_id"])
        r["application_id"] = a["id"] if a else None
        r["stage"] = a["stage"] if a else None
        if a:
            details = json.dumps({k: r[k] for k in ("rows", "missing_must", "tips", "shortlist_chance", "criteria",
                                                    "criteria_failed", "criteria_adj")})
            o = old.get(a["id"])
            if not o or o["score"] != r["score"] or o["details_json"] != details:  # only save what changed
                writes.append((a["id"], r["score"], r["skill_score"], r["text_score"], r["exp_score"], details, db.now()))
    db.run_many("INSERT INTO match_results VALUES(?,?,?,?,?,?,?) ON CONFLICT(application_id) DO UPDATE SET "
                "score=excluded.score, skill_score=excluded.skill_score, text_score=excluded.text_score, "
                "exp_score=excluded.exp_score, details_json=excluded.details_json, computed_at=excluded.computed_at",
                writes)
    return res


def recompute_all() -> None:
    for j in db.rows("SELECT id FROM jobs"):
        compute_job(j["id"])


def match_one(job_id: int, cid: int) -> dict:
    job = get_job(job_id)
    c = db.one("SELECT * FROM candidates WHERE id=?", (cid,))
    if not c:
        raise NotFound("Candidate not found")
    r = score_texts(job, [c])[0]
    a = app_for(job_id, cid)
    r["application_id"] = a["id"] if a else None
    r["stage"] = a["stage"] if a else None
    return r


def similar_candidates(cid: int) -> list[dict]:
    cands = db.rows("SELECT id, name, headline, cv_text FROM candidates")
    sims = ml.similar(cands, cid)
    names = {c["id"]: c for c in cands}
    return [{"id": i, "name": names[i]["name"], "headline": names[i]["headline"], "similarity": s} for i, s in sims]


def compare(job_id: int, cids: list[int]) -> list[dict]:
    return [match_one(job_id, c) for c in cids[:3]]
