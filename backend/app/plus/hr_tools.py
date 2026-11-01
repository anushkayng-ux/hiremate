"""HireMate Plus: tools for HR's daily work.

18 Job post writer for each site   28 Live interview helper        33 Bulk update, personal touch
19 Interview notes to scorecard    29 Panel agreement check        34 Decision journal
21 Question bank that learns       30 Role-play scenario generator 35 Blind first look
22 Hindi CV reading                31 Tone switch for emails
23 Recruiter performance           32 Candidate question auto-answer
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from .. import db
from . import lc
from ..adapters import llm
from ..core.skills import skill_regex
from ..services import assist, recruit

# =========================================================== 18. job post writer
SITES = ["Naukri", "LinkedIn", "Apna", "WhatsApp"]


def job_posts(job_id: int) -> dict:
    j = recruit.get_job(job_id)
    from .insights import pay_band
    lo, hi = pay_band(j)
    title, loc = j["title"], j["location"]
    must, nice = ", ".join(j["must"]), ", ".join(j["nice"])
    yrs = f"{j['min_years']:g}+ years" if j["min_years"] else "Freshers welcome"
    pay = f"₹{lo:,}–₹{hi:,} a month"
    posts = {
        "Naukri": (f"{title} | {loc}\n\nExperience: {yrs}\nSalary: {pay}\nQualification: {j['qualification'] or 'Any'}\n\n"
                   f"Key skills: {must}\nGood to have: {nice or '—'}\n\nAbout the role:\n"
                   + "\n".join(f"• {x.strip(' -•')}" for x in j["description"].splitlines() if x.strip().startswith(("-", "•")))[:900]
                   + "\n\nApply on our careers portal. Shortlisted candidates will be called within 3 working days."),
        "LinkedIn": (f"We're hiring: {title} in {loc.split(',')[0]} 🛒\n\nIf you're great at {lc(must)}, we'd love to "
                     f"meet you. {yrs}. {pay}.\n\nWhat you'll do: run a busy, friendly store floor where every customer "
                     f"leaves happy.\n\nApply through our careers portal or comment 'interested'.\n\n"
                     f"#hiring #retailjobs #{re.sub(r'[^A-Za-z]', '', title.split('/')[0])} #{loc.split(',')[0].replace(' ', '')}jobs"),
        "Apna": (f"{title} ki naukri – {loc}\n\nSalary: {pay}\nExperience: {yrs}\nZaroori skills: {must}\n"
                 f"Timing: store roster, 1 weekly off\nDocuments: Aadhaar, PAN, bank passbook\n\n"
                 "Apply karein ya HR ko call karein. Interview isi hafte."),
        "WhatsApp": (f"*Job opening: {title}*\n📍 {loc}\n💰 {pay}\n🧾 {yrs}\n✅ Skills: {must}\n\n"
                     "Interested? Reply *YES* with your name and area, or apply on our careers portal. Please share with friends!"),
    }
    out = llm.generate_json("Improve these 4 job posts for a value-retail chain in India. Keep every fact (title, place, pay, "
                            "years, skills) exactly. Naukri: formal. LinkedIn: friendly, under 120 words, hashtags. "
                            "Apna: simple Hinglish. WhatsApp: short with 3-4 emojis. Return JSON with keys Naukri, "
                            "LinkedIn, Apna, WhatsApp.\n\n" + json.dumps(posts, ensure_ascii=False), max_tokens=1400)
    if isinstance(out, dict) and all(isinstance(out.get(s), str) and pay.split("–")[0] in out[s] for s in SITES):
        return {"posts": out, "ai": True}
    return {"posts": posts, "ai": False}


# =========================================================== 19. interview notes -> scorecard
POS = r"good|great|strong|excellent|confident|quick|accurate|calm|clear|impressive|solid|well|fast"
NEG = r"weak|poor|slow|struggl|nervous|unclear|no idea|didn't know|did not know|needs (coaching|work|training)|confused|mistake|errors?"


def notes_to_scorecard(job_id: int, cid: int, notes: str) -> dict:
    j = recruit.get_job(job_id)
    sents = [s.strip() for s in re.split(r"(?<=[.!?\n])\s*", notes or "") if s.strip()]
    rows = []
    for s in j["must"]:
        hits = [x for x in sents if skill_regex(s).search(x) or s.split()[0].lower() in x.lower()]
        if not hits:
            rows.append({"skill": s, "rating": None, "reason": "Not mentioned in your notes. Ask about it or rate it yourself."})
            continue
        p = sum(len(re.findall(POS, h, re.I)) for h in hits)
        n = sum(len(re.findall(NEG, h, re.I)) for h in hits)
        rating = max(1, min(5, 3 + p - n))
        rows.append({"skill": s, "rating": rating, "reason": f'"{hits[0][:140]}"'})
    out = llm.generate_json(
        "Turn the interviewer's rough notes into a scorecard. For each skill give rating 1-5 (or null if the notes "
        "don't say) and a short reason quoting the notes. Use ONLY the notes. Return a JSON list of objects with keys "
        f"skill, rating, reason.\nSKILLS: {', '.join(j['must'])}\nNOTES:\n{notes}", max_tokens=600)
    if isinstance(out, list) and all(isinstance(x, dict) and x.get("skill") in j["must"] for x in out):
        rows = out
    rated = [r["rating"] for r in rows if r.get("rating")]
    return {"rows": rows, "overall": round(sum(rated) / len(rated), 1) if rated else None, "ai": rows is out}


def save_scorecard(job_id: int, cid: int, rows: list[dict], notes: str, by: str) -> dict:
    from ..services import interviews
    scores = {r["skill"]: int(r["rating"]) for r in rows if r.get("rating")}
    return interviews.save_feedback(job_id, cid, scores, notes, by)


# =========================================================== 21. question bank
def _role_key(title: str) -> str:
    return re.split(r"[/(]", title)[0].strip().lower()


def bank(job_id: int) -> list[dict]:
    key = _role_key(recruit.get_job(job_id)["title"])
    rows = db.rows("SELECT * FROM plus_qbank WHERE role=? ORDER BY (up-down) DESC, id", (key,))
    for r in rows:
        r["net"] = r["up"] - r["down"]
    return rows


def bank_add(job_id: int, question: str, qtype: str, by: str) -> dict:
    key = _role_key(recruit.get_job(job_id)["title"])
    if len(question.strip()) < 8:
        raise ValueError("Write the question first.")
    ex = db.one("SELECT id FROM plus_qbank WHERE role=? AND lower(question)=lower(?)", (key, question.strip()))
    if ex:
        return db.one("SELECT * FROM plus_qbank WHERE id=?", (ex["id"],))
    qid = db.run("INSERT INTO plus_qbank(role,question,qtype,up,down,added_by,created_at) VALUES(?,?,?,?,?,?,?)",
                 (key, question.strip(), qtype or "General", 0, 0, by, db.now()))
    return db.one("SELECT * FROM plus_qbank WHERE id=?", (qid,))


def bank_vote(qid: int, useful: bool) -> dict:
    db.run(f"UPDATE plus_qbank SET {'up=up+1' if useful else 'down=down+1'} WHERE id=?", (qid,))
    return db.one("SELECT * FROM plus_qbank WHERE id=?", (qid,))


def bank_import_generated(job_id: int, cid: int, by: str) -> list[dict]:
    """Pull the questions HireMate wrote for an interview into the bank, so HR can vote on them."""
    for q in assist.questions(job_id, cid)["questions"]:
        bank_add(job_id, q["question"], q.get("type", "General"), by)
    return bank(job_id)


# =========================================================== 22. Hindi CV reading
HI = {"नाम": "Name", "पता": "Location", "शहर": "Location", "ईमेल": "Email", "फ़ोन": "Phone", "फोन": "Phone",
      "मोबाइल": "Phone", "सारांश": "Summary", "अनुभव": "Experience", "शिक्षा": "Education", "कौशल": "Skills",
      "योग्यता": "Education", "कैशियर": "Cashier", "स्टोर मैनेजर": "Store Manager", "सुपरवाइज़र": "Supervisor",
      "सुपरवाइजर": "Supervisor", "गोदाम": "warehouse", "वेयरहाउस": "warehouse", "बिलिंग": "billing counter",
      "पीओएस": "POS", "नकद": "cash handling", "कैश": "cash", "ग्राहक सेवा": "customer service", "ग्राहकों": "customers",
      "ग्राहक": "customer", "टीम": "team", "स्टॉक": "stock", "इन्वेंटरी": "inventory", "बिक्री": "sales",
      "लक्ष्य": "targets", "प्रतिदिन": "a day", "रोज़": "daily", "साल": "years", "वर्ष": "years", "महीने": "months",
      "से": "–", "तक": "", "वर्तमान": "Present", "अब तक": "Present", "हिंदी": "Hindi", "अंग्रेज़ी": "English",
      "कंप्यूटर": "basic computer", "एक्सेल": "Excel", "यूपीआई": "UPI", "कार्ड": "card payments", "फोर्कलिफ्ट": "forklift",
      "पिकिंग": "picking", "पैकिंग": "packing", "डिस्पैच": "dispatch", "सुरक्षा": "safety", "संभाला": "handled",
      "किया": "did", "प्रबंधन": "management", "दुकान": "store", "स्टोर": "store", "और": "and", "में": "in", "का": "",
      "की": "", "के": "", "को": "", "जनवरी": "Jan", "फरवरी": "Feb", "मार्च": "Mar", "अप्रैल": "Apr", "मई": "May",
      "जून": "Jun", "जुलाई": "Jul", "अगस्त": "Aug", "सितंबर": "Sep", "अक्टूबर": "Oct", "नवंबर": "Nov", "दिसंबर": "Dec",
      "बारहवीं": "Class 12", "दसवीं": "Class 10", "स्नातक": "Graduate"}
HI.update({"नोएडा": "Noida", "ग्रेटर नोएडा": "Greater Noida", "गाज़ियाबाद": "Ghaziabad", "गाजियाबाद": "Ghaziabad",
           "गुरुग्राम": "Gurugram", "गुड़गांव": "Gurugram", "गुडगाँव": "Gurugram", "दिल्ली": "Delhi", "फरीदाबाद": "Faridabad",
           "इंदिरापुरम": "Indirapuram", "मेरठ": "Meerut", "प्रतिदिन": "every day", "ग्राहकों की": "customers'"})
DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_C = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
      "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
      "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
      "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f"}
_V = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri"}
_M = {"ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri"}


def translit(word: str) -> str:
    """Simple Devanagari → Roman for names and places (रमेश यादव → Ramesh Yadav)."""
    out, i = "", 0
    w = word.replace("़", "")
    while i < len(w):
        ch = w[i]
        nxt = w[i + 1] if i + 1 < len(w) else ""
        if ch in _C:
            out += _C[ch]
            if nxt in _M:
                out += _M[nxt]
                i += 1
            elif nxt == "्":
                i += 1
            elif nxt and nxt not in "ंँः":
                out += "a"
            elif nxt and nxt in "ंँ":
                out += "a"
        elif ch in _V:
            out += _V[ch]
        elif ch in "ंँ":
            out += "n"
        elif ch == "ः":
            out += "h"
        elif ch not in "्":
            out += ch
        i += 1
    return out[:1].upper() + out[1:]


def is_hindi(text: str) -> bool:
    dev = len(re.findall(r"[ऀ-ॿ]", text or ""))
    return dev > 0.2 * max(1, len(re.findall(r"\w", text or "")))


def hindi_to_english(text: str) -> dict:
    out = llm.generate("Translate this CV from Hindi to English. Keep the same lines and headings (Name, Location, "
                       "Email, Phone, Summary, Experience, Education, Skills). Keep names, numbers and dates exactly. "
                       "Use 'Role | Company, City | Mon YYYY – Mon YYYY' for each job. Plain text only.\n\n" + text,
                       max_tokens=1200)
    if out and len(out.split()) > 15:
        return {"text": out.strip(), "ai": True}
    t = text.translate(DEV_DIGITS)
    for k in sorted(HI, key=len, reverse=True):
        t = t.replace(k, HI[k])
    t = re.sub(r"[\u0900-\u097F]+", lambda m: translit(m.group(0)), t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"(?m)^(Name|Location|Email|Phone|Summary|Experience|Education|Skills)\s*[:：-]?\s*", r"\1: ", t)
    first = t.strip().splitlines()[0] if t.strip() else ""
    if first.startswith("Name: "):
        t = t.replace(first, first[6:], 1)
    return {"text": t.strip(), "ai": False}


def add_hindi_cv(text: str, job_id: int | None, by: str) -> dict:
    tr = hindi_to_english(text) if is_hindi(text) else {"text": text, "ai": False}
    c = recruit.create_candidate(tr["text"] + "\n\n[Original CV was in Hindi]", by, source="Upload (Hindi)",
                                 job_id=job_id, allow_duplicate=True)
    return {"candidate": c, "english": tr["text"], "ai": tr["ai"]}


# =========================================================== 23. recruiter performance
def recruiter_performance() -> list[dict]:
    users = [u["name"] for u in db.rows("SELECT name FROM users WHERE role IN ('Admin','Recruiter')")]
    out = []
    for u in users:
        logs = db.rows("SELECT action, detail, created_at, candidate_id, job_id FROM activity_logs WHERE by_name=?", (u,))
        reviewed = sum(1 for l in logs if l["action"] == "Stage changed" and (l["detail"] or "").startswith(("Applied", "Screening")))
        booked = sum(1 for l in logs if l["action"] in ("Interview scheduled", "Interview rescheduled"))
        sent = sum(1 for l in logs if l["action"] in ("Email sent", "Offer sent"))
        hires = [l for l in logs if l["action"] == "Stage changed" and (l["detail"] or "").endswith("Selected")]
        days = []
        for h in hires:
            a = db.one("SELECT created_at FROM applications WHERE job_id=? AND candidate_id=?", (h["job_id"], h["candidate_id"]))
            if a:
                from .insights import _ts
                t0, t1 = _ts(a["created_at"]), _ts(h["created_at"])
                if t0 and t1:
                    days.append((t1 - t0).days)
        out.append({"recruiter": u, "cvs_reviewed": reviewed, "interviews_booked": booked, "emails_sent": sent,
                    "hires": len(hires), "avg_days_to_hire": round(sum(days) / len(days), 1) if days else None,
                    "actions": len(logs)})
    return sorted(out, key=lambda x: -x["actions"])


# =========================================================== 28. live interview helper
def next_question(job_id: int, cid: int, asked: list[str], notes: str = "") -> dict:
    j = recruit.get_job(job_id)
    covered = " ".join(asked) + " " + notes
    left = [s for s in j["must"] if not skill_regex(s).search(covered) and s.split()[0].lower() not in covered.lower()]
    if not left:
        return {"skill": None, "question": "All must-have skills are covered. Ask: 'What questions do you have for us?'",
                "why": "Every must-have skill has come up."}
    s = left[0]
    from_bank = next((q["question"] for q in bank(job_id) if q["net"] >= 0 and skill_regex(s).search(q["question"])), None)
    q = from_bank or f"Tell me about a time you handled {lc(s)} under pressure. What exactly did you do?"
    return {"skill": s, "question": q, "why": f"{s} hasn't come up yet." + (" (Best-rated question from your bank.)" if from_bank else ""),
            "left": left}


# =========================================================== 29. panel agreement
def add_panel_rating(job_id: int, cid: int, rater: str, scores: dict, by: str) -> dict:
    a = recruit.app_for(job_id, cid)
    if not a:
        raise ValueError("Candidate is not in this job.")
    db.run("INSERT INTO plus_panel(application_id,rater,scores_json,created_at) VALUES(?,?,?,?)",
           (a["id"], rater.strip() or by, json.dumps(scores), db.now()))
    return panel_check(job_id, cid)


def panel_check(job_id: int, cid: int) -> dict:
    a = recruit.app_for(job_id, cid)
    if not a:
        return {"raters": [], "gaps": []}
    raters = [{"rater": f["by_name"] or "Interviewer", "scores": json.loads(f["scores_json"] or "{}")}
              for f in db.rows("SELECT by_name, scores_json FROM interview_feedback WHERE application_id=?", (a["id"],))]
    raters += [{"rater": p["rater"], "scores": json.loads(p["scores_json"] or "{}")}
               for p in db.rows("SELECT rater, scores_json FROM plus_panel WHERE application_id=?", (a["id"],))]
    by_skill = defaultdict(list)
    for r in raters:
        for s, v in r["scores"].items():
            by_skill[s].append((r["rater"], int(v)))
    gaps = []
    for s, vals in by_skill.items():
        if len(vals) >= 2:
            lo, hi = min(vals, key=lambda x: x[1]), max(vals, key=lambda x: x[1])
            if hi[1] - lo[1] >= 2:
                gaps.append({"skill": s, "low": lo, "high": hi,
                             "text": f"{lo[0]} gave {lo[1]}, {hi[0]} gave {hi[1]} for {s}. Discuss before deciding."})
    return {"raters": raters, "gaps": gaps, "agree": bool(raters) and len(raters) >= 2 and not gaps}


# =========================================================== 30. role-play scenarios
ROLEPLAY = {
    "Customer service": ("A customer wants to return an opened packet of biscuits without a bill, and is getting loud "
                         "in front of a queue.", "Stays calm, listens, explains the returns policy politely, offers what "
                         "is possible (exchange or manager approval), keeps the queue moving.",
                         "Argues, blames the customer, or breaks policy just to end it."),
    "Cash handling": ("At day-end the cash drawer is ₹500 short and the queue was very busy in the evening.",
                      "Recounts, checks UPI/card slips and voids, reports to the supervisor honestly, notes it in the "
                      "register.", "Hides it, pays from own pocket without reporting, or blames others."),
    "POS systems": ("The POS freezes during a Sunday rush with 12 people in the queue.",
                    "Tells customers, moves to the backup counter or manual bill book, informs IT/supervisor, keeps a "
                    "record of manual bills.", "Leaves the counter or makes customers wait without telling them."),
    "Team management": ("Two of your associates didn't turn up on the first day of the Diwali sale.",
                        "Re-plans the roster, moves people to billing, calls backups, informs the area manager, talks "
                        "to the absentees later.", "Panics, closes counters, or shouts at the team in front of customers."),
    "Inventory control": ("The system shows 40 units of a fast-selling oil but the shelf and back store have only 10.",
                          "Recounts, checks GRN and returns, looks for misplaced stock, raises a variance report.",
                          "Adjusts the system to match without finding the reason."),
    "Warehouse operations": ("A truck for 3 stores is delayed by 2 hours and the next shift is starting.",
                             "Re-sequences picking, informs stores with a new time, hands over clearly to the next shift.",
                             "Waits without telling anyone."),
    "Safety compliance": ("You see a picker riding on the forklift forks to reach a high shelf.",
                          "Stops the work at once, explains the risk, uses the right equipment, reports it.",
                          "Ignores it because the work is getting done."),
}


def roleplay(job_id: int) -> list[dict]:
    j = recruit.get_job(job_id)
    out = []
    for s in j["must"] + j["nice"]:
        if s in ROLEPLAY:
            sc, good, bad = ROLEPLAY[s]
            out.append({"skill": s, "scenario": sc, "good": good, "red_flags": bad})
    if not out:
        sc, good, bad = ROLEPLAY["Customer service"]
        out.append({"skill": "Customer service", "scenario": sc, "good": good, "red_flags": bad})
    return out


# =========================================================== 31. tone switch
TONES = ["Formal", "Warm", "Short", "Hindi", "Hinglish"]


def tone_switch(eid: int, tone: str, by: str) -> dict:
    e = assist.get_email(eid)
    if e["status"] != "Draft":
        raise ValueError("Only drafts can be changed. This one is already sent.")
    if tone not in TONES:
        raise ValueError(f"Tone must be one of {', '.join(TONES)}")
    if tone == "Hindi" and e["type"] in assist.EMAIL_TYPES:
        new = assist.draft_email(e["job_id"], e["candidate_id"], e["type"], "Hindi", by)
        db.run("DELETE FROM emails WHERE id=?", (eid,))
        return assist.get_email(new["id"])
    out = llm.generate(f"Rewrite this recruitment email in a {tone.lower()} tone"
                       + (" in Hinglish (Hindi words in Roman script mixed with English)" if tone == "Hinglish" else "")
                       + ". Keep every date, time, place and name. Keep the last line about AI. Plain text, no subject.\n\n"
                       + e["body"], max_tokens=500)
    body = out
    if not body:
        fn = e["candidate"].split()[0]
        paras = [p for p in e["body"].split("\n\n") if p.strip()]
        core = [p for p in paras if not p.startswith(("Dear", "Regards", "This email", "यह ईमेल"))]
        tail = paras[-1] if paras and ("AI" in paras[-1]) else ""
        if tone == "Short":
            body = f"Hi {fn},\n\n{core[0] if core else ''}\n\nThanks,\nHR Team\n\n{tail}"
        elif tone == "Warm":
            body = (f"Hi {fn},\n\nHope you're doing well! " + "\n\n".join(core)
                    + "\n\nWe're really glad you're interested in joining us. Reach out any time.\n\nWarm regards,\nHR Team\n\n" + tail)
        elif tone == "Formal":
            body = f"Dear {e['candidate']},\n\n" + "\n\n".join(core) + "\n\nYours sincerely,\nHR & Recruitment Team\n\n" + tail
        else:  # Hinglish
            body = (f"Hi {fn},\n\n" + "\n\n".join(core).replace("Thank you", "Thank you so much").replace("Please", "Please")
                    + "\n\nKoi bhi sawaal ho toh reply kar dijiye.\n\nDhanyavaad,\nHR Team\n\n" + tail)
    db.run("UPDATE emails SET body=? WHERE id=?", (body.strip(), eid))
    db.log("Email tone changed", tone, by, candidate_id=e["candidate_id"], job_id=e["job_id"], entity="email", entity_id=eid)
    return {**assist.get_email(eid), "ai": bool(out)}


# =========================================================== 32. candidate question auto-answer
def policy_answer(eid: int, by: str, make_draft: bool = False) -> dict:
    from ..services import knowledge
    e = assist.get_email(eid)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", e["body"]) if s.strip()]
    qs = []
    for s in sents:
        if s.endswith("?"):
            qs += [p.strip(" ,") + ("" if p.strip().endswith("?") else "?")
                   for p in re.split(r",?\s+and\s+(?=(?:should|can|do|is|are|will|what|when|where|how)\b)", s) if p.strip()]
    qs = qs or [e["body"]]
    answers = []
    for q in qs[:3]:
        hits = knowledge.retrieve(q, k=2, policy_only=True)
        if hits:
            body = hits[0]["text"].split("\n", 1)[-1]
            stop = {"the", "a", "an", "is", "are", "i", "my", "should", "there", "at", "to", "for", "do", "can", "you", "we"}
            qw = {w for w in re.findall(r"[a-z]+", q.lower()) if w not in stop}
            best = max(re.split(r"(?<=[.;])\s+", body), key=lambda x: len(qw & set(re.findall(r"[a-z]+", x.lower()))))
            answers.append({"question": q, "answer": best.strip().rstrip(";") , "source": hits[0]["meta"]["title"]})
        else:
            answers.append({"question": q, "answer": None, "source": None})
    found = [a for a in answers if a["answer"]]
    fn = e["candidate"].split()[0]
    text = (f"Hi {fn},\n\nThank you for your message.\n\n"
            + "\n\n".join(f"About \"{a['question']}\": {a['answer']}" if a["answer"] else
                          f"About \"{a['question']}\": let me check and come back to you today." for a in answers)
            + f"\n\nRegards,\nHR Team\n\n{assist.AI_LINE}")
    out = llm.generate("Write a short friendly reply from HR to the candidate. Answer each question ONLY with the policy "
                       "text given; if no policy text, say HR will check and reply today. Under 120 words. Plain text.\n\n"
                       f"CANDIDATE: {e['body']}\n\nPOLICY ANSWERS:\n" + json.dumps(answers, ensure_ascii=False),
                       max_tokens=400)
    if out:
        text = out.strip() + f"\n\n{assist.AI_LINE}"
    res = {"answers": answers, "text": text, "sources": sorted({a["source"] for a in found}), "ai": bool(out)}
    if make_draft:
        nid = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,parent_id,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?)", (e["application_id"], "reply", "English",
                                                    e["subject"] if e["subject"].lower().startswith("re:") else f"Re: {e['subject']}",
                                                    text, "Draft", "out", eid, db.now()))
        db.log("Reply drafted from policy", ", ".join(res["sources"]), by, candidate_id=e["candidate_id"], job_id=e["job_id"])
        res["draft_id"] = nid
    return res


# =========================================================== 33. bulk update, personal touch
NEXT_PLAIN = {"Applied": "Our team will read your CV in the next 3 working days.",
              "Screening": "We're reviewing your CV now and will update you within 3 working days.",
              "Shortlisted": "You're shortlisted! We'll share interview times very soon.",
              "Interview": "Your interview is coming up. Please confirm the time in your portal if you haven't.",
              "Selected": "Congratulations again. HR will share the joining details shortly."}


def bulk_preview(job_id: int, stage: str) -> list[dict]:
    j = recruit.get_job(job_id)
    out = []
    for a in db.rows("SELECT a.id, a.stage, c.id cid, c.name, c.email FROM applications a JOIN candidates c ON "
                     "c.id=a.candidate_id WHERE a.job_id=? AND a.stage=? AND c.anonymised_at IS NULL", (job_id, stage)):
        m = recruit.match_one(job_id, a["cid"])
        strong = next((r["skill"] for r in m["rows"] if r["status"] == "Proven"), None)
        fn = a["name"].split()[0]
        body = (f"Dear {fn},\n\nThank you for applying for the {j['title']} role at our {j['location']}."
                + (f" Your experience in {lc(strong)} stood out to us." if strong else "")
                + f"\n\n{NEXT_PLAIN.get(stage, '')}\n\nRegards,\nRecruitment Team\n\n{assist.AI_LINE}")
        out.append({"application_id": a["id"], "candidate_id": a["cid"], "name": a["name"], "email": a["email"],
                    "subject": f"Update on your {j['title']} application", "body": body})
    return out


def bulk_create(job_id: int, stage: str, by: str) -> dict:
    items = bulk_preview(job_id, stage)
    for it in items:
        db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,created_at) VALUES(?,?,?,?,?,?,?)",
               (it["application_id"], "followup", "English", it["subject"], it["body"], "Draft", db.now()))
    db.log("Bulk update drafted", f"{len(items)} people", by, job_id=job_id)
    return {"drafts": len(items), "text": f"{len(items)} personal drafts made. Check and press Send on each candidate."}


# =========================================================== 34. decision journal
def log_decision(job_id: int, cid: int, decision: str, reason: str, by: str) -> dict:
    a = recruit.app_for(job_id, cid)
    if not a:
        raise ValueError("Candidate is not in this job.")
    if len(reason.strip()) < 5:
        raise ValueError("Write one line on why.")
    db.run("INSERT INTO plus_decisions(application_id,decision,reason,by_name,created_at) VALUES(?,?,?,?,?)",
           (a["id"], decision, reason.strip(), by, db.now()))
    db.log("Decision noted", f"{decision}: {reason[:80]}", by, candidate_id=cid, job_id=job_id)
    return {"ok": True}


def journal() -> dict:
    rows = db.rows("SELECT d.*, c.name, j.title, a.candidate_id, a.job_id FROM plus_decisions d JOIN applications a "
                   "ON a.id=d.application_id JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
                   "ORDER BY d.id DESC")
    noted = {r["application_id"] for r in rows}
    missing = [m for m in db.rows("SELECT a.id application_id, a.stage, a.candidate_id, a.job_id, c.name, j.title "
                                  "FROM applications a JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
                                  "WHERE a.stage IN ('Selected','Rejected')") if m["application_id"] not in noted]
    return {"entries": rows, "missing": missing}


# =========================================================== 35. blind first look
def blind_first_on() -> bool:
    return bool(db.get_setting("plus_blind_first", False))


def set_blind_first(on: bool, by: str) -> dict:
    db.set_setting("plus_blind_first", bool(on))
    db.log("Blind first look " + ("on" if on else "off"), "", by)
    return {"on": bool(on)}


def revealed() -> list[int]:
    return [r["candidate_id"] for r in db.rows("SELECT candidate_id FROM plus_revealed")]


def reveal(cid: int, by: str) -> dict:
    db.run("INSERT OR IGNORE INTO plus_revealed(candidate_id,by_name,created_at) VALUES(?,?,?)", (cid, by, db.now()))
    db.log("Marked interested (details shown)", "", by, candidate_id=cid)
    return {"ok": True}


def blind_card(cid: int, job_id: int) -> dict:
    """What HR sees before 'interested': skills, years, results. No name, gender cues, age, photo or contact."""
    c = recruit.get_candidate(cid)
    m = recruit.match_one(job_id, cid)
    from .talent import _numbers
    return {"label": f"Candidate #{cid}", "years": c["years"], "education_level": c.get("edu_level"),
            "skills": [{"skill": r["skill"], "status": r["status"]} for r in m["rows"]],
            "results": _numbers(c["cv_text"])[:3], "score": m["score"]}
