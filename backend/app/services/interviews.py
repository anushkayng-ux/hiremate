"""Interview scheduling, scorecards and feedback."""
from __future__ import annotations

import json
from datetime import date

from .. import db
from . import recruit


def _row(r: dict) -> dict:
    r["questions"] = json.loads(r.pop("questions_json") or "null")
    return r


BASE = ("SELECT i.*, a.job_id, a.candidate_id, a.stage, c.name candidate, j.title job_title FROM interviews i "
        "JOIN applications a ON a.id=i.application_id JOIN candidates c ON c.id=a.candidate_id "
        "JOIN jobs j ON j.id=a.job_id")


def get(iid: int) -> dict:
    r = db.one(BASE + " WHERE i.id=?", (iid,))
    if not r:
        raise recruit.NotFound("Interview not found")
    return _row(r)


def list_all(when: str | None = None, cid: int | None = None, job_id: int | None = None) -> list[dict]:
    """when = upcoming | past | None."""
    sql, p = BASE + " WHERE 1=1", []
    today = str(date.today())
    if when == "upcoming":
        sql += " AND i.date>=? AND i.status='Scheduled'"
        p.append(today)
    elif when == "past":
        sql += " AND (i.date<? OR i.status!='Scheduled')"
        p.append(today)
    if cid:
        sql += " AND a.candidate_id=?"
        p.append(cid)
    if job_id:
        sql += " AND a.job_id=?"
        p.append(job_id)
    out = [_row(r) for r in db.rows(sql + " ORDER BY i.date, i.time", p)]
    for r in out:
        r["has_feedback"] = bool(db.one("SELECT id FROM interview_feedback WHERE application_id=?",
                                        (r["application_id"],)))
    return out


def schedule(job_id: int, cid: int, d: str, t: str, mode: str, interviewer: str, by: str) -> dict:
    date.fromisoformat(d)  # validates
    a = recruit.app_for(job_id, cid) or recruit.apply(job_id, cid, by)
    old = db.one("SELECT id FROM interviews WHERE application_id=? AND status='Scheduled'", (a["id"],))
    if old:
        db.run("UPDATE interviews SET date=?, time=?, mode=?, interviewer=? WHERE id=?", (d, t, mode, interviewer, old["id"]))
        iid = old["id"]
        action = "Interview rescheduled"
    else:
        iid = db.run("INSERT INTO interviews(application_id,date,time,mode,interviewer,status,created_at) "
                     "VALUES(?,?,?,?,?,?,?)", (a["id"], d, t, mode, interviewer, "Scheduled", db.now()))
        action = "Interview scheduled"
    if a["stage"] in ("Applied", "Screening", "Shortlisted"):
        recruit.set_stage(a["id"], "Interview", by)
    db.log(action, f"{d} {t}, {mode}, {interviewer}", by, candidate_id=cid, job_id=job_id, entity="interview",
           entity_id=iid)
    return get(iid)


def set_status(iid: int, status: str, by: str) -> dict:
    if status not in ("Scheduled", "Done", "Cancelled", "No-show"):
        raise ValueError("Bad status")
    iv = get(iid)
    db.run("UPDATE interviews SET status=? WHERE id=?", (status, iid))
    db.log(f"Interview {status.lower()}", "", by, candidate_id=iv["candidate_id"], job_id=iv["job_id"])
    return get(iid)


def save_feedback(job_id: int, cid: int, scores: dict, text: str, by: str) -> dict:
    from .assist import readiness
    a = recruit.app_for(job_id, cid)
    if not a:
        raise recruit.NotFound("Candidate is not in this job")
    r = readiness(job_id, cid, scores)
    fid = db.run("INSERT INTO interview_feedback(application_id,scores_json,text,by_name,readiness,created_at) "
                 "VALUES(?,?,?,?,?,?)", (a["id"], json.dumps(scores), text, by, r, db.now()))
    db.run("UPDATE interviews SET status='Done' WHERE application_id=? AND status='Scheduled' AND date<=?",
           (a["id"], str(date.today())))
    db.log("Feedback added", (text or "")[:80], by, candidate_id=cid, job_id=job_id)
    return get_feedback(job_id, cid) | {"id": fid}


def get_feedback(job_id: int, cid: int) -> dict | None:
    a = recruit.app_for(job_id, cid)
    if not a:
        return None
    fb = db.one("SELECT * FROM interview_feedback WHERE application_id=? ORDER BY id DESC LIMIT 1", (a["id"],))
    if fb:
        fb["scores"] = json.loads(fb.pop("scores_json") or "{}")
    return fb
