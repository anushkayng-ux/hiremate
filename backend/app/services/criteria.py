"""Recruiter screening criteria: extra rules for one job or for every job.

Why rules in the database (and not embeddings or a prompt):
- Shortlisting must be exact, repeatable and auditable. A rule stored as data gives the same result every time
  and shows *why* (the CV sentence) next to each candidate.
- Embeddings are good for "find similar text", not for "must be in NCR" or "+10 if Hindi".
- A prompt alone changes with the model and can't be audited.
So each rule is stored as structured data (kind + check + value + points), checked in code.
Only free-text rules ("prefer festive-season experience") use the AI, and the AI must quote the CV line
it used; without AI they fall back to a keyword check. Rules are also passed to the AI as context for
summaries, interview questions and chat answers.

Kinds:
- must    : candidate is flagged "doesn't meet" and listed after those who do. Never auto-rejected.
- bonus   : + points to the match score when met.
- penalty : - points when met.
Checks: skill, city, years, education, keyword, custom.
"""
from __future__ import annotations

import hashlib
import json
import re

from .. import db
from ..adapters import llm
from ..core.parsing import CITIES, cv_sentences
from ..core.skills import SKILLS, find_proof, skill_regex

KINDS = ("must", "bonus", "penalty")
CHECKS = ("skill", "city", "years", "education", "keyword", "custom")
EDU = ["Other", "Class 12", "Diploma", "Graduate", "Postgraduate"]
NCR = ["Delhi", "New Delhi", "Noida", "Greater Noida", "Gurugram", "Gurgaon", "Ghaziabad", "Faridabad"]
STOP = set("a an the and or of to in on for with at by from as is are be been was were candidates candidate people "
           "person someone who whose has have having had should must need needs prefer preferred preference give "
           "bonus extra plus points point pts only required mandatory avoid penalize penalise minus deduct any "
           "some their they them this that it its into over more than less least at very good strong".split())

SCHEMA = """
CREATE TABLE IF NOT EXISTS criteria(
  id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
  text TEXT NOT NULL, kind TEXT NOT NULL, check_type TEXT NOT NULL, value TEXT, points INTEGER DEFAULT 10,
  active INTEGER DEFAULT 1, created_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS criteria_checks(
  criterion_id INTEGER NOT NULL, cv_hash TEXT NOT NULL, status TEXT, evidence TEXT, by_ai INTEGER,
  PRIMARY KEY(criterion_id, cv_hash));
"""


def ensure_schema() -> None:
    db.conn().executescript(SCHEMA)


# ================================================================ parse plain English -> rule
def parse(text: str) -> dict:
    """'Must be in Delhi NCR' -> {kind: must, check: city, value: 'Delhi, ...'}. Recruiter can edit after."""
    raw = text.strip()
    t = raw.lower()
    if re.search(r"\b(avoid|penali[sz]e|minus|deduct|exclude|don'?t want|negative|red flag)\b", t):
        kind = "penalty"
    elif re.search(r"\b(must|only|required|requires?|mandatory|need(s)? to|has to|have to|should (be|have|know|speak|live)"
                   r"|at least|minimum|no less than)\b", t):
        kind = "must"
    else:
        kind = "bonus"
    pm = re.search(r"([+-]?\d{1,2})\s*(points|pts|marks|%)", t)
    points = abs(int(pm.group(1))) if pm else 10
    t2 = re.sub(r"[+-]?\d{1,2}\s*(points|pts|marks|%)", " ", t)

    q = re.search(r"[\"“']([^\"”']{2,60})[\"”']", raw)
    ym = re.search(r"(\d+(?:\.\d)?)\s*\+?\s*(?:years|yrs)", t2)
    city_hits = [c for c in CITIES if re.search(rf"\b{c.lower()}\b", t2)]
    if q:
        check, value = "keyword", q.group(1).strip()
    elif ym:
        op = "<" if re.search(r"less than|under|below|fewer|not more than|at most|max", t2) else ">="
        check, value = "years", f"{op}{float(ym.group(1)):g}"
    elif re.search(r"post ?graduate|\bmba\b|master", t2):
        check, value = "education", "Postgraduate"
    elif re.search(r"\bgraduate|\bdegree\b|bachelor|graduation", t2):
        check, value = "education", "Graduate"
    elif re.search(r"\bdiploma\b", t2):
        check, value = "education", "Diploma"
    elif re.search(r"class 12|12th|\bhsc\b", t2):
        check, value = "education", "Class 12"
    elif re.search(r"\bncr\b", t2) or city_hits:
        cities = list(dict.fromkeys((NCR if re.search(r"\bncr\b", t2) else []) + city_hits))
        check, value = "city", ", ".join(cities)
    else:
        sk = [k for k in SKILLS if skill_regex(k).search(t2)]
        if sk:
            check, value = "skill", sk[0]
        else:
            check, value = "custom", raw
    return {"kind": kind, "check_type": check, "value": value, "points": points}


def describe(c: dict) -> str:
    v = c["value"] or ""
    how = {"skill": f"CV proves the skill {v} (listed only = half)",
           "city": f"Lives in: {v}",
           "years": f"Total experience {'is under' if v.startswith('<') else 'is at least'} {v.lstrip('<>=')} years",
           "education": f"Education is {v} or higher",
           "keyword": f"CV mentions \"{v}\"",
           "custom": "AI reads the CV and quotes the line (keyword check without AI)"}[c["check_type"]]
    effect = {"must": "must have", "bonus": f"+{c['points']} points", "penalty": f"−{c['points']} points"}[c["kind"]]
    return f"{how} · {effect}"


# ================================================================ CRUD
def _row(r: dict) -> dict:
    r["scope"] = "All jobs" if r["job_id"] is None else "This job"
    r["how"] = describe(r)
    r["active"] = bool(r["active"])
    return r


def get(cid: int) -> dict:
    r = db.one("SELECT * FROM criteria WHERE id=?", (cid,))
    if not r:
        from .recruit import NotFound
        raise NotFound("Criterion not found")
    return _row(r)


def list_for(job_id: int | None, include_global: bool = True, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM criteria WHERE (job_id IS ?" + (" OR job_id IS NULL" if include_global and job_id else "") + ")"
    if active_only:
        sql += " AND active=1"
    return [_row(r) for r in db.rows(sql + " ORDER BY job_id IS NOT NULL, id", (job_id,))]


def list_all() -> list[dict]:
    rows = db.rows("SELECT c.*, j.title job_title FROM criteria c LEFT JOIN jobs j ON j.id=c.job_id ORDER BY c.job_id, c.id")
    return [_row(r) for r in rows]


def create(text: str, job_id: int | None, by: str, kind: str | None = None, check_type: str | None = None,
           value: str | None = None, points: int | None = None) -> dict:
    if not text.strip():
        raise ValueError("Write the criterion in a few words.")
    p = parse(text)
    # keep the rule name clean: "+10 points" lives in the points field
    text = re.sub(r"\s*\(?[+-]?\d{1,2}\s*(points|pts|marks|%)\)?", "", text).strip(" ,.") or text
    kind, check_type = kind or p["kind"], check_type or p["check_type"]
    if kind not in KINDS or check_type not in CHECKS:
        raise ValueError("Unknown rule type.")
    value = value if value not in (None, "") else (p["value"] if check_type == p["check_type"] else text.strip())
    _validate(check_type, value)
    cid = db.run("INSERT INTO criteria(job_id,text,kind,check_type,value,points,active,created_by,created_at) "
                 "VALUES(?,?,?,?,?,?,?,?,?)", (job_id, text.strip(), kind, check_type, value,
                                               int(points if points is not None else p["points"]), 1, by, db.now()))
    db.log("Criterion added", f"{text.strip()} ({'all jobs' if job_id is None else 'job'})", by, job_id=job_id,
           entity="criterion", entity_id=cid)
    _refresh(job_id)
    return get(cid)


def _validate(check: str, value: str) -> None:
    if check == "years" and not re.fullmatch(r"(<|>=)?\d+(\.\d+)?", value or ""):
        raise ValueError("Years must look like >=3 or <2.")
    if check == "education" and value not in EDU:
        raise ValueError(f"Education must be one of {', '.join(EDU)}.")


def update(cid: int, by: str, **f) -> dict:
    c = get(cid)
    f = {k: v for k, v in f.items() if v is not None and k in ("text", "kind", "check_type", "value", "points", "active")}
    if "active" in f:
        f["active"] = 1 if f["active"] else 0
    if f.get("kind", c["kind"]) not in KINDS or f.get("check_type", c["check_type"]) not in CHECKS:
        raise ValueError("Unknown rule type.")
    _validate(f.get("check_type", c["check_type"]), f.get("value", c["value"]))
    if f:
        db.run(f"UPDATE criteria SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), cid))
        db.run("DELETE FROM criteria_checks WHERE criterion_id=?", (cid,))
    db.log("Criterion edited", c["text"], by, job_id=c["job_id"], entity="criterion", entity_id=cid)
    _refresh(c["job_id"])
    return get(cid)


def delete(cid: int, by: str) -> dict:
    c = get(cid)
    db.run("DELETE FROM criteria WHERE id=?", (cid,))
    db.run("DELETE FROM criteria_checks WHERE criterion_id=?", (cid,))
    db.log("Criterion removed", c["text"], by, job_id=c["job_id"])
    _refresh(c["job_id"])
    return c


def _refresh(job_id: int | None) -> None:
    from . import recruit
    if job_id:
        recruit.compute_job(job_id)
    else:
        recruit.recompute_all()


# ================================================================ evaluate
def _h(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _skill_line(cv: str) -> str:
    return next((l.strip() for l in cv.splitlines() if re.match(r"^\s*(skills|key skills)\s*:", l, re.I)), "")


def _keyword_check(phrase: str, cand: dict) -> tuple[str, str]:
    words = [w for w in re.findall(r"[a-z0-9&]+", phrase.lower()) if w not in STOP and len(w) > 2]
    if not words:
        return "unclear", ""
    sents = cv_sentences(cand["cv_text"], cand.get("name", ""), "")
    best, bs = "", 0
    for s in sents:
        sl = s.lower()
        hit = sum(1 for w in words if re.search(rf"\b{re.escape(w[:max(4, len(w) - 2)])}", sl))
        if hit > bs:
            best, bs = s, hit
    need = 1 if len(words) <= 2 else (len(words) + 1) // 2
    return ("met", best) if bs >= need else ("not met", "")


def _check(c: dict, cand: dict) -> tuple[str, str, float]:
    """Returns (status, evidence, credit 0..1)."""
    t, v = c["check_type"], c["value"] or ""
    if t == "skill":
        sl = _skill_line(cand["cv_text"])
        p = find_proof(v, cv_sentences(cand["cv_text"], cand.get("name", ""), sl), sl)
        if not p:
            return "not met", "", 0.0
        return ("met", p[1], 1.0) if p[0] == "Proven" else ("partly", p[1] + " (skills list only)", 0.5)
    if t == "city":
        loc = (cand.get("location") or "").lower()
        ok = any(x.strip().lower() and x.strip().lower() in loc for x in v.split(","))
        return ("met" if ok else "not met", cand.get("location") or "Location not stated", 1.0 if ok else 0.0)
    if t == "years":
        n = float(v.lstrip("<>=") or 0)
        yrs = float(cand.get("years") or 0)
        ok = yrs < n if v.startswith("<") else yrs >= n
        return ("met" if ok else "not met", f"{yrs:g} years in CV", 1.0 if ok else 0.0)
    if t == "education":
        lvl = cand.get("edu_level") or "Other"
        ok = EDU.index(lvl if lvl in EDU else "Other") >= EDU.index(v)
        return ("met" if ok else "not met", cand.get("education") or lvl, 1.0 if ok else 0.0)
    if t == "keyword":
        m = next((s for s in cand["cv_text"].splitlines() if v.lower() in s.lower()), "")
        return ("met", m.strip(), 1.0) if m else ("not met", "", 0.0)
    # custom
    cached = db.one("SELECT status, evidence FROM criteria_checks WHERE criterion_id=? AND cv_hash=?",
                    (c["id"], _h(cand["cv_text"]))) if c.get("id") else None
    if cached:
        st = cached["status"]
    else:
        st, ev = _keyword_check(c["value"] or c["text"], cand)
        cached = {"status": st, "evidence": ev}
    return st, cached["evidence"] or "", {"met": 1.0, "partly": 0.5}.get(st, 0.0)


def prefetch_ai(rules: list[dict], cands: list[dict]) -> None:
    """For free-text rules, ask the AI once per rule for all uncached candidates. AI must quote the CV."""
    if not llm.get_llm():
        return
    for c in rules:
        if c["check_type"] != "custom" or not c.get("id"):
            continue
        todo = [x for x in cands if x.get("cv_text") and not db.one(
            "SELECT 1 FROM criteria_checks WHERE criterion_id=? AND cv_hash=?", (c["id"], _h(x["cv_text"])))]
        if not todo:
            continue
        cvs = "\n\n".join(f"### CANDIDATE {i}\n{x['cv_text'][:1800]}" for i, x in enumerate(todo))
        out = llm.generate_json(
            "A recruiter set this screening rule. For each candidate decide if their CV shows it.\n"
            f"RULE: {c['value'] or c['text']}\n\n"
            "Return a JSON array, one object per candidate: {\"n\": <candidate number>, \"status\": \"met\" | "
            "\"partly\" | \"not met\" | \"unclear\", \"evidence\": \"<exact sentence copied from that CV, or empty>\"}. "
            "Only say met/partly if you can copy a supporting sentence.\n\n" + cvs, max_tokens=1500)
        if not isinstance(out, list):
            continue
        for o in out:
            try:
                x = todo[int(o.get("n"))]
            except (TypeError, ValueError, IndexError):
                continue
            st = o.get("status") if o.get("status") in ("met", "partly", "not met", "unclear") else "unclear"
            ev = str(o.get("evidence") or "").strip()
            if st in ("met", "partly") and (not ev or ev[:40].lower() not in x["cv_text"].lower()):
                st, ev = "unclear", ""  # grounding check: quote must exist in the CV
            db.run("INSERT OR REPLACE INTO criteria_checks VALUES(?,?,?,?,1)", (c["id"], _h(x["cv_text"]), st, ev))


def apply(job: dict, cand: dict, res: dict, rules: list[dict]) -> dict:
    """Add criteria results to a match result: adjusts score, flags unmet must-haves."""
    out, adj, failed = [], 0.0, []
    for c in rules:
        st, ev, credit = _check(c, cand)
        pts = 0.0
        if c["kind"] == "bonus":
            pts = c["points"] * credit
        elif c["kind"] == "penalty":
            pts = -c["points"] * credit
        elif c["kind"] == "must" and credit < 1:
            failed.append(c["text"])
        adj += pts
        out.append({"id": c.get("id"), "text": c["text"], "kind": c["kind"], "check": c["check_type"],
                    "scope": c.get("scope", "This job"), "status": st, "evidence": ev, "points": round(pts)})
    res["base_score"] = res["score"]
    res["criteria_adj"] = round(adj)
    res["score"] = max(0, min(100, round(res["score"] + adj)))
    res["criteria"] = out
    res["criteria_failed"] = failed
    res["meets_criteria"] = not failed
    if failed:
        res["tips"] = [f"Doesn't meet: {failed[0]}"] + res.get("tips", [])
    return res


def brief(res: dict) -> str:
    if not res.get("criteria"):
        return ""
    return "Recruiter criteria: " + "; ".join(f"{c['text']} [{c['kind']}]: {c['status']}" for c in res["criteria"])


def guidelines() -> str:
    return db.get_setting("ai_guidelines", "") or ""


def snapshot() -> str:
    rows = list_all()
    if not rows:
        return "CRITERIA: none"
    return "CRITERIA:\n" + "\n".join(f"- {r['job_title'] or 'All jobs'}: {r['text']} ({r['how']})"
                                     + ("" if r["active"] else " [off]") for r in rows)


def explain_json() -> str:
    return json.dumps({"kinds": KINDS, "checks": CHECKS, "education": EDU})
