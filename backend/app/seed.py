"""Seed the demo database with synthetic data. Run: python -m backend.app.seed"""
from __future__ import annotations

import json
from datetime import date, timedelta

from . import db
from .adapters.vectorstore import get_store
from .config import DEMO_PASSWORD
from .sample_data import CVS, HR_DOCS, JOBS
from .security import hash_pw
from .services import recruit

USERS = [("admin@hiremate.demo", "Demo Admin", "Admin"),
         ("recruiter@hiremate.demo", "Demo Recruiter", "Recruiter"),
         ("interviewer@hiremate.demo", "Demo Interviewer", "Interviewer")]

# job key, cv key, stage
APPS = [("sm", "c1", "Shortlisted"), ("sm", "c2", "Screening"), ("sm", "c4", "Applied"), ("sm", "c5", "Screening"),
        ("ca", "c3", "Interview"), ("ca", "c2", "Applied"), ("ca", "c7", "Applied"),
        ("wh", "c6", "Interview"), ("wh", "c4", "Applied")]


def _add_contact(key: str, text: str) -> str:
    """Give each synthetic CV a fake example.com email and a dummy phone so contact features can be shown.
    One CV (c3) has no phone on purpose, to show the 'things to check' flag."""
    name = text.splitlines()[0].strip().lower().replace(" ", ".")
    lines = text.splitlines()
    lines.insert(1, f"Email: {name}@example.com")
    if key != "c3":
        lines.insert(2, f"Phone: +91 90000 0{int(key[1:]):04d}")  # clearly fake numbers
    return "\n".join(lines)


def reset_and_seed() -> None:
    c = db.conn()
    keep_ai = db.get_setting("ai")  # AI keys survive a demo reset
    keep_guide = db.get_setting("ai_guidelines")
    tables = [r["name"] for r in db.rows("SELECT name FROM sqlite_master WHERE type='table'")]
    c.execute("PRAGMA foreign_keys=OFF")
    for t in tables:
        c.execute(f"DELETE FROM {t}")
    c.commit()
    c.execute("PRAGMA foreign_keys=ON")
    try:
        get_store().clear()
    except Exception:  # noqa: BLE001
        pass

    for email, name, role in USERS:
        db.run("INSERT INTO users(email,name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
               (email, name, role, hash_pw(DEMO_PASSWORD), db.now()))
    db.set_setting("weights", {"skills": 50, "text": 30, "exp": 20})
    db.set_setting("blind", False)
    if keep_ai:
        db.set_setting("ai", keep_ai)
    if keep_guide:
        db.set_setting("ai_guidelines", keep_guide)

    by = "Seed"
    job_ids = {k: recruit.create_job(t, by, source="Seed")["id"] for k, t in JOBS.items()}
    cand_ids = {k: recruit.create_candidate(_add_contact(k, t), by, source="Seed")["id"] for k, t in CVS.items()}
    for title, text in HR_DOCS:
        did = db.run("INSERT INTO knowledge_docs(title,type,text,source,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                     (title, "FAQ" if title.startswith("FAQ") else "Policy", text, "Seed", db.now(), db.now()))
        get_store().upsert(f"doc:{did}", f"{title}\n{text}", {"type": "Policy", "title": title, "ref_id": did})

    apps = {}
    for jk, ck, stage in APPS:
        a = recruit.apply(job_ids[jk], cand_ids[ck], by)
        recruit.set_stage(a["id"], stage, by) if stage != "Applied" else None
        apps[(jk, ck)] = a["id"]

    today = date.today()
    db.run("INSERT INTO interviews(application_id,date,time,mode,interviewer,status,created_at) VALUES(?,?,?,?,?,?,?)",
           (apps[("wh", "c6")], str(today + timedelta(days=3)), "11:00", "In person", "Area Manager, Gurugram DC",
            "Scheduled", db.now()))
    db.run("INSERT INTO interviews(application_id,date,time,mode,interviewer,status,created_at) VALUES(?,?,?,?,?,?,?)",
           (apps[("ca", "c3")], str(today - timedelta(days=1)), "15:00", "In person", "Store Manager, Raj Nagar",
            "Done", db.now()))
    db.run("INSERT INTO interview_feedback(application_id,scores_json,text,by_name,readiness,created_at) "
           "VALUES(?,?,?,?,?,?)",
           (apps[("ca", "c3")], json.dumps({"Customer service": 4, "POS systems": 5, "Cash handling": 5}),
            "Very quick and accurate on the billing test: 2 errors in 50 bills. Calm with an upset customer in the "
            "role-play. Needs coaching on the returns policy. Recommend for selection.",
            "Store Manager, Raj Nagar", None, db.now()))
    db.run("INSERT INTO notes(candidate_id,job_id,text,by_name,created_at) VALUES(?,?,?,?,?)",
           (cand_ids["c1"], job_ids["sm"], "Strong festive-season experience. Ask about P&L exposure in the interview.",
            "Demo Admin", db.now()))
    # a sent invite and a reply from the candidate, so both portals show a real conversation
    from .services import assist as _assist
    from .services import portal as _portal
    inv = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at,sent_by,"
                 "approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                 (apps[("wh", "c6")], "invite", "English", "Interview for Warehouse Supervisor",
                  f"Dear Arjun,\n\nThank you for applying for the Warehouse Supervisor role (Gurugram distribution centre). "
                  f"We would like to invite you to an interview on {(today + timedelta(days=3)):%a %d %b} at 11:00 AM, in person, "
                  "with the Area Manager.\n\nPlease bring a photo ID and a copy of your CV. Reply to confirm, or to ask for "
                  f"another slot.\n\nRegards,\nRecruitment Team\n\n{_assist.AI_LINE}", "Sent", "out", db.now(), db.now(),
                  "Demo Admin", "Demo Admin", db.now()))
    _portal.reply(cand_ids["c6"], inv, "Thank you, I will be there. Is there parking at the distribution centre, and "
                                       "should I bring my forklift certificate?")
    # some people have waited a few days, so 'Waiting too long' has something to show
    import datetime as _dt
    old_ts = (_dt.datetime.now() - _dt.timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
    db.run("UPDATE applications SET updated_at=?, created_at=? WHERE candidate_id=? AND stage='Applied'",
           (old_ts, old_ts, cand_ids["c4"]))
    recruit.recompute_all()


def ensure_seeded() -> None:
    if not db.one("SELECT id FROM users LIMIT 1"):
        reset_and_seed()


if __name__ == "__main__":
    reset_and_seed()
    print("Seeded demo data. Sign in with admin@hiremate.demo /", DEMO_PASSWORD)
