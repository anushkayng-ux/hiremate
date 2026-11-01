"""HireMate Plus: candidate-portal tools. Candidates never see scores here, only friendly results.

11 No CV? Answer 6 questions      14 Honest status timing
12 AI chat screening              15 Joining day checklist
13 Pick your own interview slot   20 Cashier billing test
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime

from .. import db
from . import lc
from ..adapters import llm
from ..config import FILES_DIR
from ..core.skills import SKILLS, skill_regex
from ..services import recruit

# =========================================================== 11. CV builder
CV_QUESTIONS = [
    {"key": "name", "q": "Your full name", "hint": "Anjali Sharma"},
    {"key": "city", "q": "Which area do you live in?", "hint": "Indirapuram, Ghaziabad"},
    {"key": "phone", "q": "Your phone number", "hint": "+91 98xxx xxxxx"},
    {"key": "jobs", "q": "Your last 1–2 jobs: role, shop or company, city, from when to when",
     "hint": "Cashier, DailyNeeds Store, Ghaziabad, Jun 2022 to now"},
    {"key": "daily", "q": "What did you do every day at work?", "hint": "Billing on POS, cash tally, helping customers"},
    {"key": "proud", "q": "One thing you are proud of at work (numbers help)", "hint": "Billed 200 customers a day with no cash shortage"},
    {"key": "education", "q": "Your education", "hint": "Class 12, CBSE, 2021"},
    {"key": "languages", "q": "Languages you speak", "hint": "Hindi, English"},
]
MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{4})"


def _job_line(s: str) -> str:
    parts = [p.strip() for p in re.split(r",", s) if p.strip()]
    dates = re.findall(MONTH, s, re.I)
    now = bool(re.search(r"\b(now|present|current|till date|abhi)\b", s, re.I))
    if dates:
        d1 = f"{dates[0][0][:3].title()} {dates[0][1]}"
        d2 = "Present" if now or len(dates) < 2 else f"{dates[1][0][:3].title()} {dates[1][1]}"
        parts = [p for p in parts if not re.search(MONTH, p, re.I) and not re.search(r"\b(now|present)\b", p, re.I)]
        role = parts[0] if parts else "Role"
        org = ", ".join(parts[1:3]) if len(parts) > 1 else ""
        return f"{role} | {org} | {d1} – {d2}"
    return s


def build_cv(answers: dict) -> dict:
    a = {k: (v or "").strip() for k, v in answers.items()}
    if not a.get("name") or not a.get("jobs") and not a.get("daily"):
        raise ValueError("Write at least your name and your last job.")
    jobs = [j for j in re.split(r"\n|;", a.get("jobs", "")) if j.strip()]
    duties = [d.strip() for d in re.split(r",|\n|;", a.get("daily", "")) if d.strip()]
    lines = [a["name"]]
    if a.get("phone"):
        lines.append(f"Phone: {a['phone']}")
    if a.get("city"):
        lines.append(f"Location: {a['city']}")
    first_role = _job_line(jobs[0]).split("|")[0].strip() if jobs else "Retail associate"
    lines.append(f"Summary: {first_role} with hands-on experience in {', '.join(lc(d) for d in duties[:3]) or 'retail work'}.")
    lines.append("Experience:")
    for i, j in enumerate(jobs[:3]):
        lines.append(_job_line(j))
        if i == 0:
            lines += [f"- {d[0].upper() + d[1:]}." for d in duties[:4]]
            if a.get("proud"):
                lines.append(f"- {a['proud'][0].upper() + a['proud'][1:].rstrip('.')}.")
    if a.get("education"):
        lines.append(f"Education: {a['education']}")
    found = [k for k in SKILLS if skill_regex(k).search(a.get("daily", "") + " " + a.get("proud", ""))]
    langs = [x.strip() for x in a.get("languages", "").split(",") if x.strip()]
    lines.append("Skills: " + ", ".join(found + [l for l in langs if l not in found]))
    text = "\n".join(lines)
    out = llm.generate("Polish this CV's wording for a retail job in India. Keep the same lines, headings, names, numbers "
                       "and dates. Do not add any job, skill or number that is not there. Plain text.\n\n" + text,
                       max_tokens=700)
    if out and a["name"] in out and len(out.split()) >= len(text.split()) * 0.7:
        text = out.strip()
    return {"text": text, "ai": bool(out)}


# =========================================================== 12. AI chat screening
def _own(cid: int, app_id: int) -> dict:
    a = recruit.get_app(app_id)
    if a["candidate_id"] != cid:
        raise ValueError("Application not found.")
    return a


def screen_questions(app_id: int) -> list[dict]:
    a = recruit.get_app(app_id)
    j = recruit.get_job(a["job_id"])
    qs = [{"skill": s, "q": f"Tell us about a time you used {lc(s)} at work. What did you do, and what happened?"}
          for s in j["must"][:3]]
    qs.append({"skill": "Customer focus", "q": "A customer is angry because the item they want is out of stock. What do you say?"})
    qs.append({"skill": "Reliability", "q": "Stores are busiest on weekends and festivals. How do you plan around those shifts?"})
    return qs


def _score_answer(skill: str, ans: str) -> tuple[int, str]:
    a = ans or ""
    words = len(a.split())
    pts, why = 1, []
    if words >= 25:
        pts += 1
        why.append("gave detail")
    if re.search(r"\b(i|me|my)\b", a, re.I):
        pts += 1
        why.append("spoke about own actions")
    if re.search(r"\d", a):
        pts += 1
        why.append("used numbers")
    if skill in SKILLS and skill_regex(skill).search(a) or re.search(r"customer|sorry|help|shift|plan|team", a, re.I):
        pts += 1
        why.append("on topic")
    if words < 6:
        pts, why = 1, ["very short answer"]
    return min(5, pts), ", ".join(why) or "general answer"


def submit_screening(cid: int, app_id: int, answers: list[str]) -> dict:
    _own(cid, app_id)
    qs = screen_questions(app_id)
    res = []
    for q, ans in zip(qs, answers + [""] * len(qs)):
        s, why = _score_answer(q["skill"], ans)
        res.append({"skill": q["skill"], "question": q["q"], "answer": ans, "score": s, "why": why})
    out = llm.generate_json("Score each candidate answer 1-5 for a retail job: 5 = specific example with own actions and "
                            "result, 1 = empty or off-topic. Return a JSON list of {score, why} (why under 12 words), "
                            "same order.\n\n" + json.dumps([{"q": r["question"], "a": r["answer"]} for r in res],
                                                           ensure_ascii=False), max_tokens=500)
    if isinstance(out, list) and len(out) == len(res) and all(isinstance(x, dict) and "score" in x for x in out):
        for r, x in zip(res, out):
            r["score"], r["why"] = max(1, min(5, int(x["score"]))), str(x.get("why", r["why"]))
    total = round(sum(r["score"] for r in res) / (5 * len(res)) * 100)
    db.run("INSERT INTO plus_screen(application_id,items_json,total,ai,created_at) VALUES(?,?,?,?,?) "
           "ON CONFLICT(application_id) DO UPDATE SET items_json=excluded.items_json,total=excluded.total,ai=excluded.ai,"
           "created_at=excluded.created_at", (app_id, json.dumps(res), total, int(bool(out)), db.now()))
    a = recruit.get_app(app_id)
    db.log("AI chat screening done", f"{total}%", "Candidate", candidate_id=cid, job_id=a["job_id"])
    return {"ok": True}


def screening_result(app_id: int) -> dict | None:
    r = db.one("SELECT * FROM plus_screen WHERE application_id=?", (app_id,))
    if not r:
        return None
    return {"total": r["total"], "items": json.loads(r["items_json"]), "ai": bool(r["ai"]), "at": r["created_at"]}


# =========================================================== 13. pick your own slot
def my_slots(cid: int, app_id: int) -> list[dict]:
    from ..services import smart
    a = _own(cid, app_id)
    if a["stage"] != "Shortlisted":
        return []
    return smart.free_slots(a["job_id"], cid, "HR Team", n=6)


def book_my_slot(cid: int, app_id: int, d: str, t: str, mode: str) -> dict:
    from ..services import smart
    a = _own(cid, app_id)
    if a["stage"] != "Shortlisted":
        raise ValueError("You can pick a time once you are shortlisted.")
    ok = {(s["date"], s["time"]) for s in smart.free_slots(a["job_id"], cid, "HR Team", n=6)}
    if (d, t) not in ok:
        raise ValueError("That time was just taken. Please pick another.")
    r = smart.book(a["job_id"], cid, d, t, mode if mode in ("In person", "Video call", "Phone") else "In person",
                   "HR Team", "Candidate (self-booked)")
    db.run("UPDATE interviews SET candidate_response='Confirmed', candidate_note='Picked by the candidate', responded_at=? "
           "WHERE id=?", (db.now(), r["interview"]["id"]))
    db.run("INSERT INTO emails(application_id,type,lang,subject,body,status,direction,created_at,sent_at) "
           "VALUES(?,?,?,?,?,?,?,?,?)", (app_id, "candidate", "English", "I booked my interview",
                                          f"I picked {d} at {t} ({mode}) for my interview.", "Received", "in",
                                          db.now(), db.now()))
    return {"ok": True, "interview": r["interview"]}


# =========================================================== 14. honest status timing
TYPICAL = {"Applied": 3, "Screening": 3, "Shortlisted": 4, "Interview": 5}


def status_timing(cid: int) -> list[dict]:
    from ..services import extras
    try:
        avg = {d["stage"]: d["days"] for d in extras.metrics()["days_in_stage"] if d["days"]}
    except Exception:  # noqa: BLE001
        avg = {}
    out = []
    for a in db.rows("SELECT id, stage, created_at, updated_at FROM applications WHERE candidate_id=?", (cid,)):
        if a["stage"] not in TYPICAL:
            continue
        since = a["updated_at"] if a["stage"] != "Applied" else a["created_at"]
        try:
            day = (datetime.now() - datetime.strptime(since[:19], "%Y-%m-%d %H:%M:%S")).days + 1
        except (TypeError, ValueError):
            day = 1
        typ = max(1, round(avg.get(a["stage"]) or TYPICAL[a["stage"]]))
        late = day > typ + 1
        out.append({"application_id": a["id"], "typical_days": typ, "day": day, "late": late,
                    "text": (f"Usually about {typ} day{'s' if typ > 1 else ''} at this step. You're on day {day}."
                             + (" It's taking longer than usual. We've reminded the team." if late else ""))})
    return out


# =========================================================== 15. joining checklist
JOIN_DOCS = ["Photo ID (Aadhaar)", "PAN card", "Bank passbook or cancelled cheque", "Passport-size photo",
             "Last salary slip (if any)", "Relieving letter (if any)"]


def _offer_accepted(app_id: int) -> bool:
    return bool(db.one("SELECT 1 FROM offers WHERE application_id=? AND status='Accepted'", (app_id,)))


def checklist(app_id: int) -> dict:
    got = {r["doc"]: r for r in db.rows("SELECT * FROM plus_joining WHERE application_id=?", (app_id,))}
    items = [{"doc": d, "uploaded": d in got, "file_name": got.get(d, {}).get("file_name"),
              "verified": bool(got.get(d, {}).get("verified_at")), "verified_by": got.get(d, {}).get("verified_by"),
              "optional": "(if any)" in d} for d in JOIN_DOCS]
    need = [i for i in items if not i["optional"]]
    return {"application_id": app_id, "open": _offer_accepted(app_id), "items": items,
            "done": sum(i["verified"] for i in need), "total": len(need),
            "ready": all(i["verified"] for i in need)}


def upload_doc(cid: int, app_id: int, doc: str, name: str, data: bytes) -> dict:
    _own(cid, app_id)
    if doc not in JOIN_DOCS:
        raise ValueError("Unknown document.")
    if not _offer_accepted(app_id):
        raise ValueError("Upload documents after you accept the offer.")
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("File is too big (max 8 MB).")
    d = FILES_DIR / "joining" / str(app_id)
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-80:]
    (d / safe).write_bytes(data)
    db.run("INSERT INTO plus_joining(application_id,doc,file_name,path,uploaded_at) VALUES(?,?,?,?,?) "
           "ON CONFLICT(application_id,doc) DO UPDATE SET file_name=excluded.file_name, path=excluded.path, "
           "uploaded_at=excluded.uploaded_at, verified_by=NULL, verified_at=NULL", (app_id, doc, safe, str(d / safe), db.now()))
    return checklist(app_id)


def verify_doc(app_id: int, doc: str, by: str) -> dict:
    db.run("UPDATE plus_joining SET verified_by=?, verified_at=? WHERE application_id=? AND doc=?", (by, db.now(), app_id, doc))
    a = recruit.get_app(app_id)
    db.log("Joining document checked", doc, by, candidate_id=a["candidate_id"], job_id=a["job_id"])
    return checklist(app_id)


def doc_file(app_id: int, doc: str) -> tuple[str, bytes] | None:
    r = db.one("SELECT file_name, path FROM plus_joining WHERE application_id=? AND doc=?", (app_id, doc))
    if not r:
        return None
    from pathlib import Path
    p = Path(r["path"])
    return (r["file_name"], p.read_bytes()) if p.exists() else None


def joining_overview() -> list[dict]:
    out = []
    for o in db.rows("SELECT o.application_id, c.name, j.title, o.joining_date FROM offers o JOIN applications a "
                     "ON a.id=o.application_id JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
                     "WHERE o.status='Accepted'"):
        ch = checklist(o["application_id"])
        out.append({**o, **{k: ch[k] for k in ("done", "total", "ready")}, "items": ch["items"]})
    return out


# =========================================================== 20. cashier billing test
def _make_items(rng: random.Random) -> list[dict]:
    goods = [("Atta 5 kg", 245), ("Toor dal 1 kg", 162), ("Sugar 1 kg", 46), ("Sunflower oil 1 L", 139),
             ("Basmati rice 1 kg", 118), ("Tea 250 g", 135), ("Detergent 1 kg", 98), ("Biscuits", 30),
             ("Shampoo 180 ml", 112), ("Soap (pack of 4)", 156)]
    qs = []
    for _ in range(3):  # bill totals
        pick = rng.sample(goods, 3)
        qty = [rng.randint(1, 3) for _ in pick]
        txt = ", ".join(f"{q} × {g} @ ₹{p}" for (g, p), q in zip(pick, qty))
        qs.append({"type": "Bill total", "q": f"Total bill: {txt}", "answer": sum(p * q for (_, p), q in zip(pick, qty))})
    for _ in range(3):  # change
        bill = rng.randint(120, 1890)
        paid = next(n for n in (200, 500, 1000, 2000) if n > bill)
        qs.append({"type": "Change", "q": f"Bill is ₹{bill}. Customer gives ₹{paid}. How much change?", "answer": paid - bill})
    for _ in range(2):  # discount
        mrp = rng.choice([400, 650, 899, 1200, 1500])
        pct = rng.choice([5, 10, 15, 20])
        qs.append({"type": "Discount", "q": f"MRP ₹{mrp} with {pct}% off. What does the customer pay? (round to the rupee)",
                   "answer": round(mrp * (100 - pct) / 100)})
    return qs


def start_test(cid: int, app_id: int) -> dict:
    _own(cid, app_id)
    seed = random.randint(1, 10 ** 9)
    qs = _make_items(random.Random(seed))
    tid = db.run("INSERT INTO plus_tests(application_id,seed,started_at) VALUES(?,?,?)", (app_id, seed, db.now()))
    return {"test_id": tid, "minutes": 8, "questions": [{"n": i, "type": q["type"], "q": q["q"]} for i, q in enumerate(qs)]}


def submit_test(cid: int, tid: int, answers: list) -> dict:
    t = db.one("SELECT * FROM plus_tests WHERE id=?", (tid,))
    if not t:
        raise ValueError("Test not found.")
    _own(cid, t["application_id"])
    if t["finished_at"]:
        raise ValueError("You already finished this test.")
    qs = _make_items(random.Random(t["seed"]))
    right = 0
    detail = []
    for q, a in zip(qs, answers + [None] * len(qs)):
        try:
            ok = a is not None and abs(float(str(a).replace("₹", "").replace(",", "")) - q["answer"]) < 1
        except ValueError:
            ok = False
        right += ok
        detail.append({"type": q["type"], "q": q["q"], "given": a, "correct": q["answer"], "ok": ok})
    secs = int((datetime.now() - datetime.strptime(t["started_at"][:19], "%Y-%m-%d %H:%M:%S")).total_seconds())
    db.run("UPDATE plus_tests SET finished_at=?, score=?, total=?, seconds=?, detail_json=? WHERE id=?",
           (db.now(), right, len(qs), secs, json.dumps(detail), tid))
    a = recruit.get_app(t["application_id"])
    db.log("Billing test done", f"{right}/{len(qs)} in {secs // 60}m {secs % 60}s", "Candidate", candidate_id=cid, job_id=a["job_id"])
    return {"done": True, "right": right, "total": len(qs)}


def test_result(app_id: int) -> dict | None:
    t = db.one("SELECT * FROM plus_tests WHERE application_id=? AND finished_at IS NOT NULL ORDER BY id DESC", (app_id,))
    if not t:
        return None
    return {"score": t["score"], "total": t["total"], "seconds": t["seconds"], "detail": json.loads(t["detail_json"] or "[]"),
            "pct": round(t["score"] / t["total"] * 100), "at": t["finished_at"]}


def test_applies(app_id: int) -> bool:
    j = recruit.get_job(recruit.get_app(app_id)["job_id"])
    return any(k in j["title"].lower() for k in ("cashier", "billing", "customer service"))
