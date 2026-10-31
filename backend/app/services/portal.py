"""Candidate portal: what a candidate can see and do.

A candidate sees only their own applications (stage in plain words, never their score),
the emails the recruiter SENT them (never drafts), their interview, and open jobs.
Replies and interview answers go back to the recruiter's inbox as messages.
"""
from __future__ import annotations

import json

from .. import db
from ..core.parsing import parse_cv
from ..security import check_pw, hash_pw, make_candidate_token
from . import assist, recruit

DEMO_CANDIDATE_PASSWORD = "candidate123"
LABEL = {"Applied": "Received", "Screening": "Under review", "Shortlisted": "Shortlisted", "Interview": "Interview",
         "Selected": "Selected", "Rejected": "Closed"}
FLOW = ["Applied", "Screening", "Shortlisted", "Interview", "Selected"]


class PortalError(ValueError):
    pass


def ensure_account(cid: int, password: str = DEMO_CANDIDATE_PASSWORD) -> None:
    """Every candidate gets a portal account (demo password) so they can read and reply to emails."""
    c = recruit.get_candidate(cid)
    if not c.get("email") or db.one("SELECT 1 FROM candidate_accounts WHERE candidate_id=?", (cid,)):
        return
    if db.one("SELECT 1 FROM candidate_accounts WHERE lower(email)=lower(?)", (c["email"],)):
        return
    db.run("INSERT INTO candidate_accounts(candidate_id,email,password_hash,created_at) VALUES(?,?,?,?)",
           (cid, c["email"].lower(), hash_pw(password), db.now()))


def ensure_all_accounts() -> None:
    for r in db.rows("SELECT c.id FROM candidates c LEFT JOIN candidate_accounts a ON a.candidate_id=c.id "
                     "WHERE a.candidate_id IS NULL AND c.email IS NOT NULL AND c.email!=''"):
        ensure_account(r["id"])


def login(email: str, password: str) -> dict:
    a = db.one("SELECT * FROM candidate_accounts WHERE lower(email)=lower(?)", (email.strip(),))
    if not a or not check_pw(password, a["password_hash"]):
        raise PortalError("Wrong email or password.")
    db.run("UPDATE candidate_accounts SET last_login=? WHERE candidate_id=?", (db.now(), a["candidate_id"]))
    return {"token": make_candidate_token(a["candidate_id"]), "candidate": profile(a["candidate_id"])}


def signup(name: str, email: str, password: str, cv_text: str, job_id: int | None, file_name: str | None) -> dict:
    """A new candidate makes an account by uploading a CV. The CV is read and matched like any other."""
    email = email.strip().lower()
    if len(password) < 6:
        raise PortalError("Use at least 6 characters for the password.")
    if db.one("SELECT 1 FROM candidate_accounts WHERE email=?", (email,)):
        raise PortalError("An account with this email already exists. Sign in instead.")
    if len(cv_text.split()) < 20:
        raise PortalError("The CV looks empty. Upload a PDF, Word or text CV.")
    # make sure the name and email the person typed are what the CV parser sees first
    text = f"{name.strip()}\nEmail: {email}\n" + cv_text
    existing = db.one("SELECT id FROM candidates WHERE lower(email)=?", (email,))
    if existing:
        cid = existing["id"]
    else:
        cid = recruit.create_candidate(text, "Candidate portal", source="Portal", file_name=file_name,
                                       allow_duplicate=True)["id"]
    db.run("INSERT INTO candidate_accounts(candidate_id,email,password_hash,created_at) VALUES(?,?,?,?)",
           (cid, email, hash_pw(password), db.now()))
    if job_id:
        apply(cid, job_id)
    return {"token": make_candidate_token(cid), "candidate": profile(cid)}


def profile(cid: int) -> dict:
    c = recruit.get_candidate(cid)
    skills = [s["skill"] for s in c.get("skills", [])]
    return {"id": cid, "name": c["name"], "email": c["email"], "phone": c["phone"], "location": c["location"],
            "headline": c["headline"], "education": c["education"], "years": c["years"], "skills": skills,
            "cv_text": c["cv_text"], "file_name": c.get("file_name")}


def update_profile(cid: int, phone: str | None, location: str | None) -> dict:
    db.run("UPDATE candidates SET phone=COALESCE(?,phone), location=COALESCE(?,location) WHERE id=?",
           (phone, location, cid))
    db.log("Profile updated by candidate", "phone / city", "Candidate", candidate_id=cid, entity="candidate", entity_id=cid)
    return profile(cid)


def replace_cv(cid: int, text: str, file_name: str | None) -> dict:
    """Candidate uploads a new CV: re-read it, keep the same person, re-score every job they applied to."""
    c = recruit.get_candidate(cid)
    if len(text.split()) < 20:
        raise PortalError("The CV looks empty.")
    p = parse_cv(f"{c['name']}\nEmail: {c['email']}\n" + text)
    db.run("UPDATE candidates SET phone=COALESCE(NULLIF(?,''),phone), location=?, headline=?, summary=?, education=?, "
           "edu_level=?, years=?, roles_json=?, cv_text=?, file_name=? WHERE id=?",
           (p["phone"], p["location"], p["headline"], p["summary"], p["education"], p["edu_level"], p["years"],
            json.dumps(p["roles"]), p["cv_text"], file_name, cid))
    db.run("DELETE FROM candidate_skills WHERE candidate_id=?", (cid,))
    for s, v in p["skills"].items():
        db.run("INSERT OR IGNORE INTO candidate_skills VALUES(?,?,?,?)", (cid, s, v["status"], v["evidence"]))
    from ..adapters.vectorstore import get_store
    get_store().upsert(f"cand:{cid}", p["cv_text"], {"type": "CV", "title": c["name"], "ref_id": cid})
    for a in db.rows("SELECT DISTINCT job_id FROM applications WHERE candidate_id=?", (cid,)):
        recruit.compute_job(a["job_id"])
    db.log("New CV uploaded by candidate", file_name or "text", "Candidate", candidate_id=cid, entity="candidate",
           entity_id=cid)
    return profile(cid)


def applications(cid: int) -> list[dict]:
    out = []
    for a in db.rows("SELECT a.*, j.title, j.location FROM applications a JOIN jobs j ON j.id=a.job_id "
                     "WHERE a.candidate_id=? ORDER BY a.id DESC", (cid,)):
        iv = db.one("SELECT * FROM interviews WHERE application_id=? AND status='Scheduled' ORDER BY id DESC", (a["id"],))
        out.append({"application_id": a["id"], "job_id": a["job_id"], "title": a["title"], "location": a["location"],
                    "stage": a["stage"], "label": LABEL.get(a["stage"], a["stage"]),
                    "step": FLOW.index(a["stage"]) if a["stage"] in FLOW else -1, "applied_on": (a["created_at"] or "")[:10],
                    "interview": {k: iv[k] for k in ("id", "date", "time", "mode", "interviewer", "candidate_response",
                                                      "candidate_note")} if iv else None})
    return out


def open_jobs(cid: int) -> list[dict]:
    mine = {r["job_id"] for r in db.rows("SELECT job_id FROM applications WHERE candidate_id=?", (cid,))}
    return [{"id": j["id"], "title": j["title"], "location": j["location"], "min_years": j["min_years"],
             "must": j["must"], "nice": j["nice"], "description": j["description"], "applied": j["id"] in mine}
            for j in recruit.list_jobs(status="Open")]


def apply(cid: int, job_id: int) -> dict:
    j = recruit.get_job(job_id)
    if j["status"] != "Open":
        raise PortalError("This job is not open.")
    a = recruit.apply(job_id, cid, "Candidate portal")
    return {"ok": True, "application_id": a["id"], "title": j["title"]}


def messages(cid: int) -> list[dict]:
    """Sent emails to the candidate + their own replies. Drafts are never shown."""
    rows = db.rows("SELECT e.id FROM emails e JOIN applications a ON a.id=e.application_id WHERE a.candidate_id=? "
                   "AND (e.status='Sent' OR e.direction='in') ORDER BY COALESCE(e.sent_at, e.created_at) DESC, e.id DESC",
                   (cid,))
    out = []
    for r in rows:
        e = assist.get_email(r["id"])
        out.append({"id": e["id"], "job_id": e["job_id"], "job_title": e["job_title"], "subject": e["subject"],
                    "body": e["body"], "type_label": e["type_label"], "from_me": e["direction"] == "in",
                    "at": e["sent_at"] or e["created_at"], "parent_id": e.get("parent_id"),
                    "unread": e["direction"] == "out" and not e.get("cand_read_at")})
    return out


def _own_email(cid: int, eid: int) -> dict:
    e = assist.get_email(eid)
    if e["candidate_id"] != cid or (e["direction"] == "out" and e["status"] != "Sent"):
        raise PortalError("Message not found.")
    return e


def reply(cid: int, eid: int, body: str) -> dict:
    """Candidate replies. The reply lands in the recruiter's inbox as an unread message."""
    if not body.strip():
        raise PortalError("Write a message first.")
    e = _own_email(cid, eid)
    subj = e["subject"] if e["subject"].lower().startswith("re:") else f"Re: {e['subject']}"
    new = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,parent_id,created_at,sent_at) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?)", (e["application_id"], "candidate", e["lang"], subj, body.strip()[:4000],
                                                  "Received", "in", eid, db.now(), db.now()))
    db.log("Candidate replied", subj, e["candidate"], candidate_id=cid, job_id=e["job_id"], entity="email", entity_id=new)
    return {"ok": True, "id": new}


def respond_interview(cid: int, iid: int, response: str, note: str = "") -> dict:
    """Confirm, or ask for another time. Sent to the recruiter as a message too, so nothing is missed."""
    if response not in ("Confirmed", "Reschedule requested"):
        raise PortalError("Choose Confirm or Ask for another time.")
    iv = db.one("SELECT i.*, a.candidate_id, a.job_id FROM interviews i JOIN applications a ON a.id=i.application_id "
                "WHERE i.id=?", (iid,))
    if not iv or iv["candidate_id"] != cid:
        raise PortalError("Interview not found.")
    db.run("UPDATE interviews SET candidate_response=?, candidate_note=?, responded_at=? WHERE id=?",
           (response, note.strip()[:500], db.now(), iid))
    j = recruit.get_job(iv["job_id"])
    when = assist.fmt_when(iv)
    text = (f"I confirm the interview on {when}." if response == "Confirmed"
            else f"Could we move the interview on {when}? " + (note.strip() or "Please suggest another time."))
    if response == "Confirmed" and note.strip():
        text += "\n\n" + note.strip()
    db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at) "
           "VALUES(?,?,?,?,?,?,?,?,?)", (iv["application_id"], "candidate", "English",
                                          f"Interview {response.lower()}: {j['title']}", text, "Received", "in",
                                          db.now(), db.now()))
    db.log(f"Interview {response.lower()}", note[:80], "Candidate", candidate_id=cid, job_id=iv["job_id"],
           entity="interview", entity_id=iid)
    return {"ok": True}


def mark_read(cid: int, eid: int) -> None:
    _own_email(cid, eid)
    db.run("UPDATE emails SET cand_read_at=COALESCE(cand_read_at, ?) WHERE id=?", (db.now(), eid))
