"""Features most recruiting tools have that HireMate was missing (found in the competitor gap review):

1. Screening (knockout) questions per job, answered by candidates when they apply.
   A wrong knockout answer only FLAGS the person. AI and code never reject anyone.
2. Offer letters: drafted from the job + numbers the recruiter types, downloadable as Word,
   sent to the candidate portal, where the candidate can accept or decline.
3. WhatsApp: a short version of any email + a click-to-chat link (most store staff in India read WhatsApp first).
4. Calendar invites (.ics) for every interview.
5. Source of hire + referrals, time-to-hire and time-in-stage reports.
6. CSV export of a job's ranked list.
7. Privacy (India DPDP Act 2023): consent at sign-up, a candidate can erase their data,
   admin can anonymise old candidates who were never hired.
"""
from __future__ import annotations

import csv
import io
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone

from .. import db
from ..adapters import llm
from . import assist, recruit

SOURCES = ["Recruiter upload", "Candidate portal", "Referral", "Walk-in", "Naukri", "LinkedIn", "Indeed",
           "Apna", "Talent pool", "Campus"]
KINDS = {"yesno": "Yes / No", "number": "Number", "text": "Short answer"}


class ExtraError(ValueError):
    pass


def _ts(s: str | None) -> datetime | None:
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


# =============================================================== 1. screening questions
def questions(job_id: int) -> list[dict]:
    return db.rows("SELECT * FROM screening_questions WHERE job_id=? ORDER BY position, id", (job_id,))


def add_question(job_id: int, question: str, kind: str, ideal: str | None, knockout: bool, by: str) -> dict:
    recruit.get_job(job_id)
    if kind not in KINDS:
        raise ExtraError(f"Type must be one of {', '.join(KINDS)}")
    if len(question.strip()) < 5:
        raise ExtraError("Write the question first.")
    if kind == "number" and ideal and not re.fullmatch(r"\s*(>=|<=)?\s*\d+(\.\d+)?\s*", ideal):
        raise ExtraError("For a number question, the ideal answer looks like '>= 1' or '<= 30'.")
    pos = (db.one("SELECT MAX(position) m FROM screening_questions WHERE job_id=?", (job_id,))["m"] or 0) + 1
    qid = db.run("INSERT INTO screening_questions(job_id,question,kind,ideal,knockout,position,created_at) "
                 "VALUES(?,?,?,?,?,?,?)", (job_id, question.strip(), kind, (ideal or "").strip() or None,
                                           int(knockout), pos, db.now()))
    db.log("Screening question added", question[:80], by, job_id=job_id, entity="job", entity_id=job_id)
    return db.one("SELECT * FROM screening_questions WHERE id=?", (qid,))


def delete_question(qid: int, by: str) -> None:
    q = db.one("SELECT * FROM screening_questions WHERE id=?", (qid,))
    if not q:
        raise recruit.NotFound("Question not found")
    db.run("DELETE FROM screening_questions WHERE id=?", (qid,))
    db.log("Screening question removed", q["question"][:80], by, job_id=q["job_id"])


def suggest_questions(job_id: int) -> list[dict]:
    """Starter questions from the job's own requirements (no AI needed; AI can reword them)."""
    j = recruit.get_job(job_id)
    out = [{"question": f"Can you join within 30 days?", "kind": "yesno", "ideal": "Yes", "knockout": False},
           {"question": f"Are you willing to work in {j['location'].split(',')[0]}?", "kind": "yesno", "ideal": "Yes",
            "knockout": True},
           {"question": "Are you comfortable with rotational shifts, weekends and festive-season hours?",
            "kind": "yesno", "ideal": "Yes", "knockout": False},
           {"question": "What is your expected monthly salary (in rupees)?", "kind": "number", "ideal": None,
            "knockout": False}]
    if j["min_years"]:
        out.insert(0, {"question": "How many years of relevant experience do you have?", "kind": "number",
                       "ideal": f">= {j['min_years']:g}", "knockout": False})
    for s in j["must"][:2]:
        out.append({"question": f"Have you worked with {s} in a job?", "kind": "yesno", "ideal": "Yes",
                    "knockout": False})
    have = {q["question"].lower() for q in questions(job_id)}
    return [q for q in out if q["question"].lower() not in have]


def _passes(q: dict, ans: str | None) -> bool | None:
    if ans is None or str(ans).strip() == "" or not q.get("ideal"):
        return None
    a = str(ans).strip()
    if q["kind"] == "yesno":
        return a.lower() == q["ideal"].strip().lower()
    if q["kind"] == "number":
        try:
            v = float(re.sub(r"[^\d.]", "", a) or "nan")
        except ValueError:
            return None
        m = re.fullmatch(r"\s*(>=|<=)?\s*(\d+(?:\.\d+)?)\s*", q["ideal"])
        if not m:
            return None
        op, n = m.group(1) or ">=", float(m.group(2))
        return v >= n if op == ">=" else v <= n
    return None  # free text is for a human to read


def save_answers(app_id: int, answers: dict) -> dict:
    a = recruit.get_app(app_id)
    qs = {q["id"]: q for q in questions(a["job_id"])}
    rows = [(app_id, int(qid), str(v).strip()[:300], db.now()) for qid, v in answers.items() if int(qid) in qs]
    db.run_many("INSERT INTO screening_answers(application_id,question_id,answer,created_at) VALUES(?,?,?,?) "
                "ON CONFLICT(application_id,question_id) DO UPDATE SET answer=excluded.answer", rows)
    return answers_for(app_id)


def answers_for(app_id: int) -> dict:
    a = recruit.get_app(app_id)
    got = {r["question_id"]: r["answer"] for r in
           db.rows("SELECT question_id, answer FROM screening_answers WHERE application_id=?", (app_id,))}
    out, flags = [], 0
    for q in questions(a["job_id"]):
        ans = got.get(q["id"])
        ok = _passes(q, ans)
        if ok is False and q["knockout"]:
            flags += 1
        out.append({**q, "answer": ans, "ok": ok})
    return {"items": out, "answered": sum(1 for x in out if x["answer"] not in (None, "")),
            "knockout_flags": flags}


def job_knockouts(job_id: int) -> dict[int, int]:
    """candidate_id -> number of knockout questions answered the 'wrong' way (a flag, not a rejection)."""
    out = {}
    for a in db.rows("SELECT id, candidate_id FROM applications WHERE job_id=?", (job_id,)):
        n = answers_for(a["id"])["knockout_flags"]
        if n:
            out[a["candidate_id"]] = n
    return out


# =============================================================== 2. offer letters
def _rupees(n: int | None) -> str:
    if not n:
        return "—"
    s = str(int(n))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
    return f"₹{head},{tail}"


def _offer_template(o: dict, c: dict, j: dict) -> str:
    fn = c["name"].split()[0]
    jd = date.fromisoformat(o["joining_date"]) if o.get("joining_date") else None
    monthly = round((o["ctc"] or 0) / 12)
    return (
        f"Date: {date.today():%d %B %Y}\n\nDear {c['name']},\n\n"
        f"Subject: Offer of employment – {o['designation']}\n\n"
        f"We are pleased to offer you the position of {o['designation']} at our {o['location']} location, "
        f"reporting to the {o['reporting_to']}.\n\n"
        f"1. Compensation: Your annual cost to company (CTC) will be {_rupees(o['ctc'])} "
        f"(about {_rupees(monthly)} per month, before statutory deductions such as PF and ESI where they apply).\n"
        f"2. Joining date: {jd:%A, %d %B %Y}" + (".\n" if jd else ".\n") +
        f"3. Probation: {o['probation_months']} months, after which your role will be confirmed on satisfactory "
        "performance.\n"
        "4. Working hours: as per store roster, including weekends and festive-season shifts, with a weekly off.\n"
        "5. Documents to bring on day one: photo ID, PAN, Aadhaar, last 3 salary slips (if any), relieving letter "
        "(if any), 2 passport-size photos and bank details.\n\n"
        f"Please accept this offer in the candidate portal within 5 working days. If you have any questions, reply "
        f"to us there.\n\nWe look forward to welcoming you, {fn}.\n\nRegards,\nHR & Recruitment Team\n\n"
        "This letter was drafted with an AI tool and checked by a recruiter. It is a sample for a prototype "
        "(synthetic data) and is not a legal document.")


def draft_offer(app_id: int, ctc: int, joining_date: str, by: str, designation: str | None = None,
                reporting_to: str | None = None, probation_months: int = 6) -> dict:
    a = recruit.get_app(app_id)
    j, c = recruit.get_job(a["job_id"]), recruit.get_candidate(a["candidate_id"])
    if ctc <= 0:
        raise ExtraError("Enter the yearly CTC in rupees.")
    date.fromisoformat(joining_date)
    o = {"designation": designation or j["title"].split(" /")[0], "ctc": int(ctc), "joining_date": joining_date,
         "location": j["location"], "reporting_to": reporting_to or "Store Manager",
         "probation_months": int(probation_months)}
    letter = _offer_template(o, c, j)
    out = llm.generate(
        "Rewrite this offer letter so it reads warm and professional for a value-retail chain in India. Keep every "
        "number, date, name and the numbered points exactly as they are. Do not add any benefit, clause or figure "
        "that is not in it. Keep the last disclaimer paragraph. Plain text only.\n\n" + letter, max_tokens=900)
    if out and all(x in out for x in (_rupees(o["ctc"]), c["name"])):
        letter = out.strip()
    old = db.one("SELECT id FROM offers WHERE application_id=? AND status='Draft'", (app_id,))
    if old:
        db.run("UPDATE offers SET designation=?,ctc=?,joining_date=?,location=?,reporting_to=?,probation_months=?,"
               "letter=?,created_by=?,created_at=? WHERE id=?", (*o.values(), letter, by, db.now(), old["id"]))
        oid = old["id"]
    else:
        oid = db.run("INSERT INTO offers(application_id,designation,ctc,joining_date,location,reporting_to,"
                     "probation_months,letter,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (app_id, *o.values(), letter, "Draft", by, db.now()))
    db.log("Offer letter drafted", f"{o['designation']}, CTC {_rupees(o['ctc'])}", by, candidate_id=c["id"],
           job_id=j["id"], entity="offer", entity_id=oid)
    return {**get_offer(oid), "ai": bool(out)}


def get_offer(oid: int) -> dict:
    o = db.one("SELECT o.*, a.job_id, a.candidate_id, c.name candidate, j.title job_title FROM offers o "
               "JOIN applications a ON a.id=o.application_id JOIN candidates c ON c.id=a.candidate_id "
               "JOIN jobs j ON j.id=a.job_id WHERE o.id=?", (oid,))
    if not o:
        raise recruit.NotFound("Offer not found")
    o["ctc_text"] = _rupees(o["ctc"])
    return o


def offers_for(app_id: int | None = None, cid: int | None = None) -> list[dict]:
    sql, p = "SELECT o.id FROM offers o JOIN applications a ON a.id=o.application_id WHERE 1=1", []
    if app_id:
        sql += " AND o.application_id=?"
        p.append(app_id)
    if cid:
        sql += " AND a.candidate_id=?"
        p.append(cid)
    return [get_offer(r["id"]) for r in db.rows(sql + " ORDER BY o.id DESC", p)]


def update_offer_text(oid: int, letter: str) -> dict:
    o = get_offer(oid)
    if o["status"] != "Draft":
        raise ExtraError("This offer is already sent.")
    db.run("UPDATE offers SET letter=? WHERE id=?", (letter, oid))
    return get_offer(oid)


def send_offer(oid: int, by: str) -> dict:
    """Recruiter presses Send. The candidate sees it in the portal (Messages + My applications)."""
    o = get_offer(oid)
    if o["status"] != "Draft":
        return o
    db.run("UPDATE offers SET status='Sent', sent_at=? WHERE id=?", (db.now(), oid))
    db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at,sent_by,"
           "approved_by,approved_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
           (o["application_id"], "offer", "English", f"Your offer letter: {o['designation']}",
            o["letter"] + "\n\nOpen 'My applications' to accept or decline this offer.", "Sent", "out", db.now(),
            db.now(), by, by, db.now()))
    a = recruit.get_app(o["application_id"])
    if a["stage"] != "Selected":
        recruit.set_stage(a["id"], "Selected", by)
    db.log("Offer sent", f"{o['designation']}, {o['ctc_text']}", by, candidate_id=o["candidate_id"],
           job_id=o["job_id"], entity="offer", entity_id=oid)
    return get_offer(oid)


def respond_offer(cid: int, oid: int, response: str, note: str = "") -> dict:
    o = get_offer(oid)
    if o["candidate_id"] != cid or o["status"] == "Draft":
        raise ExtraError("Offer not found.")
    if response not in ("Accepted", "Declined"):
        raise ExtraError("Choose Accept or Decline.")
    if o["status"] in ("Accepted", "Declined"):
        raise ExtraError(f"You already {o['status'].lower()} this offer.")
    db.run("UPDATE offers SET status=?, candidate_note=?, responded_at=? WHERE id=?",
           (response, note.strip()[:500], db.now(), oid))
    body = (f"I accept the offer for {o['designation']}. I will join on {o['joining_date']}." if response == "Accepted"
            else f"I am declining the offer for {o['designation']}.") + (f"\n\n{note.strip()}" if note.strip() else "")
    db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at) "
           "VALUES(?,?,?,?,?,?,?,?,?)", (o["application_id"], "candidate", "English",
                                          f"Offer {response.lower()}: {o['designation']}", body, "Received", "in",
                                          db.now(), db.now()))
    db.log(f"Offer {response.lower()}", note[:80], o["candidate"], candidate_id=cid, job_id=o["job_id"],
           entity="offer", entity_id=oid)
    return get_offer(oid)


def offer_docx(oid: int) -> bytes:
    from docx import Document
    from docx.shared import Pt
    o = get_offer(oid)
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(11)
    d.add_heading("Offer of Employment", level=1)
    for para in o["letter"].split("\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# =============================================================== 3. WhatsApp
def _phone_digits(p: str | None) -> str | None:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 10:
        d = "91" + d
    return d if len(d) >= 11 else None


def whatsapp_for_email(eid: int) -> dict:
    """A short WhatsApp version of an email + a wa.me link the recruiter clicks (WhatsApp opens with the text ready)."""
    e = assist.get_email(eid)
    c = recruit.get_candidate(e["candidate_id"])
    fn = c["name"].split()[0]
    body = e["body"].split("\n\nRegards")[0]
    body = re.sub(r"^Dear [^,\n]+,\s*", "", body).strip()
    short = None
    out = llm.generate("Turn this recruitment email into a short WhatsApp message (max 60 words, plain text, friendly, "
                       "no emojis except one at most). Keep every date, time and place exactly. Do not add facts.\n\n"
                       + e["body"], max_tokens=200)
    if out and len(out) < 600:
        short = out.strip()
    if not short:
        if e["type"] == "offer":
            first = (f"Your offer letter for {e['job_title']} is ready. Please open My applications in your HireMate "
                     "portal to read it and accept or decline within 5 working days.")
        else:
            paras = [p for p in body.split("\n\n") if p.strip() and not p.lower().startswith(("date:", "subject:"))]
            first = " ".join(re.split(r"(?<=[.!?])\s+", " ".join(paras[:2]).replace("\n", " "))[:3])
        short = f"Hi {fn}, this is the Recruitment Team. {first} You can reply here or in your HireMate portal."
    digits = _phone_digits(c.get("phone"))
    return {"text": short, "phone": c.get("phone"), "link": f"https://wa.me/{digits}?text={urllib.parse.quote(short)}"
            if digits else None, "ai": bool(out)}


# =============================================================== 4. calendar invite
def ics(iid: int) -> bytes:
    from . import interviews
    iv = interviews.get(iid)
    start = datetime.strptime(f"{iv['date']} {iv['time']}", "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=45)
    f = "%Y%m%dT%H%M%S"
    esc = lambda s: str(s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HireMate//Interviews//EN", "CALSCALE:GREGORIAN",
             "METHOD:REQUEST", "BEGIN:VEVENT", f"UID:hiremate-interview-{iid}@hiremate.demo",
             f"DTSTAMP:{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}", f"DTSTART;TZID=Asia/Kolkata:{start:{f}}",
             f"DTEND;TZID=Asia/Kolkata:{end:{f}}", f"SUMMARY:{esc('Interview: ' + iv['job_title'] + ' – ' + iv['candidate'])}",
             f"LOCATION:{esc(iv['mode'])}",
             f"DESCRIPTION:{esc('Interviewer: ' + (iv['interviewer'] or '') + '. Bring a photo ID and your CV.')}",
             "BEGIN:VALARM", "TRIGGER:-PT60M", "ACTION:DISPLAY", "DESCRIPTION:Interview in 1 hour", "END:VALARM",
             "END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(lines) + "\r\n").encode()


# =============================================================== 5. source of hire, referrals, time metrics
def set_source(app_id: int, source: str, referred_by: str | None, by: str) -> dict:
    a = recruit.get_app(app_id)
    if source not in SOURCES:
        raise ExtraError(f"Source must be one of {', '.join(SOURCES)}")
    db.run("UPDATE applications SET source=?, referred_by=? WHERE id=?",
           (source, (referred_by or "").strip() or None if source == "Referral" else None, app_id))
    db.log("Source set", source + (f" (by {referred_by})" if referred_by else ""), by, candidate_id=a["candidate_id"],
           job_id=a["job_id"], entity="application", entity_id=app_id)
    return recruit.get_app(app_id)


def _stage_times(app_id: int, created: str) -> dict:
    """When the application first reached each stage (from the activity log)."""
    out = {"Applied": _ts(created)}
    for r in db.rows("SELECT a.detail, a.created_at FROM activity_logs a JOIN applications p "
                     "ON p.job_id=a.job_id AND p.candidate_id=a.candidate_id WHERE p.id=? AND a.action='Stage changed' "
                     "ORDER BY a.id", (app_id,)):
        to = r["detail"].split("→")[-1].strip()
        out.setdefault(to, _ts(r["created_at"]))
    return out


def metrics() -> dict:
    apps = db.rows("SELECT a.*, j.title FROM applications a JOIN jobs j ON j.id=a.job_id")
    by_source: dict[str, dict] = {}
    t2h, t2i, stage_days = [], [], {"Applied": [], "Screening": [], "Shortlisted": [], "Interview": []}
    flow = ["Applied", "Screening", "Shortlisted", "Interview", "Selected"]
    for a in apps:
        s = a.get("source") or "Recruiter upload"
        d = by_source.setdefault(s, {"source": s, "applications": 0, "shortlisted": 0, "hired": 0})
        d["applications"] += 1
        d["shortlisted"] += a["stage"] in ("Shortlisted", "Interview", "Selected")
        d["hired"] += a["stage"] == "Selected"
        t = _stage_times(a["id"], a["created_at"])
        if t.get("Selected") and t.get("Applied"):
            t2h.append((t["Selected"] - t["Applied"]).total_seconds() / 86400)
        if t.get("Interview") and t.get("Applied"):
            t2i.append((t["Interview"] - t["Applied"]).total_seconds() / 86400)
        reached = [s_ for s_ in flow if t.get(s_)]
        for i, s_ in enumerate(reached[:-1]):
            if s_ in stage_days:
                stage_days[s_].append((t[reached[i + 1]] - t[s_]).total_seconds() / 86400)
        if a["stage"] in stage_days and t.get(a["stage"]):
            stage_days[a["stage"]].append((datetime.now() - t[a["stage"]]).total_seconds() / 86400)
    for d in by_source.values():
        d["quality"] = round(d["shortlisted"] / d["applications"] * 100) if d["applications"] else 0
    offers = db.rows("SELECT status FROM offers")
    decided = [o for o in offers if o["status"] in ("Accepted", "Declined")]
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    jobs_open = [{"job": j["short"], "days_open": max(0, (datetime.now() - (_ts(j["created_at"]) or datetime.now())).days)}
                 for j in recruit.list_jobs(status="Open")]
    referrals = db.rows("SELECT a.referred_by, c.name, j.title, a.stage FROM applications a JOIN candidates c "
                        "ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id WHERE a.source='Referral'")
    return {"by_source": sorted(by_source.values(), key=lambda x: -x["applications"]),
            "time_to_hire_days": avg(t2h), "time_to_interview_days": avg(t2i),
            "days_in_stage": [{"stage": s, "days": avg(v) or 0} for s, v in stage_days.items()],
            "offers": {"sent": sum(o["status"] != "Draft" for o in offers),
                       "accepted": sum(o["status"] == "Accepted" for o in offers),
                       "declined": sum(o["status"] == "Declined" for o in offers),
                       "acceptance_rate": round(sum(o["status"] == "Accepted" for o in decided) / len(decided) * 100)
                       if decided else None},
            "jobs_open": jobs_open, "referrals": referrals}


# =============================================================== 6. CSV export
def job_csv(job_id: int) -> bytes:
    j = recruit.get_job(job_id)
    ranked = recruit.compute_job(job_id)
    ko = job_knockouts(job_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Rank", "Name", "Email", "Phone", "City", "Years", "Stage", "Match %", "Skills", "CV text", "Experience",
                "Has (must-have)", "Missing (must-have)", "Source", "Knockout flags"])
    for i, r in enumerate(ranked, 1):
        c = recruit.get_candidate(r["candidate_id"])
        a = recruit.app_for(job_id, r["candidate_id"]) or {}
        must = [x for x in r["rows"] if x.get("must")]
        w.writerow([i, c["name"], c.get("email"), c.get("phone"), c.get("location"), c.get("years"), r["stage"],
                    r["score"], r["skill_score"], r["text_score"], r["exp_score"],
                    "; ".join(x["skill"] for x in must if x["status"] != "Missing"),
                    "; ".join(x["skill"] for x in must if x["status"] == "Missing"),
                    a.get("source") or "", ko.get(r["candidate_id"], 0)])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM so Excel shows ₹ and Hindi names correctly


# =============================================================== 7. privacy (DPDP Act 2023)
def record_consent(cid: int) -> None:
    db.run("UPDATE candidates SET consent_at=COALESCE(consent_at, ?) WHERE id=?", (db.now(), cid))


def erase_candidate(cid: int, by: str) -> dict:
    """Right to erasure: remove the person's CV, contact details, answers and messages. Numbers in reports stay
    (the application row is kept, anonymised) so funnel counts don't change."""
    c = recruit.get_candidate(cid)
    db.run("UPDATE candidates SET name=?, email=NULL, phone=NULL, location=NULL, headline='(erased)', summary='', "
           "education='', roles_json='[]', cv_text='(erased on request)', file_name=NULL, anonymised_at=? WHERE id=?",
           (f"Erased candidate #{cid}", db.now(), cid))
    db.run("DELETE FROM candidate_skills WHERE candidate_id=?", (cid,))
    db.run("DELETE FROM candidate_accounts WHERE candidate_id=?", (cid,))
    db.run("DELETE FROM notes WHERE candidate_id=?", (cid,))
    db.run("DELETE FROM screening_answers WHERE application_id IN (SELECT id FROM applications WHERE candidate_id=?)",
           (cid,))
    db.run("UPDATE emails SET subject='(erased)', body='(erased)' WHERE application_id IN "
           "(SELECT id FROM applications WHERE candidate_id=?)", (cid,))
    db.run("UPDATE activity_logs SET detail='(erased)' WHERE candidate_id=?", (cid,))
    try:
        from ..adapters.vectorstore import get_store
        get_store().delete(f"cand:{cid}")
    except Exception:  # noqa: BLE001
        pass
    db.log("Candidate data erased", "DPDP request", by, candidate_id=cid, entity="candidate", entity_id=cid)
    return {"ok": True, "was": c["name"]}


def privacy_status(days: int = 180) -> dict:
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = db.rows("SELECT c.id, c.name, c.created_at, c.consent_at, MAX(COALESCE(a.updated_at, c.created_at)) last "
                   "FROM candidates c LEFT JOIN applications a ON a.candidate_id=c.id WHERE c.anonymised_at IS NULL "
                   "GROUP BY c.id")
    hired = {r["candidate_id"] for r in db.rows("SELECT candidate_id FROM applications WHERE stage='Selected'")}
    old = [r for r in rows if (r["last"] or "") < cut and r["id"] not in hired]
    return {"days": days, "total": len(rows), "with_consent": sum(1 for r in rows if r["consent_at"]),
            "erased": db.one("SELECT COUNT(*) n FROM candidates WHERE anonymised_at IS NOT NULL")["n"],
            "due": [{"id": r["id"], "name": r["name"], "last_activity": (r["last"] or "")[:10]} for r in old]}


def purge_old(days: int, by: str) -> dict:
    due = privacy_status(days)["due"]
    for r in due:
        erase_candidate(r["id"], by)
    return {"erased": len(due)}


# =============================================================== demo data for the new features
def seed(job_ids: dict, cand_ids: dict, apps: dict) -> None:
    """Called from seed.reset_and_seed: questions, answers, sources, realistic dates."""
    for jk, jid in job_ids.items():
        for q in suggest_questions(jid)[:4]:
            add_question(jid, q["question"], q["kind"], q["ideal"], q["knockout"], "Seed")
    src = {("sm", "c1"): ("Referral", "Employee referral (Store Manager, Noida store)"), ("sm", "c2"): ("Naukri", None),
           ("sm", "c4"): ("Candidate portal", None), ("sm", "c5"): ("LinkedIn", None), ("ca", "c3"): ("Walk-in", None),
           ("ca", "c2"): ("Talent pool", None), ("ca", "c7"): ("Apna", None), ("wh", "c6"): ("Referral",
                                                                                          "Employee referral (DC Supervisor)"),
           ("wh", "c4"): ("Candidate portal", None)}
    for k, aid in apps.items():
        s, ref = src.get(k, ("Recruiter upload", None))
        db.run("UPDATE applications SET source=?, referred_by=? WHERE id=?", (s, ref, aid))
    # spread history over the last few weeks so time-in-stage reports have something real to show
    back = {("sm", "c1"): 12, ("sm", "c2"): 9, ("sm", "c5"): 8, ("ca", "c3"): 15, ("wh", "c6"): 11, ("ca", "c2"): 2,
            ("ca", "c7"): 1}
    for k, days in back.items():
        aid = apps[k]
        t0 = datetime.now() - timedelta(days=days)
        db.run("UPDATE applications SET created_at=? WHERE id=?", (t0.strftime("%Y-%m-%d %H:%M:%S"), aid))
        a = recruit.get_app(aid)
        logs = db.rows("SELECT id FROM activity_logs WHERE action='Stage changed' AND job_id=? AND candidate_id=? "
                       "ORDER BY id", (a["job_id"], a["candidate_id"]))
        for i, lg in enumerate(logs, 1):
            t = t0 + timedelta(days=days * i / (len(logs) + 1))
            db.run("UPDATE activity_logs SET created_at=? WHERE id=?", (t.strftime("%Y-%m-%d %H:%M:%S"), lg["id"]))
    for jk, jid in job_ids.items():
        db.run("UPDATE jobs SET created_at=? WHERE id=?",
               ((datetime.now() - timedelta(days={"sm": 18, "ca": 21, "wh": 14}.get(jk, 10))).strftime(
                   "%Y-%m-%d %H:%M:%S"), jid))
    # sample screening answers (one person trips a knockout question, to show the flag)
    for k, aid in apps.items():
        qs = questions(recruit.get_app(aid)["job_id"])
        ans = {}
        for q in qs:
            if q["kind"] == "yesno":
                ans[q["id"]] = "No" if (k == ("sm", "c4") and q["knockout"]) else "Yes"
            elif q["kind"] == "number":
                yrs = recruit.get_candidate(recruit.get_app(aid)["candidate_id"])["years"]
                ans[q["id"]] = f"{yrs:g}" if "experience" in q["question"] else "22000"
        save_answers(aid, ans)
    for cid in cand_ids.values():
        record_consent(cid)
