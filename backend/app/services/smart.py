"""Small helpers that save the recruiter time:

- red_flags: things to check on a CV (gaps, short jobs, missing contact, years, duplicates)
- free_slots: suggest interview times that don't clash
- move: change stage and draft the matching email (never sends; recruiter approves)
- waiting: people stuck in one stage too long
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from .. import db
from ..core import parsing
from . import assist, recruit

# which email to draft when a candidate moves to a stage
STAGE_EMAIL = {"Rejected": "rejection", "Selected": "selection"}
WAIT_DAYS = {"Applied": 3, "Screening": 3, "Shortlisted": 3}


def _span(dates: str) -> tuple[int, int] | None:
    """'Mar 2021 – Present' -> (start_month_index, end_month_index)."""
    m = parsing.DATE_RANGE.search(dates or "")
    if not m or parsing._month(m.group(1)) is None:
        return None
    start = int(m.group(2)) * 12 + parsing._month(m.group(1))
    if re.search(r"present|current|now|till", m.group(3), re.I):
        t = date.today()
        end = t.year * 12 + t.month - 1
    elif m.group(5) and parsing._month(m.group(4)) is not None:
        end = int(m.group(5)) * 12 + parsing._month(m.group(4))
    else:
        end = start
    return start, end


def _ym(i: int) -> str:
    return f"{datetime(i // 12, i % 12 + 1, 1):%b %Y}"


def red_flags(cid: int, job_id: int | None = None) -> list[dict]:
    """Plain-English things to check. level: 'warn' (ask about it) or 'info' (good to know)."""
    c = recruit.get_candidate(cid)
    roles = c.get("roles") or json.loads(c.get("roles_json") or "[]")
    out = []
    spans = sorted([s for s in (_span(r.get("dates", "")) for r in roles) if s])
    for (s1, e1), (s2, _) in zip(spans, spans[1:]):
        gap = s2 - e1 - 1
        if gap >= 6:
            out.append({"level": "warn", "text": f"Gap of {gap} months between jobs ({_ym(e1)} to {_ym(s2)}). Ask what they did."})
    t = date.today()
    now = t.year * 12 + t.month - 1
    short = [r for r, s in ((r, _span(r.get("dates", ""))) for r in roles) if s and s[1] < now - 1 and s[1] - s[0] + 1 < 12]
    if len(short) >= 2:
        out.append({"level": "warn", "text": f"{len(short)} jobs lasted less than a year. Ask why they left."})
    if not c.get("phone"):
        out.append({"level": "warn", "text": "No phone number in the CV."})
    if not c.get("email"):
        out.append({"level": "warn", "text": "No email in the CV. You can't send emails until you add one."})
    if job_id:
        j = recruit.get_job(job_id)
        need = float(j.get("min_years") or 0)
        yrs = float(c.get("years") or 0)
        if need and yrs < need:
            out.append({"level": "warn", "text": f"Has {yrs:g} years. The job asks for {need:g}+."})
        elif need and yrs >= max(need * 3, need + 8):
            out.append({"level": "info", "text": f"Has {yrs:g} years, much more than the {need:g}+ asked. May expect higher pay."})
    dup = db.rows("SELECT id, name FROM candidates WHERE id!=? AND ((email!='' AND email=?) OR (phone!='' AND phone=?) "
                  "OR lower(name)=lower(?))", (cid, c.get("email") or "-", c.get("phone") or "-", c["name"]))
    for d in dup[:2]:
        out.append({"level": "warn", "text": f"Possible duplicate: {d['name']} (candidate #{d['id']}) has the same name, email or phone.",
                    "candidate_id": d["id"]})
    if len((c.get("cv_text") or "").split()) < 60:
        out.append({"level": "info", "text": "Very short CV. Ask for more detail in the call."})
    return out


def free_slots(job_id: int, cid: int, interviewer: str | None = None, n: int = 3) -> list[dict]:
    """Next free weekday slots (10:00–17:00, on the hour) with no clash for the interviewer or the candidate."""
    busy = {(r["date"], r["time"]) for r in db.rows(
        "SELECT i.date, i.time, i.interviewer, a.candidate_id FROM interviews i JOIN applications a ON a.id=i.application_id "
        "WHERE i.status='Scheduled' AND (a.candidate_id=? OR (? IS NOT NULL AND i.interviewer=?))",
        (cid, interviewer, interviewer))}
    out, d = [], date.today() + timedelta(days=1)
    hours = ["11:00", "15:00", "10:00", "12:00", "16:00", "14:00"]  # spread suggestions over the day
    while len(out) < n and d < date.today() + timedelta(days=21):
        if d.weekday() < 6:  # Mon–Sat (stores work Saturdays)
            k = len(out)  # rotate the hour so suggestions give a real choice (morning / afternoon)
            for h in hours[k:] + hours[:k]:
                if (str(d), h) not in busy:
                    hr = int(h[:2])
                    out.append({"date": str(d), "time": h,
                                "label": f"{d:%a} {d.day} {d:%b} · {hr % 12 or 12} {'AM' if hr < 12 else 'PM'}"})
                    break
        d += timedelta(days=1)
    return out


def book(job_id: int, cid: int, d: str, t: str, mode: str, interviewer: str, by: str) -> dict:
    """Book (or move) the interview, set stage to Interview, draft the invitation."""
    from . import interviews
    iv = interviews.schedule(job_id, cid, d, t, mode, interviewer, by)
    a = recruit.app_for(job_id, cid)
    if a and a["stage"] in ("Applied", "Screening", "Shortlisted"):
        recruit.set_stage(a["id"], "Interview", by)
    e = assist.draft_email(job_id, cid, "invite", "English", by)
    return {"interview": iv, "email_id": e["id"]}


def move(app_id: int, stage: str, by: str, draft: bool = True) -> dict:
    """Change stage; draft the matching email. Returns old stage too, so the screen can offer Undo."""
    a = recruit.get_app(app_id)
    old = a["stage"]
    new = recruit.set_stage(app_id, stage, by)
    email_id = None
    if draft and stage in STAGE_EMAIL and old != stage:
        have = db.one("SELECT id FROM emails WHERE application_id=? AND type=? AND status='Draft'", (app_id, STAGE_EMAIL[stage]))
        email_id = have["id"] if have else assist.draft_email(a["job_id"], a["candidate_id"], STAGE_EMAIL[stage], "English", by)["id"]
    return {"application": new, "old_stage": old, "email_id": email_id}


def undo(app_id: int, old_stage: str, email_id: int | None, by: str) -> dict:
    """Put the stage back and drop the draft that the move created (only if still a draft)."""
    if email_id:
        db.run("DELETE FROM emails WHERE id=? AND status='Draft'", (email_id,))
    a = recruit.set_stage(app_id, old_stage, by)
    db.log("Undo", f"Back to {old_stage}", by, candidate_id=a["candidate_id"], job_id=a["job_id"], entity="application",
           entity_id=app_id)
    return a


def waiting() -> list[dict]:
    """People who have been in the same early stage for too long."""
    rows = db.rows("SELECT a.id, a.stage, a.job_id, a.candidate_id, coalesce(a.updated_at, a.created_at) since, "
                   "c.name, j.title FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                   "JOIN jobs j ON j.id=a.job_id WHERE j.status='Open'")
    out = []
    for r in rows:
        lim = WAIT_DAYS.get(r["stage"])
        if not lim or not r["since"]:
            continue
        try:
            days = (datetime.now() - datetime.strptime(r["since"][:19], "%Y-%m-%d %H:%M:%S")).days
        except ValueError:
            continue
        if days >= lim:
            out.append({"application_id": r["id"], "job_id": r["job_id"], "candidate_id": r["candidate_id"],
                        "name": r["name"], "job": r["title"], "stage": r["stage"], "days": days})
    return sorted(out, key=lambda x: -x["days"])


def next_action(job_id: int) -> dict:
    """The one thing to do next on this job, in plain words."""
    counts = {s: 0 for s in recruit.STAGES}
    for a in db.rows("SELECT stage FROM applications WHERE job_id=?", (job_id,)):
        counts[a["stage"]] = counts.get(a["stage"], 0) + 1
    fb = db.rows("SELECT a.candidate_id, c.name FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                 "WHERE a.job_id=? AND a.stage='Interview' AND EXISTS(SELECT 1 FROM interview_feedback f WHERE f.application_id=a.id)",
                 (job_id,))
    no_iv = db.rows("SELECT a.candidate_id, c.name FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                    "WHERE a.job_id=? AND a.stage='Shortlisted' AND NOT EXISTS(SELECT 1 FROM interviews i "
                    "WHERE i.application_id=a.id AND i.status='Scheduled')", (job_id,))
    to_review = counts["Applied"] + counts["Screening"]
    total = sum(counts.values())
    if total == 0:
        return {"kind": "add", "text": "No CVs yet. Add CVs to start.", "button": "Add CVs"}
    if to_review:
        return {"kind": "review", "text": f"{to_review} {'person is' if to_review == 1 else 'people are'} waiting for review.",
                "button": "Start quick review"}
    if no_iv:
        return {"kind": "book", "text": f"Book an interview with {no_iv[0]['name']}"
                + (f" and {len(no_iv) - 1} more" if len(no_iv) > 1 else "") + ".", "button": "Book interview",
                "candidate_id": no_iv[0]["candidate_id"]}
    if fb:
        return {"kind": "decide", "text": f"Feedback is in for {fb[0]['name']}. Hire or not?", "button": "Decide",
                "candidate_id": fb[0]["candidate_id"]}
    if counts["Interview"]:
        return {"kind": "wait", "text": "Interviews are booked. Add feedback after each one.", "button": None}
    if counts["Selected"]:
        return {"kind": "done", "text": f"{counts['Selected']} hired. Close the job when you're done.", "button": None}
    return {"kind": "add", "text": "Everyone is reviewed. Add more CVs or look in the talent pool.", "button": "Add CVs"}
