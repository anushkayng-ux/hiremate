"""HireMate Plus: matching and talent-pool insights.

 2  Success profile        24 Why not shortlisted?    37 Talent pool health
 5  Integrity check        25 JD reality check        38 Re-engage silver list
 9  Offer at risk          26 Hidden-gem finder       39 Skill demand board
17  Bring back runners-up  27 Career-path view        40 Duplicate and merge
36  Second opinion
All worked out in code from HireMate's own data. The AI only rewrites wording when a key is set.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date

from .. import db
from . import lc
from ..adapters import llm
from ..core import parsing
from ..services import recruit
from ..services.smart import _span, _ym
from . import insights

SENIOR = [("intern", 0), ("trainee", 0), ("associate", 1), ("assistant", 1), ("cashier", 1), ("executive", 2),
          ("senior", 3), ("lead", 3), ("supervisor", 4), ("in-charge", 4), ("deputy", 4), ("manager", 5), ("head", 6)]


def _level(title: str) -> int:
    t = (title or "").lower()
    return max([v for k, v in SENIOR if k in t] or [1])


def _numbers(cv: str) -> list[str]:
    """Achievement lines with numbers (%, ₹, 'x+', counts) – a sign of real results."""
    out = []
    for ln in (cv or "").splitlines():
        if re.search(r"\d+(\.\d+)?\s?%|₹\s?\d|\d+\+|\b\d{2,}\b\s+(customers|orders|bills|stores|people|associates|staff)", ln, re.I) \
                and not re.search(r"(email|phone|\b(19|20)\d{2}\b\s*[–-])", ln, re.I):
            out.append(ln.strip(" -•"))
    return out


# =========================================================== 27. career path
def career_path(cid: int) -> dict:
    c = recruit.get_candidate(cid)
    roles = []
    for r in c.get("roles") or []:
        s = _span(r.get("dates", ""))
        if s:
            roles.append({"role": r.get("role", ""), "org": r.get("org", ""), "start": s[0], "end": s[1],
                          "start_label": _ym(s[0]), "end_label": _ym(s[1]), "months": s[1] - s[0] + 1,
                          "level": _level(r.get("role", ""))})
    roles.sort(key=lambda x: x["start"])
    if not roles:
        return {"roles": [], "story": "No dated jobs in the CV, so the path can't be drawn.", "pattern": "unknown"}
    gaps = [(a["end"], b["start"]) for a, b in zip(roles, roles[1:]) if b["start"] - a["end"] - 1 >= 6]
    short = [r for r in roles[:-1] if r["months"] < 12]
    up = sum(1 for a, b in zip(roles, roles[1:]) if b["level"] > a["level"])
    avg = round(sum(r["months"] for r in roles) / len(roles))
    if up and not short:
        pattern, story = "growth", f"Steady growth: moved up {up} time{'s' if up > 1 else ''}, about {avg} months per job."
    elif len(short) >= 2:
        pattern, story = "hopping", f"{len(short)} jobs under a year. Ask why they moved."
    elif gaps:
        pattern, story = "gap", f"A gap of {gaps[0][1] - gaps[0][0] - 1} months. Ask what they did (never scored)."
    else:
        pattern, story = "stable", f"Stable: about {avg} months per job."
    return {"roles": roles, "story": story, "pattern": pattern, "promotions": up, "avg_months": avg}


# =========================================================== 2. success profile
def _good_hires(job_id: int) -> list[int]:
    """People HR hired, or rated 4+ on average in interview feedback, for this job."""
    out = set(r["candidate_id"] for r in db.rows("SELECT candidate_id FROM applications WHERE job_id=? AND stage='Selected'",
                                                 (job_id,)))
    for f in db.rows("SELECT a.candidate_id, f.scores_json FROM interview_feedback f JOIN applications a "
                     "ON a.id=f.application_id WHERE a.job_id=?", (job_id,)):
        s = list(json.loads(f["scores_json"] or "{}").values())
        if s and sum(s) / len(s) >= 4:
            out.add(f["candidate_id"])
    return list(out)


def _traits(job: dict, cid: int) -> dict:
    c = recruit.get_candidate(cid)
    m = recruit.match_one(job["id"], cid)
    cp = career_path(cid)
    cm = insights.commute(c.get("location"), job.get("location"))
    must = [r for r in m["rows"] if r.get("must")]
    return {
        "Proves the must-have skills": all(r["status"] == "Proven" for r in must) if must else True,
        "Shows results in numbers": len(_numbers(c["cv_text"])) >= 2,
        "Stays 1 year or more per job": cp.get("avg_months", 0) >= 12 if cp["roles"] else False,
        "Lives within 45 minutes": cm.get("level") == "ok",
        "Has the experience asked for": m["years"] >= m["min_years"],
    }


def success_profile(job_id: int, cid: int | None = None) -> dict:
    job = recruit.get_job(job_id)
    good = _good_hires(job_id)
    basis = "your past good hires for this job"
    if not good:  # no history yet: top quarter of current applicants
        ranked = recruit.compute_job(job_id)
        good = [r["candidate_id"] for r in ranked[:max(1, len(ranked) // 4)]]
        basis = "your top-ranked applicants (no hires yet for this job)"
    prof = Counter()
    for g in good:
        for k, v in _traits(job, g).items():
            prof[k] += v
    traits = [k for k, n in prof.items() if n >= max(1, len(good) / 2)]
    out = {"job": job["title"], "basis": basis, "examples": len(good), "traits": traits}
    if cid:
        mine = _traits(job, cid)
        out["candidate"] = {k: mine[k] for k in traits}
        out["matches"] = sum(mine[k] for k in traits)
        out["text"] = f"Matches {out['matches']} of {len(traits)} traits of {basis}."
    return out


# =========================================================== 5. integrity check
def integrity(cid: int) -> dict:
    c = recruit.get_candidate(cid)
    cv = c["cv_text"] or ""
    flags = []
    cp = career_path(cid)
    rs = cp["roles"]
    for a, b in zip(rs, rs[1:]):
        if b["start"] < a["end"] and a["end"] - b["start"] >= 2:
            flags.append(f"Two jobs overlap ({a['role']} and {b['role']}, {_ym(b['start'])} to {_ym(min(a['end'], b['end']))}). "
                         "Ask if one was part-time.")
    m = re.search(r"(\d{1,2})\+?\s*years", cv, re.I)
    if m and c.get("years") and int(m.group(1)) > c["years"] + 1.5:
        flags.append(f"Says {m.group(1)} years, but the dated jobs add up to {c['years']:g}.")
    for a, b in zip(rs, rs[1:]):
        if b["level"] - a["level"] >= 3 and a["months"] < 18:
            flags.append(f"Big jump from {a['role']} to {b['role']} in {a['months']} months. Check the title.")
    if re.search(r"\b(1[0-9]{2}|[2-9]\d{2})\s?%", cv):
        flags.append("A figure over 100% (e.g. accuracy). Check what it means.")
    today = date.today().year * 12 + date.today().month - 1
    if any(r["start"] > today for r in rs):
        flags.append("A job starts in the future.")
    from ..core import ml
    others = db.rows("SELECT id, name, cv_text FROM candidates WHERE id!=? AND anonymised_at IS NULL", (cid,))
    for oid, sim in ml.similar([{"id": cid, "cv_text": cv}] + others, cid, k=1) if len(others) >= 2 else []:
        if sim >= 0.9:
            o = next(x for x in others if x["id"] == oid)
            flags.append(f"Very similar text to {o['name']}'s CV ({round(sim * 100)}%). Possible copy or duplicate.")
    return {"flags": flags, "ok": not flags,
            "text": "Nothing looks inconsistent." if not flags else f"{len(flags)} thing{'s' if len(flags) > 1 else ''} to verify."}


# =========================================================== 24. why not shortlisted
def why_not(job_id: int, cid: int) -> dict:
    job = recruit.get_job(job_id)
    c = db.one("SELECT * FROM candidates WHERE id=?", (cid,))
    base = recruit.score_texts(job, [c])[0]
    reasons = []
    for r in base["rows"]:
        if r.get("must") and r["status"] == "Missing":
            reasons.append(f"No sign of {r['skill']} (must-have) in the CV.")
        elif r.get("must") and r["status"] == "Listed":
            reasons.append(f"{r['skill']} is only listed, with no work example (counts half).")
    if base["years"] < base["min_years"]:
        reasons.append(f"{base['years']:g} years; the job asks for {base['min_years']:g}+.")
    if base["text_score"] < 30:
        reasons.append("The CV's overall wording is far from the job description (different kind of work).")
    for x in base.get("criteria") or []:
        if x["status"] == "not met":
            reasons.append(f"Misses your rule: {x['text']}")
    # what single change moves the score most? re-score with that one thing fixed
    fixes = []
    for r in base["rows"]:
        if r.get("must") and r["status"] in ("Missing", "Listed"):
            alt = dict(c, cv_text=c["cv_text"] + f"\n- Used {lc(r['skill'])} every day at work.")
            fixes.append((recruit.score_texts(job, [alt])[0]["score"], f"Proof of {r['skill']}"))
    if base["years"] < base["min_years"]:
        fixes.append((recruit.score_texts(job, [dict(c, years=base["min_years"])])[0]["score"],
                      f"{base['min_years']:g} years of experience"))
    best = max(fixes, default=None)
    return {"score": base["score"], "reasons": reasons or ["Nothing major. They rank lower only because others score higher."],
            "best_fix": {"what": best[1], "new_score": best[0], "gain": best[0] - base["score"]} if best else None}


# =========================================================== 26. hidden gems
GEM_WORDS = r"award|best (cashier|employee|store)|employee of the month|top performer|promoted|recogni[sz]ed|star"


def hidden_gems(min_signals: int = 2) -> list[dict]:
    out = []
    for c in db.rows("SELECT id, name, cv_text, headline FROM candidates WHERE anonymised_at IS NULL"):
        nums = _numbers(c["cv_text"])
        awards = re.findall(GEM_WORDS, c["cv_text"] or "", re.I)
        cp = career_path(c["id"])
        signals = []
        if len(nums) >= 2:
            signals.append(f"{len(nums)} results with numbers, e.g. \"{nums[0][:80]}\"")
        if awards:
            signals.append("Mentions an award or recognition")
        if cp.get("promotions"):
            signals.append(f"Promoted {cp['promotions']} time{'s' if cp['promotions'] > 1 else ''}")
        if cp.get("avg_months", 0) >= 24:
            signals.append(f"Stays long: about {cp['avg_months']} months per job")
        apps = db.rows("SELECT a.job_id, j.title, m.score FROM applications a JOIN jobs j ON j.id=a.job_id "
                       "LEFT JOIN match_results m ON m.application_id=a.id WHERE a.candidate_id=?", (c["id"],))
        low = [a for a in apps if a["score"] is not None and a["score"] < 65]
        if len(signals) >= min_signals and low:
            out.append({"candidate_id": c["id"], "name": c["name"], "headline": c["headline"], "signals": signals,
                        "job_id": low[0]["job_id"], "job": low[0]["title"], "score": low[0]["score"]})
    return sorted(out, key=lambda x: (-len(x["signals"]), x["score"]))


# =========================================================== 25. JD reality check
def jd_reality(job_id: int) -> dict:
    job = recruit.get_job(job_id)
    cands = db.rows("SELECT * FROM candidates WHERE anonymised_at IS NULL")
    n = len(cands) or 1
    res = recruit.score_texts(job, cands)
    items = []
    for s in job["must"]:
        proven = sum(1 for r in res for x in r["rows"] if x["skill"] == s and x["status"] == "Proven")
        listed = sum(1 for r in res for x in r["rows"] if x["skill"] == s and x["status"] == "Listed")
        pct = round(proven / n * 100)
        items.append({"skill": s, "proven": proven, "listed": listed, "pct": pct,
                      "level": "rare" if pct < 25 else "ok" if pct < 60 else "common"})
    yrs = sum(1 for c in cands if (c["years"] or 0) >= (job["min_years"] or 0))
    advice = [f"Only {i['proven']} of {n} people prove {i['skill']}. Make it nice-to-have, or expect a longer search."
              for i in items if i["level"] == "rare"]
    if job["min_years"] and yrs / n < 0.3:
        advice.append(f"Only {yrs} of {n} people have {job['min_years']:g}+ years. Consider {max(0, job['min_years'] - 2):g}+.")
    return {"job": job["title"], "pool": n, "skills": items, "meet_years": yrs, "advice": advice or ["The JD fits the talent pool well."]}


# =========================================================== 17 + 38. runners-up and silver list
def runners_up(job_id: int) -> list[dict]:
    """People not in this job who were not selected elsewhere (or are just in the pool) and score 60%+ here."""
    job = recruit.get_job(job_id)
    out = []
    for r in recruit.compute_job(job_id, scope="suggested"):
        past = db.rows("SELECT j.title, a.stage FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.candidate_id=?",
                       (r["candidate_id"],))
        if r["score"] >= 60:
            why = ("Not selected for " + past[0]["title"] if any(p["stage"] == "Rejected" for p in past)
                   else f"In {past[0]['title']} ({past[0]['stage']})" if past else "In the talent pool")
            out.append({"candidate_id": r["candidate_id"], "name": r["name"], "score": r["score"], "why": why,
                        "job": job["title"]})
    seen, uniq = set(), []
    for o in sorted(out, key=lambda x: -x["score"]):
        c = db.one("SELECT name, phone FROM candidates WHERE id=?", (o["candidate_id"],))
        key = _digits(c["phone"]) or c["name"].lower()
        if key not in seen:
            seen.add(key)
            uniq.append(o)
    return uniq


def invite_runners_up(job_id: int, cids: list[int], by: str) -> dict:
    from ..services import assist
    n = 0
    for cid in cids:
        recruit.apply(job_id, cid, by, source="Talent pool")
        assist.draft_email(job_id, cid, "followup", "English", by)
        n += 1
    return {"added": n, "text": f"Added {n} people and drafted a note for each. Check and press Send."}


def silver_list(k: int = 5) -> list[dict]:
    jobs = recruit.list_jobs(status="Open")
    best: dict[int, dict] = {}
    for j in jobs:
        for r in recruit.compute_job(j["id"], scope="all"):
            if r["stage"] in (None, "Rejected") and r["score"] >= 55:
                if r["candidate_id"] not in best or r["score"] > best[r["candidate_id"]]["score"]:
                    best[r["candidate_id"]] = {"candidate_id": r["candidate_id"], "name": r["name"], "score": r["score"],
                                               "job_id": j["id"], "job": j["title"]}
    seen, uniq = set(), []
    for o in sorted(best.values(), key=lambda x: -x["score"]):
        c = db.one("SELECT name, phone FROM candidates WHERE id=?", (o["candidate_id"],))
        key = _digits(c["phone"]) or c["name"].lower()
        if key not in seen:
            seen.add(key)
            uniq.append(o)
    out = uniq[:k]
    for o in out:
        fn = o["name"].split()[0]
        o["message"] = (f"Hi {fn}, this is the HR team. We have an opening for {o['job']} and your "
                        "profile fits it well. Would you like us to consider you? Just reply YES and we'll call you.")
    return out


# =========================================================== 9. offer at risk
def offer_at_risk() -> list[dict]:
    out = []
    for e in db.rows("SELECT e.id, e.body, e.created_at, a.id app_id, a.stage, c.name, c.id cid, j.title FROM emails e "
                     "JOIN applications a ON a.id=e.application_id JOIN candidates c ON c.id=a.candidate_id "
                     "JOIN jobs j ON j.id=a.job_id WHERE e.direction='in' AND a.stage IN "
                     "('Screening','Shortlisted','Interview','Selected') ORDER BY e.id DESC"):
        hit = [w for w in insights.HESITATION if w in (e["body"] or "").lower()]
        if hit:
            sent = re.split(r"(?<=[.!?])\s+", e["body"])
            quote = next((s for s in sent if hit[0] in s.lower()), e["body"][:120])
            out.append({"candidate_id": e["cid"], "name": e["name"], "job": e["title"], "stage": e["stage"],
                        "signal": hit[0], "quote": quote.strip(), "email_id": e["id"],
                        "action": "Call today. Ask what would help them say yes (date, pay, travel)."})
    seen, uniq = set(), []
    for o in out:
        if o["candidate_id"] not in seen:
            seen.add(o["candidate_id"])
            uniq.append(o)
    return uniq


# =========================================================== 36. second opinion
def second_opinion(job_id: int, cid: int) -> dict:
    m = recruit.match_one(job_id, cid)
    a = recruit.app_for(job_id, cid)
    stage = a["stage"] if a else None
    leaning_yes = stage in ("Shortlisted", "Interview", "Selected") or m["score"] >= 70
    pts = []
    if leaning_yes:
        side = "Reasons to slow down"
        pts += [f"Missing must-have: {s}" for s in m["missing_must"]]
        pts += [f"{r['skill']} is only listed, not shown with an example" for r in m["rows"] if r.get("must") and r["status"] == "Listed"]
        if a:
            r = insights.dropout_risk(a["id"])
            pts += [x["reason"] for x in r["reasons"][:3]]
        pts += integrity(cid)["flags"][:2]
        cp = career_path(cid)
        if cp["pattern"] == "hopping":
            pts.append(cp["story"])
    else:
        side = "Reasons to reconsider"
        pts += [f"Proves {r['skill']}: \"{r['evidence'][:90]}\"" for r in m["rows"] if r["status"] == "Proven"][:3]
        tr = insights.hire_and_train(job_id, cid)
        if tr["trainable"]:
            pts.append(tr["text"])
        gem = next((g for g in hidden_gems(1) if g["candidate_id"] == cid), None)
        if gem:
            pts += gem["signals"][:2]
        if m["years"] >= m["min_years"]:
            pts.append(f"Meets the experience ask ({m['years']:g} years)")
    pts = pts or ["No strong counter-points found. The current view looks balanced."]
    out = llm.generate(f"A recruiter is about to decide on a candidate. Write a short, fair 'second opinion' titled "
                       f"'{side}' as 3 bullet points using ONLY these facts:\n" + "\n".join(f"- {p}" for p in pts),
                       max_tokens=250)
    return {"side": side, "points": pts[:6], "text": out, "ai": bool(out)}


# =========================================================== 37 + 39. pool health and skill demand
def pool_health() -> list[dict]:
    out = []
    for j in recruit.list_jobs(status="Open"):
        res = recruit.compute_job(j["id"], scope="all")
        inside = [r for r in res if r["stage"] and r["stage"] != "Rejected"]
        pool = [r for r in res if not r["stage"]]
        ready = [r for r in pool if r["score"] >= 70]
        near = [r for r in pool if 50 <= r["score"] < 70]
        status = "healthy" if len(ready) >= 2 or len(inside) >= 4 else "thin" if ready or near else "empty"
        out.append({"job_id": j["id"], "job": j["title"], "in_pipeline": len(inside), "ready_in_pool": len(ready),
                    "near_in_pool": len(near), "status": status,
                    "ready_names": [r["name"] for r in ready[:3]]})
    return out


def skill_demand() -> list[dict]:
    demand = Counter()
    for j in recruit.list_jobs(status="Open"):
        for s in j["must"]:
            demand[s] += 1
    supply = Counter(r["skill"] for r in db.rows("SELECT cs.skill FROM candidate_skills cs JOIN candidates c "
                                                 "ON c.id=cs.candidate_id WHERE cs.status='Proven' AND c.anonymised_at IS NULL"))
    n = db.one("SELECT COUNT(*) n FROM candidates WHERE anonymised_at IS NULL")["n"] or 1
    out = [{"skill": s, "jobs_need": d, "people_prove": supply.get(s, 0), "pct": round(supply.get(s, 0) / n * 100),
            "gap": "short" if supply.get(s, 0) / n < 0.25 else "ok"} for s, d in demand.items()]
    return sorted(out, key=lambda x: (x["gap"] != "short", x["pct"]))


# =========================================================== 40. duplicates and merge
def _digits(p):
    return re.sub(r"\D", "", p or "")[-10:]


def duplicates() -> list[dict]:
    cs = db.rows("SELECT id, name, email, phone, location, cv_text, created_at FROM candidates WHERE anonymised_at IS NULL")
    out, seen = [], set()
    from ..core import ml
    sims = {a["id"]: dict(ml.similar(cs, a["id"], k=len(cs))) for a in cs} if len(cs) > 1 else {}
    for i, a in enumerate(cs):
        for b in cs[i + 1:]:
            why = []
            if _digits(a["phone"]) and _digits(a["phone"]) == _digits(b["phone"]):
                why.append("same phone")
            if a["email"] and b["email"] and a["email"].split("@")[0].replace(".", "") == b["email"].split("@")[0].replace(".", ""):
                why.append("almost the same email")
            if a["name"].lower() == b["name"].lower() and (a["location"] or "").lower() == (b["location"] or "").lower():
                why.append("same name and city")
            if why and (a["id"], b["id"]) not in seen:
                seen.add((a["id"], b["id"]))
                sim = sims.get(a["id"], {}).get(b["id"], 0)
                out.append({"keep_id": a["id"], "keep": a["name"], "keep_email": a["email"], "dup_id": b["id"],
                            "dup": b["name"], "dup_email": b["email"], "why": why, "cv_similarity": round(sim * 100)})
    return out


def merge(keep_id: int, dup_id: int, by: str) -> dict:
    if keep_id == dup_id:
        raise ValueError("Pick two different people.")
    k, d = recruit.get_candidate(keep_id), recruit.get_candidate(dup_id)
    moved = 0
    for a in db.rows("SELECT * FROM applications WHERE candidate_id=?", (dup_id,)):
        if recruit.app_for(a["job_id"], keep_id):
            continue
        db.run("UPDATE applications SET candidate_id=? WHERE id=?", (keep_id, a["id"]))
        moved += 1
    db.run("UPDATE notes SET candidate_id=? WHERE candidate_id=?", (keep_id, dup_id))
    db.run("UPDATE activity_logs SET candidate_id=? WHERE candidate_id=?", (keep_id, dup_id))
    db.run("UPDATE candidates SET phone=COALESCE(NULLIF(phone,''),?), email=COALESCE(NULLIF(email,''),?) WHERE id=?",
           (d["phone"], d["email"], keep_id))
    recruit.delete_candidate(dup_id, by)
    db.log("Duplicates merged", f"{d['name']} (#{dup_id}) into #{keep_id}", by, candidate_id=keep_id)
    for j in db.rows("SELECT DISTINCT job_id FROM applications WHERE candidate_id=?", (keep_id,)):
        recruit.compute_job(j["job_id"])
    return {"ok": True, "moved_applications": moved, "kept": k["name"]}
