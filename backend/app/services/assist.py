"""AI writing tasks: candidate summary, interview questions, assessment, feedback summary, emails.

Each task builds a grounded prompt from database facts. If no LLM is available (or it fails),
a template version is returned, so every feature works offline. `ai` in the result says which.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from .. import db
from ..adapters import llm
from . import recruit

EMAIL_TYPES = {"invite": "Interview invitation", "reminder": "Interview reminder", "followup": "Follow-up",
               "assessment": "Assessment instructions", "selection": "Selection", "rejection": "Rejection"}
ALL_TYPES = {**EMAIL_TYPES, "reply": "Reply", "candidate": "Message from candidate"}
AI_LINE = "This email was drafted with an AI tool and checked by our recruiter."
AI_LINE_HI = "यह ईमेल एक AI टूल की मदद से लिखा गया और हमारे रिक्रूटर ने जाँचा है।"


def _ctx(job_id: int, cid: int):
    j = recruit.get_job(job_id)
    c = recruit.get_candidate(cid)
    m = recruit.match_one(job_id, cid)
    return j, c, m


def match_brief(j: dict, c: dict, m: dict) -> str:
    return (f"Score {m['score']}% (skills {m['skill_score']}%, text match {m['text_score']}%, experience {m['exp_score']}%). "
            f"Years: {c['years']:g} (job asks {j['min_years']:g}+). "
            + "; ".join(f"{r['skill']} [{'must' if r['must'] else 'nice'}]: {r['status']}" for r in m["rows"])
            + (". " + "; ".join(f"Recruiter criterion '{x['text']}' ({x['kind']}): {x['status']}"
                                + (f" — CV: {x['evidence']}" if x["evidence"] else "") for x in m.get("criteria", []))
               if m.get("criteria") else ""))


def fmt_when(iv: dict | None) -> str:
    if not iv:
        return "[date and time]"
    try:
        d = datetime.strptime(f"{iv['date']} {iv['time']}", "%Y-%m-%d %H:%M")
        return d.strftime("%a %d %b %Y at %I:%M %p").replace(" 0", " ")
    except ValueError:
        return f"{iv['date']} {iv['time']}"


def latest_interview(app_id: int) -> dict | None:
    return db.one("SELECT * FROM interviews WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))


# ---------------------------------------------------------------- summary
def summary(job_id: int, cid: int) -> dict:
    j, c, m = _ctx(job_id, cid)
    proven = [r["skill"] for r in m["rows"] if r["status"] == "Proven"]
    gaps = [r["skill"] for r in m["rows"] if r["status"] == "Missing"]
    tmpl = "\n".join([
        f"- **Strengths:** {', '.join(proven[:4]) or 'none proven yet'}",
        f"- **Experience:** {c['headline']}, {c['years']:g} years in total",
        f"- **Gaps:** {', '.join(gaps[:3]) or 'no missing skills'}",
        f"- **Fit:** {m['score']}% match for {j['title']}; "
        f"{'meets' if m['meets_years'] else 'below'} the {j['min_years']:g}+ years asked"])
    out = llm.generate(
        "You are a helpful recruiting assistant. Write a short candidate summary for a retail HR manager in very simple words. "
        "Use ONLY the CV and match data below. Output EXACTLY 5 lines in this markdown format, one per line, nothing else:\n"
        "- **Verdict:** one clear sentence (should we move this person forward, and why)\n"
        "- **Strengths:** 2 or 3 skills with proof from the CV\n"
        "- **Experience:** the most relevant job, place and time\n"
        "- **Gaps:** missing skills, or 'None'\n"
        "- **Next step:** one action for the recruiter\n"
        "Each line under 25 words. No brackets, no source tags, no numbers like 'Match data'.\n\n"
        f"JOB:\n{j['description']}\n\nCV:\n{c['cv_text'][:2500]}\n\nMATCH DATA:\n{match_brief(j, c, m)}", max_tokens=400)
    if out:   # make sure every point is on its own line, even if the AI used '•' on one line
        out = re.sub(r"\s*[•●]\s*", "\n- ", out).strip()
        out = re.sub(r"(?<!\n)\s+(?=- \*\*)", "\n", out)
        out = re.sub(r"\n{2,}", "\n", out)
    return {"text": out or tmpl, "ai": bool(out)}


# ---------------------------------------------------------------- questions
def questions(job_id: int, cid: int) -> dict:
    j, c, m = _ctx(job_id, cid)
    proven = [r for r in m["rows"] if r["status"] == "Proven"]
    missing = [r for r in m["rows"] if r["status"] == "Missing"]
    tmpl = [{"type": "Technical", "skill": s, "question": f"Walk me through how you handle {s.lower()} on a busy day.",
             "follow_up": "What would you do differently next time?",
             "good_answer": "A specific example with numbers and the result."} for s in j["must"][:2]]
    tmpl.append({"type": "HR", "skill": "Teamwork",
                 "question": "Tell me about a time two people in your team disagreed. What did you do?",
                 "follow_up": "How did it end?", "good_answer": "Listens to both sides, acts fairly, follows up."})
    tmpl += [{"type": "Verification", "skill": r["skill"], "question": f"Your CV says \"{r['evidence']}\" How did you do it?",
              "follow_up": "What was the result, in numbers?",
              "good_answer": "Clear steps, their own part, and how they measured it."} for r in proven[:2]]
    tmpl += [{"type": "Gap-probing", "skill": r["skill"],
              "question": f"This role needs {r['skill'].lower()}. How would you learn it in your first month?",
              "follow_up": "Have you done anything close to this?",
              "good_answer": "A realistic plan: who to learn from, what to practise, how to check progress."}
             for r in missing[:1]]
    # one question for each recruiter criterion that isn't clearly met
    tmpl += [{"type": "Criteria", "skill": x["text"][:40],
              "question": f"We look for this in the role: {x['text'].rstrip('.')}. Can you give an example from your work?",
              "follow_up": "What was your part, and the result?",
              "good_answer": "A specific, recent example that shows it clearly."}
             for x in m.get("criteria", []) if x["status"] in ("not met", "unclear", "partly")
             and x["check"] in ("custom", "skill", "keyword")][:2]
    out = llm.generate_json(
        f"Create 6 interview questions for a {j['title']} candidate at a value-retail chain in India. Use ONLY the data "
        "below. Rules: 2 'Technical' from the job's must-have skills; 1 'HR' (behavioural); 2 'Verification' that check "
        "a specific proven-skill sentence from the CV; 1 'Gap-probing' about a missing skill (if none, a third "
        "Verification). If the match data lists recruiter criteria that are not clearly met, add one 'Criteria' "
        "question for each (max 2). Return a JSON array of 6 to 8 objects with keys type, skill, question (<30 words), "
        "follow_up (<20 words), good_answer (<25 words).\n\n"
        f"JOB:\n{j['description']}\n\nCV:\n{c['cv_text'][:2500]}\n\nMATCH DATA:\n{match_brief(j, c, m)}")
    ok = isinstance(out, list) and all(isinstance(q, dict) and "question" in q for q in out)
    qs = out if ok else tmpl
    a = recruit.app_for(job_id, cid)
    if a:
        iv = latest_interview(a["id"])
        if iv:
            db.run("UPDATE interviews SET questions_json=? WHERE id=?", (json.dumps(qs), iv["id"]))
        db.log("Interview questions generated", "", "AI", candidate_id=cid, job_id=job_id)
    return {"questions": qs, "ai": ok}


# ---------------------------------------------------------------- assessment
ASSESS = {
    "Store management": "Task: Plan staffing and stock for a festive weekend in a 15,000 sq ft store.\n"
                        "Deliverable: a 2-page plan (shift roster, billing counters, stock top-ups).\nTime: 3 days.\n"
                        "Scored on: realistic numbers, customer flow, cost awareness.\n"
                        "Instructions:\n• Use the store size and team size from the job description.\n• State your assumptions.",
    "Cashier & customer service": "Task: Billing accuracy test at the store.\n"
                                  "Deliverable: bill 25 mixed baskets on the POS, including UPI, card and cash.\n"
                                  "Time: 15 minutes.\nScored on: accuracy, speed, correct change.\n"
                                  "Instructions:\n• Bring a photo ID.\n• A trainer will play the customer.",
    "Warehouse & logistics": "Task: Plan tomorrow's dispatch to 12 stores with 2 trucks.\n"
                             "Deliverable: a one-page loading plan and pick list order.\nTime: 2 days.\n"
                             "Scored on: on-time delivery, truck use, safety steps.\n"
                             "Instructions:\n• Assume each truck makes two trips.\n• Show your safety checks.",
}


def assessment(job_id: int, cid: int | None = None) -> dict:
    j = recruit.get_job(job_id)
    from ..core.ml import job_family
    fam = job_family(j["description"])[0][0]
    tmpl = ASSESS.get(fam, f"Task: A short case on {', '.join(j['must'][:2])}.\nDeliverable: a one-page answer.\n"
                           "Time: 2 days.\nScored on: clarity, realistic steps.")
    out = llm.generate(
        f"Write a short take-home assessment for a {j['title']} candidate at a value-retail chain in India. "
        f"Base it on these must-have skills: {', '.join(j['must'])}. Plain text with these lines: Task, Deliverable, "
        "Time, Scored on, Instructions (2 short bullets). Under 120 words.")
    text = out or tmpl
    if cid:
        a = recruit.app_for(job_id, cid)
        iv = latest_interview(a["id"]) if a else None
        if iv:
            db.run("UPDATE interviews SET assessment=? WHERE id=?", (text, iv["id"]))
    return {"text": text, "ai": bool(out)}


# ---------------------------------------------------------------- feedback
def readiness(job_id: int, cid: int, scores: dict) -> int | None:
    v = [int(x) for x in scores.values() if x]
    if not v:
        return None
    return round(0.5 * recruit.match_one(job_id, cid)["score"] + 0.5 * (sum(v) / len(v)) * 20)


def feedback_summary(app_id: int) -> dict:
    a = recruit.get_app(app_id)
    fb = db.one("SELECT * FROM interview_feedback WHERE application_id=? ORDER BY id DESC LIMIT 1", (app_id,))
    if not fb:
        return {"text": "No feedback yet.", "ai": False}
    sc = json.loads(fb["scores_json"] or "{}")
    r = readiness(a["job_id"], a["candidate_id"], sc)
    tmpl = "\n".join([
        f"• Strengths: {', '.join(k for k, v in sc.items() if v >= 4) or 'see notes'}",
        f"• Concerns: {', '.join(k for k, v in sc.items() if v <= 2) or 'none from ratings'}",
        f"• Recommendation: {'Interviewer recommends selection' if 'recommend' in (fb['text'] or '').lower() else 'Recruiter to decide'}"
        f" (readiness {r if r is not None else '—'}%)"])
    out = llm.generate(
        "Summarize this interview feedback for a recruiter in 3 short bullets starting with '• ': Strengths, Concerns, "
        f"Recommendation. Use only this data.\nRatings (1-5): {', '.join(f'{k} {v}' for k, v in sc.items()) or 'none'}\n"
        f"Feedback by {fb['by_name'] or 'interviewer'}: {fb['text'] or 'none'}\nReadiness: {r}%")
    text = out or tmpl
    db.run("UPDATE interview_feedback SET ai_summary=?, readiness=? WHERE id=?", (text, r, fb["id"]))
    return {"text": text, "ai": bool(out), "readiness": r}


# ---------------------------------------------------------------- emails
def _email_template(t: str, j: dict, c: dict, iv: dict | None, lang: str) -> tuple[str, str]:
    fn = c["name"].split()[0]
    when = fmt_when(iv)
    mode = f", {iv['mode'].lower()}" if iv and iv.get("mode") else ""
    who = f", with the {iv['interviewer']}" if iv and iv.get("interviewer") else ""
    if lang == "Hindi":
        hi = {
            "invite": (f"{j['title']} के लिए इंटरव्यू",
                       f"प्रिय {fn},\n\n{j['title']} ({j['location']}) के लिए आवेदन करने के लिए धन्यवाद। हम आपको {when} को इंटरव्यू के लिए बुलाना चाहते हैं।\n\nकृपया फोटो ID और अपना CV साथ लाएँ। पुष्टि के लिए इस ईमेल का जवाब दें।"),
            "reminder": (f"याद दिलाना: {when} को आपका इंटरव्यू",
                         f"प्रिय {fn},\n\n{j['title']} के लिए आपका इंटरव्यू {when} को है। कृपया 10 मिनट पहले फोटो ID के साथ पहुँचें।"),
            "followup": (f"{j['title']} के आवेदन पर अपडेट",
                         f"प्रिय {fn},\n\nआपके धैर्य के लिए धन्यवाद। आपका आवेदन अभी समीक्षा में है। हम 3 कार्य दिवसों में अपडेट देंगे।"),
            "assessment": (f"{j['title']}: अगला कदम",
                           f"प्रिय {fn},\n\nइंटरव्यू के लिए धन्यवाद। अगले कदम के रूप में कृपया 3 दिनों में एक छोटा असेसमेंट पूरा करें।"),
            "selection": (f"{j['title']} के लिए आपका चयन हुआ है",
                          f"प्रिय {fn},\n\nहमें खुशी है कि {j['title']} ({j['location']}) के लिए आपका चयन हुआ है। HR जल्द ही ऑफर लेटर भेजेगा।"),
            "rejection": (f"{j['title']} के लिए आपका आवेदन",
                          f"प्रिय {fn},\n\n{j['title']} में रुचि के लिए धन्यवाद। इस बार हम आगे नहीं बढ़ रहे हैं। हम आपकी प्रोफ़ाइल भविष्य के लिए रखेंगे।"),
        }[t]
        return hi[0], hi[1] + f"\n\nसादर,\nरिक्रूटमेंट टीम\n\n{AI_LINE_HI}"
    en = {
        "invite": (f"Interview for {j['title']}",
                   f"Dear {fn},\n\nThank you for applying for the {j['title']} role ({j['location']}). We would like to invite "
                   f"you to an interview on {when}{mode}{who}.\n\nPlease bring a photo ID and a copy of your CV. Reply to "
                   "confirm, or to ask for another slot. You can reschedule once with 24 hours' notice."),
        "reminder": (f"Reminder: your interview on {when}",
                     f"Dear {fn},\n\nThis is a reminder of your interview for the {j['title']} role on {when}{mode}. "
                     "Please arrive 10 minutes early with a photo ID."),
        "followup": (f"Following up on your application for {j['title']}",
                     f"Dear {fn},\n\nThank you for your patience. Your application for the {j['title']} role is still under "
                     "review, and we will update you within 3 working days."),
        "assessment": (f"Next step for {j['title']}: short assessment",
                       f"Dear {fn},\n\nThank you for the interview. As the next step, please complete a short assessment "
                       f"within 3 days and reply to this email with your answer.\n\n{(iv or {}).get('assessment') or ''}".rstrip()),
        "selection": (f"You have been selected for {j['title']}",
                      f"Dear {fn},\n\nWe are happy to tell you that you have been selected for the {j['title']} role "
                      f"({j['location']}). HR will share the offer letter with salary and joining details shortly."),
        "rejection": (f"Your application for {j['title']}",
                      f"Dear {fn},\n\nThank you for your interest in the {j['title']} role. We will not be moving forward "
                      "at this stage, and we will keep your profile for future store roles."),
    }[t]
    return en[0], en[1] + f"\n\nRegards,\nRecruitment Team\n\n{AI_LINE}"


def draft_email(job_id: int, cid: int, etype: str, lang: str = "English", by: str = "Recruiter") -> dict:
    if etype not in EMAIL_TYPES:
        raise ValueError(f"Email type must be one of {', '.join(EMAIL_TYPES)}")
    j = recruit.get_job(job_id)
    c = recruit.get_candidate(cid)
    a = recruit.app_for(job_id, cid) or recruit.apply(job_id, cid, by)
    iv = latest_interview(a["id"])
    subj, body = _email_template(etype, j, c, iv, lang)
    policy = db.one("SELECT text FROM knowledge_docs WHERE title LIKE '%Reschedule%'")
    out = llm.generate(
        f"Write a '{EMAIL_TYPES[etype]}' email from the recruitment team of a value-retail chain in India to a candidate. "
        f"Language: {lang}{' (Devanagari script, simple everyday words)' if lang == 'Hindi' else ''}. Plain text. "
        "First line 'Subject: ...', then a blank line, then the body. Under 140 words, warm and clear. Use only these "
        "facts; do not invent salary, dates or names. End with one line saying the email was drafted with an AI tool "
        "and checked by a recruiter.\n\n"
        f"Candidate: {c['name']}\nRole: {j['title']}, {j['location']}\nStage: {a['stage']}\n"
        f"Interview: {fmt_when(iv) + ', ' + (iv['mode'] or '') + ', with ' + (iv['interviewer'] or '') if iv else 'not scheduled'}\n"
        f"Assessment: {(iv or {}).get('assessment') or 'none'}\nReschedule policy: {policy['text'] if policy else 'n/a'}")
    if out and out.lower().startswith("subject:"):
        first, _, rest = out.partition("\n")
        subj, body = first.split(":", 1)[1].strip(), rest.strip()
    eid = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,created_at) VALUES(?,?,?,?,?,?,?)",
                 (a["id"], etype, lang, subj, body, "Draft", db.now()))
    db.log("Email drafted", f"{EMAIL_TYPES[etype]} ({lang})", by, candidate_id=cid, job_id=job_id, entity="email",
           entity_id=eid)
    return {**get_email(eid), "ai": bool(out)}


def get_email(eid: int) -> dict:
    e = db.one("SELECT e.*, a.job_id, a.candidate_id, c.name candidate, c.email to_email, j.title job_title "
               "FROM emails e JOIN applications a ON a.id=e.application_id JOIN candidates c ON c.id=a.candidate_id "
               "JOIN jobs j ON j.id=a.job_id WHERE e.id=?", (eid,))
    if not e:
        raise recruit.NotFound("Email not found")
    e["type_label"] = ALL_TYPES.get(e["type"], e["type"])
    e["direction"] = e.get("direction") or "out"
    return e


def update_email(eid: int, subject: str | None, body: str | None) -> dict:
    e = get_email(eid)
    if e["status"] == "Approved":
        raise ValueError("This email is already approved.")
    db.run("UPDATE emails SET subject=COALESCE(?,subject), body=COALESCE(?,body) WHERE id=?", (subject, body, eid))
    return get_email(eid)


def send_email(eid: int, by: str) -> dict:
    """The recruiter presses Send. The email goes to the candidate's portal inbox
    (and to their real inbox too if SMTP is set up in .env). AI never sends on its own."""
    e = get_email(eid)
    if e["direction"] != "out":
        raise ValueError("This is a message from the candidate, it can't be sent.")
    if e["status"] == "Sent":
        return e
    db.run("UPDATE emails SET status='Sent', sent_at=?, sent_by=?, approved_by=?, approved_at=? WHERE id=?",
           (db.now(), by, by, db.now(), eid))
    from . import mailer
    real = mailer.send(e["to_email"], e["subject"], e["body"])
    db.log("Email sent", f"{e['type_label']} to {e['candidate']}" + (" (also by email)" if real else ""), by,
           candidate_id=e["candidate_id"], job_id=e["job_id"], entity="email", entity_id=eid)
    return {**get_email(eid), "real_email": real}


approve_email = send_email  # old name, kept so older screens and the assistant keep working


def mark_read(eid: int) -> None:
    db.run("UPDATE emails SET read_at=COALESCE(read_at, ?) WHERE id=?", (db.now(), eid))


def inbox(unread_only: bool = True) -> list[dict]:
    """Messages from candidates (replies, interview confirmations, reschedule requests)."""
    sql = "SELECT id FROM emails WHERE direction='in'" + (" AND read_at IS NULL" if unread_only else "")
    return [get_email(r["id"]) for r in db.rows(sql + " ORDER BY id DESC")]


def thread(app_id: int) -> list[dict]:
    """Every sent / received message for one person and one job, oldest first (drafts excluded)."""
    return [get_email(r["id"]) for r in db.rows(
        "SELECT id FROM emails WHERE application_id=? AND status!='Draft' ORDER BY COALESCE(sent_at, created_at), id",
        (app_id,))]


def draft_reply(eid: int, by: str) -> dict:
    """AI drafts a reply to a candidate's message, using the job, the interview and the policies. Saved as Draft."""
    m = get_email(eid)
    if m["direction"] != "in":
        raise ValueError("Pick a message from the candidate to reply to.")
    j = recruit.get_job(m["job_id"])
    a = recruit.app_for(m["job_id"], m["candidate_id"])
    iv = latest_interview(a["id"]) if a else None
    policy = "\n".join(d["text"][:600] for d in db.rows(
        "SELECT text FROM knowledge_docs WHERE type IN ('Policy','FAQ') ORDER BY id LIMIT 4"))
    fn = m["candidate"].split()[0]
    subj = m["subject"] if m["subject"].lower().startswith("re:") else f"Re: {m['subject']}"
    body = (f"Dear {fn},\n\nThank you for your message about the {j['title']} role. We have noted it and will get back "
            f"to you within 2 working days.\n\nRegards,\nRecruitment Team\n\n{AI_LINE}")
    out = llm.generate(
        "Write a short, warm reply from a retail recruitment team to this candidate message. Plain text body only "
        "(no subject line), under 120 words. Use only the facts below; if the candidate asks for something the policy "
        "does not allow, say so kindly. Do not promise anything not in the facts. End with 'Regards, Recruitment Team' "
        "and one line saying the email was drafted with an AI tool and checked by a recruiter.\n\n"
        f"Candidate: {m['candidate']}\nRole: {j['title']}, {j['location']}\nStage: {a['stage'] if a else '-'}\n"
        f"Interview: {fmt_when(iv) + ', ' + (iv.get('mode') or '') if iv else 'not scheduled'}\n"
        f"Policies:\n{policy}\n\nCandidate's message:\n{m['body']}")
    if out:
        body = out
    new = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,parent_id,created_at) "
                 "VALUES(?,?,?,?,?,?,?,?,?)", (m["application_id"], "reply", "English", subj, body, "Draft", "out", eid, db.now()))
    mark_read(eid)
    db.log("Email drafted", "Reply to candidate", by, candidate_id=m["candidate_id"], job_id=m["job_id"], entity="email",
           entity_id=new)
    return {**get_email(new), "ai": bool(out)}


def list_emails(cid: int | None = None, job_id: int | None = None, status: str | None = None) -> list[dict]:
    sql = ("SELECT e.id FROM emails e JOIN applications a ON a.id=e.application_id WHERE 1=1")
    if status == "Approved":
        status = "Sent"
    p: list = []
    if cid:
        sql += " AND a.candidate_id=?"
        p.append(cid)
    if job_id:
        sql += " AND a.job_id=?"
        p.append(job_id)
    if status:
        sql += " AND e.status=?"
        p.append(status)
    return [get_email(r["id"]) for r in db.rows(sql + " ORDER BY e.id DESC", p)]
