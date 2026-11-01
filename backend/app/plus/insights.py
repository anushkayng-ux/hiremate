"""HireMate Plus: smart insights on top of the 5 core features.

Everything here is worked out in code from the data already in HireMate, so every number can be explained.
The AI (when a key is set) only rewrites text: the briefing, CV answers and CV-coach tips. Nothing here
rejects, moves or messages a candidate on its own; it only tells HR what it noticed.

  1. Best fit elsewhere   – a person who is weak for their job but strong for another open job
  2. Dropout risk         – who might disappear, why, and what to send them
  3. Commute check        – estimated travel time from the candidate's area to the store
  4. Salary fit           – expected salary vs the job's pay band
  5. Hire and train       – missing skills that can be learned quickly, with weeks to learn
  6. Ask the CV           – questions about one CV, answered only with quoted CV lines
  7. CV coach             – tips for candidates in the portal (never shows scores)
  8. 9 AM briefing        – HR's day in five lines
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime

from .. import db
from . import lc
from ..adapters import llm
from ..core.skills import skill_regex
from ..services import recruit

ACTIVE = ("Applied", "Screening", "Shortlisted", "Interview")


def _ts(s: str | None) -> datetime | None:
    try:
        return datetime.strptime((s or "")[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _days_since(s: str | None) -> int | None:
    t = _ts(s)
    return (datetime.now() - t).days if t else None


# ===================================================================== 3. commute check
# Delhi-NCR places (approximate centre points). Longest name wins, so "Noida Sector 18" beats "Noida".
PLACES = {
    "noida sector 18": (28.5700, 77.3260), "noida sector 62": (28.6270, 77.3650), "greater noida": (28.4744, 77.5040),
    "noida": (28.5355, 77.3910), "raj nagar": (28.6850, 77.4400), "indirapuram": (28.6460, 77.3695),
    "vaishali": (28.6450, 77.3400), "ghaziabad": (28.6692, 77.4538), "faridabad": (28.4089, 77.3178),
    "gurugram distribution centre": (28.4300, 76.9900), "manesar": (28.3540, 76.9366), "gurugram": (28.4595, 77.0266),
    "gurgaon": (28.4595, 77.0266), "laxmi nagar": (28.6304, 77.2777), "mayur vihar": (28.6090, 77.2950),
    "dwarka": (28.5921, 77.0460), "rohini": (28.7495, 77.0565), "saket": (28.5245, 77.2066),
    "lajpat nagar": (28.5677, 77.2433), "karol bagh": (28.6519, 77.1909), "new delhi": (28.6139, 77.2090),
    "delhi": (28.6139, 77.2090), "sonipat": (28.9931, 77.0151), "meerut": (28.9845, 77.7064),
    "bahadurgarh": (28.6920, 76.9240), "ballabgarh": (28.3410, 77.3200),
}


def _place(text: str | None) -> tuple[str, tuple[float, float]] | None:
    t = (text or "").lower()
    for name in sorted(PLACES, key=len, reverse=True):
        if name in t:
            return name, PLACES[name]
    return None


def commute(cand_location: str | None, job_location: str | None) -> dict:
    """Straight-line distance × 1.35 for real roads, at about 22 km/h in NCR traffic, plus 10 minutes to walk/wait."""
    a, b = _place(cand_location), _place(job_location)
    if not a or not b:
        return {"known": False, "text": "Area not recognised. Ask where they live.", "level": "unknown"}
    (la1, lo1), (la2, lo2) = a[1], b[1]
    r = 6371
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    km = 2 * r * math.asin(math.sqrt(math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)) * 1.35
    mins = round(km / 22 * 60 + 10) if km > 1 else 10
    level = "ok" if mins <= 45 else "long" if mins <= 75 else "very long"
    text = {"ok": "Easy daily commute", "long": "Long commute: ask how they will travel",
            "very long": "Very long commute: a common reason store staff leave in the first 3 months"}[level]
    return {"known": True, "from": a[0].title(), "to": b[0].title(), "km": round(km), "minutes": mins,
            "level": level, "text": text}


# ===================================================================== 4. salary fit
DEFAULT_BANDS = [("store manager", 45000, 70000), ("supervisor", 25000, 35000), ("cashier", 15000, 22000),
                 ("customer service", 15000, 22000), ("merchandiser", 20000, 30000), ("associate", 14000, 20000)]


def pay_band(job: dict) -> tuple[int, int]:
    saved = (db.get_setting("plus_pay_bands") or {}).get(str(job["id"]))
    if saved:
        return int(saved[0]), int(saved[1])
    t = job["title"].lower()
    for key, lo, hi in DEFAULT_BANDS:
        if key in t:
            return lo, hi
    return 18000, 30000


def set_pay_band(job_id: int, lo: int, hi: int, by: str) -> dict:
    if lo <= 0 or hi < lo:
        raise ValueError("The top of the band must be at least the bottom.")
    bands = db.get_setting("plus_pay_bands") or {}
    bands[str(job_id)] = [int(lo), int(hi)]
    db.set_setting("plus_pay_bands", bands)
    db.log("Pay band set", f"₹{lo:,}–₹{hi:,} a month", by, job_id=job_id)
    return {"job_id": job_id, "min": lo, "max": hi}


def expected_salary(app_id: int) -> int | None:
    r = db.one("SELECT s.answer FROM screening_answers s JOIN screening_questions q ON q.id=s.question_id "
               "WHERE s.application_id=? AND lower(q.question) LIKE '%salary%'", (app_id,))
    if not r or not r["answer"]:
        return None
    d = re.sub(r"[^\d]", "", r["answer"])
    return int(d) if d else None


def salary_fit(app_id: int) -> dict:
    a = recruit.get_app(app_id)
    j = recruit.get_job(a["job_id"])
    lo, hi = pay_band(j)
    exp = expected_salary(app_id)
    base = {"min": lo, "max": hi, "expected": exp}
    if exp is None:
        return {**base, "level": "unknown", "text": "No expected salary yet. It is asked in the screening questions."}
    if exp < lo:
        return {**base, "level": "low", "text": "Below the band. Check they understood it is a monthly figure."}
    if exp <= hi:
        return {**base, "level": "ok", "text": "Within budget"}
    over = round((exp - hi) / hi * 100)
    if over <= 15:
        return {**base, "level": "negotiate", "text": f"{over}% above the band. Room to talk."}
    return {**base, "level": "high", "text": f"{over}% above the band. Discuss before the interview."}


# ===================================================================== 5. hire and train
LEARN = {  # skill: (weeks to learn on the job, how)
    "POS systems": (1, "Billing-counter training with a senior cashier"),
    "Cash handling": (1, "Cash-tally practice in the first week"),
    "UPI / card payments": (0.5, "Half-day payment-terminal training"),
    "Basic computer": (2, "Basic computer course (MS Office)"),
    "Excel reporting": (2, "Excel basics + the store's MIS template"),
    "Customer service": (2, "Buddy shifts on the shop floor"),
    "Safety compliance": (1, "Safety induction"),
    "WMS software": (2, "WMS training at the distribution centre"),
    "Inventory control": (3, "Shadow two stock audits and cycle counts"),
    "Visual merchandising": (4, "VM workshop + planogram practice"),
    "Forklift": (4, "Certified forklift licence course"),
    "Warehouse operations": (6, "Rotation through picking, packing and dispatch"),
    "Store operations": (8, "Assistant-manager rotation"),
    "Team management": (12, "Needs real experience; hard to teach quickly"),
    "Hindi": (12, "Language takes months"),
    "P&L ownership": (24, "Needs real experience; hard to teach quickly"),
}
TRAINABLE_WEEKS = 4


def hire_and_train(job_id: int, cid: int) -> dict:
    m = recruit.match_one(job_id, cid)
    missing = [r["skill"] for r in m["rows"] if r.get("must") and r["status"] == "Missing"]
    items = [{"skill": s, "weeks": LEARN.get(s, (6, "Ask the team how long this takes"))[0],
              "how": LEARN.get(s, (6, "Ask the team how long this takes"))[1]} for s in missing]
    weeks = sum(i["weeks"] for i in items)
    yrs_short = max(0.0, m["min_years"] - m["years"])
    trainable = bool(items) and weeks <= TRAINABLE_WEEKS and yrs_short <= 1
    text = ("Nothing missing." if not items else
            f"Trainable: about {weeks:g} week{'s' if weeks != 1 else ''} to learn the missing must-haves." if trainable else
            f"About {weeks:g} weeks to learn the missing skills. Probably too long for this role.")
    return {"missing": items, "weeks": weeks, "trainable": trainable, "years_short": yrs_short, "score": m["score"],
            "text": text}


# ===================================================================== 1. best fit elsewhere
def _open_scores() -> dict[tuple[int, int], int]:
    out = {}
    for j in recruit.list_jobs(status="Open"):
        for r in recruit.compute_job(j["id"], scope="all"):
            out[(j["id"], r["candidate_id"])] = r["score"]
    return out


def best_fit_elsewhere(cid: int | None = None) -> list[dict]:
    """Someone in an open job who scores at least 10 points (and 60%+) higher for another open job they're not in."""
    scores = _open_scores()
    jobs = {j["id"]: j for j in recruit.list_jobs(status="Open")}
    sql = ("SELECT a.id, a.job_id, a.candidate_id, a.stage, c.name FROM applications a JOIN candidates c "
           "ON c.id=a.candidate_id WHERE c.anonymised_at IS NULL")
    apps = db.rows(sql + (" AND a.candidate_id=?" if cid else ""), (cid,) if cid else ())
    applied = {(a["job_id"], a["candidate_id"]) for a in db.rows("SELECT job_id, candidate_id FROM applications")}
    best: dict[int, dict] = {}
    for a in apps:
        if a["job_id"] not in jobs or a["stage"] == "Selected":
            continue
        cur = scores.get((a["job_id"], a["candidate_id"]))
        if cur is None:
            continue
        for jid, j in jobs.items():
            if (jid, a["candidate_id"]) in applied:
                continue
            s = scores.get((jid, a["candidate_id"]))
            if s is not None and s >= 60 and s >= cur + 10:
                prev = best.get(a["candidate_id"])
                if not prev or s - cur > prev["gain"]:
                    best[a["candidate_id"]] = {
                        "candidate_id": a["candidate_id"], "name": a["name"], "from_job_id": a["job_id"],
                        "from_job": jobs[a["job_id"]]["title"], "from_score": cur, "from_stage": a["stage"],
                        "to_job_id": jid, "to_job": j["title"], "to_score": s, "gain": s - cur}
    return sorted(best.values(), key=lambda x: -x["gain"])


def move_to_better_fit(cid: int, job_id: int, by: str) -> dict:
    a = recruit.apply(job_id, cid, by, source="Talent pool")
    db.log("Added from Best fit elsewhere", recruit.get_job(job_id)["title"], by, candidate_id=cid, job_id=job_id)
    return a


# ===================================================================== 2. dropout risk
HESITATION = ["another offer", "other offer", "think about it", "let you know", "not sure", "too far", "salary is low",
              "less salary", "can't come", "cannot come", "family", "reconsider", "already joined", "busy"]


def dropout_risk(app_id: int) -> dict:
    a = recruit.get_app(app_id)
    j, c = recruit.get_job(a["job_id"]), recruit.get_candidate(a["candidate_id"])
    reasons: list[tuple[int, str, str]] = []  # (points, reason, what to do)
    iv = db.one("SELECT * FROM interviews WHERE application_id=? AND status='Scheduled' ORDER BY id DESC", (app_id,))
    if iv and not iv.get("candidate_response"):
        days_to = (date.fromisoformat(iv["date"]) - date.today()).days
        if days_to <= 3:
            reasons.append((25, f"Hasn't confirmed the interview ({'in ' + str(days_to) + ' days' if days_to > 0 else 'today'})",
                            "Call or WhatsApp today to confirm the time."))
    since = _days_since(a.get("updated_at") or a.get("created_at"))
    if a["stage"] in ("Applied", "Screening", "Shortlisted") and since is not None and since >= 3:
        reasons.append((min(30, 10 + since * 3), f"Waiting {since} days with no update from us",
                        "Send a short follow-up so they know we're still interested."))
    last_out = db.one("SELECT MAX(sent_at) t FROM emails WHERE application_id=? AND direction='out' AND status='Sent'",
                      (app_id,))["t"]
    last_in = db.one("SELECT MAX(created_at) t FROM emails WHERE application_id=? AND direction='in'", (app_id,))["t"]
    if last_out and (not last_in or last_in < last_out) and (_days_since(last_out) or 0) >= 2:
        reasons.append((15, f"No reply to our last email ({_days_since(last_out)} days)", "Try WhatsApp or a call."))
    words = []
    for m in db.rows("SELECT body FROM emails WHERE application_id=? AND direction='in'", (app_id,)):
        words += [w for w in HESITATION if w in (m["body"] or "").lower()]
    if words:
        reasons.append((25, f'Sounds unsure in a message: "{words[0]}"', "Call them to ask what would help them say yes."))
    cm = commute(c.get("location"), j.get("location"))
    if cm["known"] and cm["level"] != "ok":
        reasons.append((20 if cm["level"] == "very long" else 10, f"Commute about {cm['minutes']} minutes",
                        "Ask how they'll travel; offer a nearer store if there is one."))
    sf = salary_fit(app_id)
    if sf["level"] in ("negotiate", "high"):
        reasons.append((20 if sf["level"] == "high" else 10, f"Expects ₹{sf['expected']:,} a month (band ₹{sf['min']:,}–₹{sf['max']:,})",
                        "Talk about pay early, before the interview."))
    nj = db.one("SELECT s.answer FROM screening_answers s JOIN screening_questions q ON q.id=s.question_id "
                "WHERE s.application_id=? AND lower(q.question) LIKE '%join within%'", (app_id,))
    if nj and (nj["answer"] or "").lower() == "no":
        reasons.append((10, "Can't join within 30 days", "Confirm their notice period and a joining date."))
    off = db.one("SELECT * FROM offers WHERE application_id=? AND status='Sent'", (app_id,))
    if off and (_days_since(off["sent_at"]) or 0) >= 2:
        reasons.append((20, f"Offer sent {_days_since(off['sent_at'])} days ago, no answer", "Call to answer any questions about the offer."))
    pts = min(95, sum(p for p, _, _ in reasons))
    level = "High" if pts >= 50 else "Medium" if pts >= 25 else "Low"
    reasons.sort(key=lambda r: -r[0])
    return {"application_id": app_id, "candidate_id": c["id"], "name": c["name"], "job_id": j["id"], "job": j["title"],
            "stage": a["stage"], "risk": pts, "level": level,
            "reasons": [{"points": p, "reason": r, "action": x} for p, r, x in reasons],
            "next": reasons[0][2] if reasons else "Nothing to do. Keep the process moving."}


def dropout_list() -> list[dict]:
    rows = db.rows("SELECT a.id FROM applications a JOIN jobs j ON j.id=a.job_id JOIN candidates c ON c.id=a.candidate_id "
                   "WHERE j.status='Open' AND c.anonymised_at IS NULL AND (a.stage IN ('Applied','Screening','Shortlisted',"
                   "'Interview') OR EXISTS(SELECT 1 FROM offers o WHERE o.application_id=a.id AND o.status='Sent'))")
    return sorted((dropout_risk(r["id"]) for r in rows), key=lambda x: -x["risk"])


def nudge_message(app_id: int) -> dict:
    """A friendly check-in written for the top risk reason (HR edits and sends it from the Emails tab or WhatsApp)."""
    r = dropout_risk(app_id)
    fn = r["name"].split()[0]
    text = (f"Hi {fn}, this is the HR team about the {r['job']} role. We're still keen on your application. "
            + {True: "Could you confirm your interview time? ", False: ""}[any("confirmed" in x["reason"] for x in r["reasons"])]
            + "Is there anything we can help with, like timings, travel or the role itself? Just reply here.")
    return {"text": text, "risk": r}


# ===================================================================== 6. ask the CV
def _lines(cv: str) -> list[str]:
    out = []
    for ln in (cv or "").splitlines():
        ln = ln.strip(" -•\t")
        if len(ln) < 4:
            continue
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", ln) if len(s.strip()) > 3]
    return out


def ask_cv(cid: int, question: str) -> dict:
    c = recruit.get_candidate(cid)
    lines = _lines(c["cv_text"])
    if not question.strip() or not lines:
        return {"answer": "Ask a question about this CV.", "quotes": [], "ai": False}
    from rank_bm25 import BM25Okapi
    tok = lambda s: re.findall(r"[a-z0-9₹]+", s.lower())
    bm = BM25Okapi([tok(x) for x in lines])
    sc = bm.get_scores(tok(question))
    hits = {i for i, s in enumerate(sc) if s > 0.5}
    for k in ("POS systems", "Cash handling", "Customer service", "Team management", "Inventory control",
              "Excel reporting", "Warehouse operations", "Forklift", "Visual merchandising", "UPI / card payments"):
        if skill_regex(k).search(question):
            hits |= {i for i, x in enumerate(lines) if skill_regex(k).search(x)}
    quotes = [lines[i] for i in sorted(hits, key=lambda i: -sc[i])[:4]]
    if not quotes:
        return {"answer": "Not in the CV. Ask this in the interview.", "quotes": [], "ai": False}
    out = llm.generate("Answer the recruiter's question about a candidate using ONLY these lines from the CV. "
                       "One or two sentences. If the lines don't answer it, say 'Not clear from the CV' and what to ask. "
                       f"Do not guess.\n\nQUESTION: {question}\n\nCV LINES:\n" + "\n".join(f"- {q}" for q in quotes),
                       max_tokens=200)
    return {"answer": (out or "From the CV:").strip(), "quotes": quotes, "ai": bool(out)}


# ===================================================================== 7. CV coach (candidate portal, no scores)
EXAMPLES = {
    "POS systems": "Billed 200+ customers a day on the POS at the billing counter.",
    "Cash handling": "Handled the day-end cash tally with zero shortage for 6 months.",
    "Customer service": "Helped customers with exchanges and answered their queries on the floor.",
    "Team management": "Led a team of 8 associates and made the weekly roster.",
    "Inventory control": "Ran weekly stock audits and cut shrinkage by 1%.",
    "Excel reporting": "Prepared the daily sales MIS report in Excel.",
    "Store operations": "Opened and closed the store and managed daily store operations.",
    "Visual merchandising": "Set up window displays for festive launches using the planogram.",
    "Warehouse operations": "Managed picking, packing and dispatch of 500+ orders a day.",
    "WMS software": "Used the WMS to put away stock and track orders.",
    "Forklift": "Operated a forklift safely (licence valid till 2027).",
    "Safety compliance": "Ran monthly safety checks on the warehouse floor.",
    "UPI / card payments": "Took UPI and card payments at the counter.",
    "P&L ownership": "Owned the store's monthly sales targets and P&L.",
}


def cv_coach(cid: int, job_id: int) -> dict:
    c = recruit.get_candidate(cid)
    m = recruit.match_one(job_id, cid)
    tips = []
    for r in m["rows"]:
        if not r.get("must"):
            continue
        if r["status"] == "Missing":
            tips.append({"kind": "add", "title": f"Show {lc(r['skill'])}, if you have done it",
                         "detail": "The job asks for it and your CV doesn't mention it.",
                         "example": EXAMPLES.get(r["skill"], f"Add one line about where you used {r['skill']}.")})
        elif r["status"] == "Listed":
            tips.append({"kind": "prove", "title": f"Give an example of {lc(r['skill'])}",
                         "detail": "You list it under skills but don't say where you used it.",
                         "example": EXAMPLES.get(r["skill"], f"Add one sentence about using {r['skill']} at work.")})
    if not c.get("phone"):
        tips.append({"kind": "basic", "title": "Add your phone number",
                     "detail": "The team calls or WhatsApps to book interviews.", "example": "Phone: +91 98xxx xxxxx"})
    if not c.get("roles"):
        tips.append({"kind": "basic", "title": "Add dates to each job",
                     "detail": "Write the month and year you started and left.",
                     "example": "Cashier | DailyNeeds Store, Ghaziabad | Jun 2022 – Feb 2023"})
    if len((c["cv_text"] or "").split()) < 120:
        tips.append({"kind": "basic", "title": "Add a little more detail",
                     "detail": "Two or three lines per job with numbers (customers a day, team size, targets).",
                     "example": "Billed 250+ customers a day with 99.8% cash accuracy."})
    good = [r["skill"] for r in m["rows"] if r.get("must") and r["status"] == "Proven"]
    return {"job_id": job_id, "job": recruit.get_job(job_id)["title"], "strengths": good, "tips": tips,
            "done": len(tips) == 0}


# ===================================================================== 8. 9 AM briefing
def briefing(user_name: str = "") -> dict:
    from ..services import assist, interviews, smart
    today = str(date.today())
    ivs = [i for i in interviews.list_all("upcoming") if i["date"] == today]
    replies = assist.inbox(unread_only=True)
    waits = smart.waiting()
    risks = [r for r in dropout_list() if r["level"] == "High"]
    moves = best_fit_elsewhere()
    drafts = db.one("SELECT COUNT(*) n FROM emails WHERE status='Draft' AND direction='out'")["n"]
    lines = []
    lines.append(f"Interviews today: {len(ivs)}" + (f" ({', '.join(i['candidate'] + ' ' + i['time'] for i in ivs[:3])})" if ivs else "") + ".")
    lines.append(f"Replies waiting: {len(replies)}" + (f" (from {', '.join(sorted({r['candidate'] for r in replies})[:3])})" if replies else "") + ".")
    if risks:
        lines.append(f"Might drop out: {', '.join(r['name'] for r in risks[:3])}. Top reason: {risks[0]['reasons'][0]['reason'].lower()}.")
    if waits:
        lines.append(f"Waiting too long: {len(waits)} people, longest {waits[0]['name']} ({waits[0]['days']} days).")
    if moves:
        mv = moves[0]
        lines.append(f"Better fit elsewhere: {mv['name']} scores {mv['to_score']}% for {mv['to_job']} "
                     f"(vs {mv['from_score']}% now).")
    if drafts:
        lines.append(f"{drafts} email draft{'s' if drafts != 1 else ''} ready to check and send.")
    first = (["Start with " + ("the replies" if replies else f"{risks[0]['name']}" if risks else "the waiting list" if waits
                               else "today's interviews") + "."])
    text = "\n".join(f"- {x}" for x in lines + first)
    out = llm.generate("Rewrite this HR morning briefing as 5 short, friendly bullet points for a recruiter. Keep every "
                       "name and number exactly. No new facts.\n\n" + text, max_tokens=300)
    return {"text": (out or text).strip(), "ai": bool(out), "date": today,
            "counts": {"interviews": len(ivs), "replies": len(replies), "high_risk": len(risks), "waiting": len(waits),
                       "better_fit": len(moves), "drafts": drafts}}


# ===================================================================== one call for the candidate page
def candidate_panel(cid: int, job_id: int) -> dict:
    c = recruit.get_candidate(cid)
    j = recruit.get_job(job_id)
    a = recruit.app_for(job_id, cid)
    out = {"commute": commute(c.get("location"), j.get("location")), "train": hire_and_train(job_id, cid),
           "elsewhere": best_fit_elsewhere(cid)}
    if a:
        out["salary"] = salary_fit(a["id"])
        out["risk"] = dropout_risk(a["id"])
    return out


# ===================================================================== demo data
SAMPLE_SALARY = {("Priya Nair", "Store Manager"): 65000, ("Rohit Verma", "Store Manager"): 78000,
                 ("Imran Qureshi", "Store Manager"): 52000, ("Kavya Iyer", "Store Manager"): 60000,
                 ("Anjali Sharma", "Cashier"): 21000, ("Rohit Verma", "Cashier"): 40000, ("Sana Khan", "Cashier"): 16000,
                 ("Arjun Mehta", "Warehouse"): 33000, ("Imran Qureshi", "Warehouse"): 30000}


def seed() -> None:
    """Realistic expected salaries + a hesitant message, so every Plus feature has something to show."""
    for a in db.rows("SELECT a.id, c.name, j.title FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                     "JOIN jobs j ON j.id=a.job_id"):
        val = next((v for (n, t), v in SAMPLE_SALARY.items() if n == a["name"] and t in a["title"]), None)
        q = db.one("SELECT q.id FROM screening_questions q JOIN applications p ON p.job_id=q.job_id WHERE p.id=? "
                   "AND lower(q.question) LIKE '%salary%'", (a["id"],))
        if val and q:
            db.run("INSERT INTO screening_answers(application_id,question_id,answer,created_at) VALUES(?,?,?,?) "
                   "ON CONFLICT(application_id,question_id) DO UPDATE SET answer=excluded.answer",
                   (a["id"], q["id"], str(val), db.now()))
    # Priya (shortlisted) sounds a little unsure in a reply
    p = db.one("SELECT a.id FROM applications a JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
               "WHERE c.name='Priya Nair' AND j.title LIKE 'Store Manager%'")
    if p:
        out = db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at,sent_by)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?)", (p["id"], "followup", "English",
                                                      "Following up on your application for Store Manager",
                                                      "Dear Priya,\n\nThank you for your patience. You are shortlisted, and we will share "
                                                      "interview times shortly.\n\nRegards,\nRecruitment Team", "Sent", "out",
                                                      db.now(), db.now(), "Demo Admin"))
        db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,parent_id,created_at,sent_at) "
               "VALUES(?,?,?,?,?,?,?,?,?,?)", (p["id"], "candidate", "English", "Re: Following up on your application",
                                                "Thank you. I have another offer from a mall chain, so please let me know "
                                                "the interview date soon.", "Received", "in", out, db.now(), db.now()))


DEEPAK_CV = """Deepak Singh
Email: deepak.singh@example.com
Phone: +91 90000 00088
Location: Gurugram
Summary: Warehouse team lead with 4 years in e-commerce and retail distribution centres.
Experience:
Warehouse Team Lead | FastShip Logistics, Gurugram | Apr 2023 – Present
- Led a team of 12 pickers and packers on the night shift.
- Managed picking, packing and dispatch of 900+ orders a day.
- Used the WMS for put-away, cycle counts and stock variance reports.
- Ran weekly safety checks on the warehouse floor; zero accidents in 2024.
Picker | QuickKart Warehouse, Manesar | Jan 2021 – Mar 2023
- Operated a forklift (licence valid till 2027) and loaded trucks for 15 stores.
Education: Class 12, 2020
Skills: warehouse operations, WMS, inventory, forklift, safety, team management, Hindi"""


def seed_all() -> None:
    """Demo data for every Plus feature (called after the core seed)."""
    from . import ensure_schema, hr_tools
    ensure_schema()
    seed()
    from ..services import knowledge
    knowledge.create_doc("Interview day guide",
                         "Candidates should bring a photo ID and a printed copy of their CV. For warehouse roles, bring any "
                         "forklift licence or safety certificate you have. Free two-wheeler and car parking is available at "
                         "the Gurugram distribution centre and at most stores; tell the security desk you are here for an "
                         "interview. Please arrive 10 minutes early.", "Policy", "Seed", source="Seed")
    # a second interviewer who disagrees with the first on one skill (panel agreement check)
    a = db.one("SELECT a.id, a.job_id, a.candidate_id FROM applications a JOIN candidates c ON c.id=a.candidate_id "
               "WHERE c.name='Anjali Sharma' AND a.stage='Interview'")
    if a:
        db.run("INSERT INTO plus_panel(application_id,rater,scores_json,created_at) VALUES(?,?,?,?)",
               (a["id"], "Second interviewer (HR)", '{"Customer service": 2, "POS systems": 5, "Cash handling": 4}', db.now()))
    # question bank starters
    for j in recruit.list_jobs():
        for s in j["must"][:3]:
            q = hr_tools.bank_add(j["id"], f"Walk me through how you handle {lc(s)} on your busiest day.",
                                  "Technical", "Seed")
            db.run("UPDATE plus_qbank SET up=? WHERE id=?", (2 if s == j["must"][0] else 1, q["id"]))
        hr_tools.bank_add(j["id"], "Why do you want to work in retail?", "HR", "Seed")
    # a duplicate profile (same phone, different email) for Duplicate & merge
    imran = db.one("SELECT * FROM candidates WHERE name='Imran Qureshi'")
    if imran:
        dup_cv = imran["cv_text"].replace(imran["email"] or "@@", "imran.q@example.com")
        recruit.create_candidate(dup_cv, "Seed", source="Seed", allow_duplicate=True)
    # recruiter performance: give real names to the seeded work
    names = ["Demo Admin", "Demo Recruiter"]
    for i, l in enumerate(db.rows("SELECT id FROM activity_logs WHERE by_name='Seed' AND action IN "
                                  "('Stage changed','Interview scheduled','Added to job') ORDER BY id")):
        db.run("UPDATE activity_logs SET by_name=? WHERE id=?", (names[i % 2], l["id"]))
    # the seeded interviews and the sent invite, credited to the people who did them
    for i, iv in enumerate(db.rows("SELECT i.id, i.date, i.time, a.candidate_id, a.job_id FROM interviews i JOIN applications a "
                                   "ON a.id=i.application_id")):
        db.log("Interview scheduled", f"{iv['date']} {iv['time']}", names[i % 2], candidate_id=iv["candidate_id"],
               job_id=iv["job_id"], entity="interview", entity_id=iv["id"])
    for e in db.rows("SELECT e.id, e.sent_by, a.candidate_id, a.job_id FROM emails e JOIN applications a "
                     "ON a.id=e.application_id WHERE e.status='Sent' AND e.direction='out'"):
        db.log("Email sent", "", e["sent_by"] or names[0], candidate_id=e["candidate_id"], job_id=e["job_id"],
               entity="email", entity_id=e["id"])
    # a decision already noted, and a 'Not selected' without a reason so the journal has both
    # Deepak (warehouse background) applied for Cashier – Best fit elsewhere spots he suits Warehouse Supervisor
    cashier = db.one("SELECT id FROM jobs WHERE title LIKE 'Cashier%'")
    if cashier:
        dk = recruit.create_candidate(DEEPAK_CV, "Seed", source="Seed", allow_duplicate=True)
        a2 = recruit.apply(cashier["id"], dk["id"], "Seed", source="Walk-in")
        q = db.one("SELECT id FROM screening_questions WHERE job_id=? AND lower(question) LIKE '%salary%'", (cashier["id"],))
        if q:
            db.run("INSERT OR REPLACE INTO screening_answers(application_id,question_id,answer,created_at) VALUES(?,?,?,?)",
                   (a2["id"], q["id"], "26000", db.now()))
        from ..services import extras
        extras.record_consent(dk["id"])
    # Rohit was marked 'not selected' for Cashier (over-qualified, expects more pay) with no reason written yet
    r = db.one("SELECT a.id FROM applications a JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
               "WHERE c.name='Rohit Verma' AND j.title LIKE 'Cashier%'")
    if r:
        recruit.set_stage(r["id"], "Rejected", "Demo Recruiter")
    if a:
        hr_tools.log_decision(a["job_id"], a["candidate_id"], "Interview",
                              "Strong billing test (2 errors in 50 bills); calm in role-play.", "Demo Admin")
