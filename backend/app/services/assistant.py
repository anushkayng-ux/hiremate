"""Asha, the in-app assistant.

How it works:
1. A rule-based intent router handles actions (create job, add candidate, move stage, schedule,
   draft email, notes, knowledge store) and database questions. This works with no LLM at all.
2. Questions about policies/documents go to RAG (BM25 + vectors) with sources.
3. The LLM (if configured) only writes text: JDs, emails, and grounded answers.
4. Anything risky (create, delete, approve) waits for the recruiter to say yes.
"""
from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta

from .. import db
from ..adapters import llm
from ..core.jdcheck import jd_check
from ..core.parsing import ParseError, classify, find_city, parse_cv, parse_jd
from ..core.skills import skills_in
from . import analytics, assist, criteria, files, interviews, knowledge, recruit

BOT = "Asha"
YES = r"^(ok|okay|yes|yep|sure|go ahead|confirm|do it|haan|ha|please do|approve|send|send it|create|yes,)\b"
NO = r"^(no|cancel|stop|not now|leave it)\b"


# ================================================================ session state
def load_state(sid: str) -> dict:
    r = db.one("SELECT state_json FROM assistant_sessions WHERE id=?", (sid,))
    st = json.loads(r["state_json"]) if r else {}
    st.setdefault("pending", None)
    st.setdefault("ctx", {})
    st.setdefault("history", [])
    return st


def save_state(sid: str, uid: int, st: dict) -> None:
    st["history"] = st["history"][-40:]
    db.run("INSERT INTO assistant_sessions(id,user_id,state_json,updated_at) VALUES(?,?,?,?) "
           "ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
           (sid, uid, json.dumps(st), db.now()))


def clear(sid: str) -> None:
    db.run("DELETE FROM assistant_sessions WHERE id=?", (sid,))


# ================================================================ helpers
_MODE = threading.local()   # set while a streamed chat call is running


def R(reply: str, **kw) -> dict:
    return {"reply": reply, "badge": kw.get("badge"), "table": kw.get("table"), "bullets": kw.get("bullets"), "sources": kw.get("sources", []),
            "suggestions": [s for s in kw.get("suggestions", []) if s][:4], "doc": kw.get("doc"),
            "email": kw.get("email"), "link": kw.get("link"), "awaiting_yes": kw.get("awaiting_yes", False)}


def first(c: dict) -> str:
    return c["name"].split()[0]


def find_cands(text: str) -> list[dict]:
    t = text.lower()
    out = []
    for c in db.rows("SELECT id, name FROM candidates ORDER BY id"):
        parts = [p for p in c["name"].lower().split() if len(p) > 2]
        if c["name"].lower() in t or any(re.search(rf"\b{re.escape(p)}\b", t) for p in parts[:1]):
            out.append(recruit.get_candidate(c["id"]))
    # keep the order in which names appear in the text
    def pos(c):
        m = re.search(rf"\b{re.escape(c['name'].split()[0].lower())}\b", t)
        return m.start() if m else 999
    return sorted(out, key=pos)


def find_job(text: str) -> dict | None:
    t = re.sub(r"knowledge store|talent pool", " ", text.lower())
    return recruit.find_job(t)


def job_of(c: dict, fj: dict | None = None) -> dict:
    """The job to use for a candidate: the one named, else their first application, else best fit."""
    if fj:
        return fj
    if c["applications"]:
        return recruit.get_job(c["applications"][0]["job_id"])
    return best_job(c["cv_text"], c.get("years", 0), c["name"])[0]


def best_job(cv_text: str, years: float, name: str = "x") -> tuple[dict, int]:
    best, bs = None, -1
    for j in recruit.list_jobs(status="Open"):
        s = recruit.score_texts(j, [{"id": None, "name": name, "cv_text": cv_text, "years": years}])[0]["score"]
        if s > bs:
            best, bs = j, s
    return best, bs


def met(m: dict) -> str:
    must = [r for r in m["rows"] if r["must"]]
    return f"{sum(r['status'] == 'Proven' for r in must)}/{len(must)}"


def parse_when(t: str, today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    d = None
    if "tomorrow" in t:
        d = today + timedelta(days=1)
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t) or \
        re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", t)
    if m:
        a, b = m.groups()
        day, mon = (int(a), b) if a.isdigit() else (int(b), a)
        y = today.year
        try:
            d = date(y, months.index(mon[:3]) + 1, day)
            if d < today:
                d = date(y + 1, d.month, d.day)
        except ValueError:
            d = None
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    dw = next((i for i, x in enumerate(days) if x in t), None)
    if dw is not None and d is None:
        d = today + timedelta(days=1)
        while d.weekday() != dw:
            d += timedelta(days=1)
    if d is None:
        d = today + timedelta(days=1)
        while d.weekday() == 6:
            d += timedelta(days=1)
    tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    time_s = "11:00"
    if tm:
        h = int(tm.group(1)) % 12 + (12 if tm.group(3) == "pm" else 0)
        time_s = f"{h:02d}:{tm.group(2) or '00'}"
    return str(d), time_s


def default_suggestions(ctx: dict) -> list[str]:
    out = []
    if ctx.get("cand_id"):
        try:
            c = recruit.get_candidate(ctx["cand_id"])
            out += [f"Summarize {first(c)}'s profile", f"Draft an invitation for {first(c)}"]
        except recruit.NotFound:
            pass
    if ctx.get("job_id"):
        try:
            out.append(f"Who matches {recruit.get_job(ctx['job_id'])['short']}?")
        except recruit.NotFound:
            pass
    out += ["Which candidates are awaiting interviews?", "Write a JD for a visual merchandiser in Noida with 2+ years",
            "Show the knowledge store"]
    return list(dict.fromkeys(out))[:4]


# ================================================================ JD writing
def jd_template(desc: str) -> str:
    body = re.sub(r"^(please\s+)?(can you\s+)?(write|make|create|draft|prepare|generate)\s+(me\s+)?(a\s+|an\s+)?"
                  r"(jd|job description)\s*(for)?\s*", "", desc.strip(), flags=re.I)
    tm = re.match(r"(?:an?\s+)?([A-Za-z /&-]{3,40}?)(?:\s+(?:in|at|for|based|with|who|role|position)\b|[,.]|$)", body, re.I)
    title = (tm.group(1) if tm else body.split(",")[0]).strip().title() or "New Role"
    loc = find_city(desc) or "Not stated"
    sk = skills_in(desc) or ["Customer service", "Team management"]
    yrs = (re.search(r"(\d+)\s*\+?\s*(years|yrs)", desc, re.I) or [None, "1"])[1]
    return "\n".join([
        title, f"Location: {loc}{' store' if loc != 'Not stated' else ''}",
        f"About the role: Join our {loc if loc != 'Not stated' else ''} team as a {title}. {body[:1].upper() + body[1:]}".replace("  ", " "),
        "Responsibilities:", "- Run the day-to-day work of the role to store standards.",
        "- Serve customers well and keep the floor tidy.", "- Work with the team across shifts.",
        "- Report daily numbers to the manager.",
        f"Must have: {', '.join(s.lower() for s in sk)}", "Nice to have: Hindi",
        "Qualification: Graduate or Class 12 with relevant experience", f"Experience: {yrs}+ years."])


def write_jd(desc: str) -> tuple[str, bool]:
    out = llm.generate(
        "Write a clear, fair job description for a value-retail chain in India from this request. Plain text, under "
        "190 words, no hype words, no age or gender words. Use exactly this structure:\n<Job title>\nLocation: "
        "<location or Not stated>\nAbout the role: <2 sentences>\nResponsibilities:\n- <4 to 5 bullets>\nMust have: "
        "<4 to 6 short skills, comma separated>\nNice to have: <2 to 3 short skills, comma separated>\nQualification: "
        f"<short>\nExperience: <N>+ years.\n\nRequest: {desc}")
    if out:
        out = re.sub(r"^```\w*|```$", "", out.strip()).strip()
    return (out, True) if out and "Must have" in out else (jd_template(desc), False)


def revise_jd(text: str, ask: str) -> str | None:
    return llm.generate(f"Revise this job description as asked. Keep the same structure and plain-text format. Reply "
                        f"with the full revised JD only.\n\nRequest: {ask}\n\nJD:\n{text}")


def jd_doc(text: str) -> dict:
    title = text.splitlines()[0].strip()
    f = files.make_docx(title, text)
    return {"title": title, "text": text, "file_id": f["id"], "file_name": f["name"]}


# ================================================================ actions
def rank_text(jd_text: str) -> dict:
    try:
        p = parse_jd(jd_text)
    except ParseError as e:
        return R(str(e))
    tmp = {"title": p["title"], "description": p["description"], "must": p["must"], "nice": p["nice"],
           "min_years": p["min_years"]}
    res = recruit.score_texts(tmp, db.rows("SELECT * FROM candidates"))[:5]
    if not res:
        return R("There are no candidates in the talent pool yet.")
    rows = [[i + 1, r["name"], f"{r['score']}%", met(r), ", ".join(r["missing_must"][:2]) or "None"]
            for i, r in enumerate(res)]
    f0 = res[0]["name"].split()[0]
    sugg = ["Yes, create the job", f"Summarize {f0}'s profile"]
    if len(res) > 1:
        sugg.append(f"Compare {f0} and {res[1]['name'].split()[0]}")
    return R(f"Against this JD ({p['title']}), {res[0]['name']} is the strongest at {res[0]['score']}%.",
             badge="Database", table={"head": ["#", "Candidate", "Match", "Must-haves", "Missing"], "rows": rows},
             suggestions=sugg)


def do_create_job(text: str, by: str, st: dict, file_name: str | None = None) -> dict:
    j = recruit.create_job(text, by, source="Ask AI", file_name=file_name)
    st["ctx"]["job_id"] = j["id"]
    st["ctx"].pop("jd", None)
    sg = [s for s in recruit.compute_job(j["id"], "suggested") if s["score"] >= 40][:2]
    msg = (f"Done. \"{j['title']}\" has been created with {len(j['must'])} must-have skills"
           + (f" and {j['min_years']:g}+ years" if j['min_years'] else "") + ".")
    if sg:
        msg += f" {sg[0]['name']} from your talent pool fits best ({sg[0]['score']}%)."
    return R(msg, badge="Action", link={"page": "job", "job_id": j["id"], "label": "Open job"},
             suggestions=[f"Who matches {j['short']}?",
                          f"Add {sg[0]['name'].split()[0]} to {j['short']}" if sg else None,
                          "Check this JD for bias"])


def do_add_cands(cvs: list[dict], job_id: int | None, by: str, st: dict) -> dict:
    ok, dup, bad = [], [], []
    for a in cvs:
        try:
            ok.append(recruit.create_candidate(a["text"], by, source="Ask AI", file_name=a.get("name"), job_id=job_id))
        except ValueError as e:
            (dup if "duplicate" in str(e).lower() else bad).append((a.get("name") or "file", str(e)))
    st["ctx"].pop("cvs", None)
    parts = []
    if ok:
        where = f" to {recruit.get_job(job_id)['short']}" if job_id else " to your talent pool"
        parts.append(f"Added {', '.join(c['name'] for c in ok)}{where}.")
        st["ctx"]["cand_id"] = ok[0]["id"]
    if dup:
        parts.append(f"Skipped {', '.join(d[0] for d in dup)}: already in your talent pool.")
    if bad:
        parts.append(" ".join(f"{n}: {e}" for n, e in bad))
    sugg = []
    if ok:
        c = ok[0]
        bj = best_job(c["cv_text"], c["years"], c["name"])[0] if not job_id else None
        sugg = [f"Summarize {first(c)}'s profile", f"Which jobs fit {first(c)}?",
                f"Add {first(c)} to {bj['short']}" if bj else f"Shortlist {first(c)}"]
    return R(" ".join(parts) or "Nothing was added.", badge="Action",
             link={"page": "candidate", "candidate_id": ok[0]["id"], "label": f"Open {first(ok[0])}"} if ok else None,
             suggestions=sugg)


def do_pending(st: dict, by: str) -> dict:
    p, st["pending"] = st.get("pending"), None
    if not p:
        return R("There's nothing waiting for a yes right now.", suggestions=default_suggestions(st["ctx"]))
    if p["type"] == "createJob":
        return do_create_job(p["text"], by, st, p.get("file_name"))
    if p["type"] == "addCands":
        return do_add_cands(st["ctx"].get("cvs", []), p.get("job_id"), by, st)
    if p["type"] == "approve":
        e = assist.approve_email(p["email_id"], by)
        return R(f"Sent to {e['candidate']}. It is in their candidate portal inbox now, and logged on the profile.",
                 badge="Action", suggestions=default_suggestions(st["ctx"]))
    if p["type"] == "stage":
        recruit.set_stage(p["app_id"], p["stage"], by)
        c = recruit.get_candidate(p["cid"])
        return R(f"{c['name']} → {p['stage']}. I haven't emailed anyone.", badge="Action",
                 suggestions=[f"Draft a rejection email for {first(c)}"] if p["stage"] == "Rejected" else [])
    if p["type"] == "delete_rule":
        criteria.delete(p["id"], by)
        return R(f"Removed the rule \"{p['title']}\". Scores are updated.", badge="Action")
    if p["type"] == "delete":
        kind, iid, title = p["kind"], p["id"], p["title"]
        if kind == "doc":
            knowledge.delete_doc(iid, by)
        elif kind == "job":
            recruit.delete_job(iid, by)
        elif kind == "cand":
            recruit.delete_candidate(iid, by)
        return R(f"Deleted \"{title}\".", badge="Action", suggestions=["Show the knowledge store"])
    return R("Done.")


# ================================================================ structured (database) questions
def everyone_table(t: str, fj: dict | None) -> dict | None:
    """'List all candidates with skills and gaps' (optionally filtered by job, stage, city, years)."""
    if not re.search(r"\b(list|show|all|every|give me|table)\b", t) or \
            not re.search(r"\b(candidates?|applicants?|people|talent pool|everyone|profiles)\b", t):
        return None
    ym = re.search(r"(?:more than|over|at least|above|>=?)\s*(\d+)\s*(?:\+\s*)?(?:years|yrs)", t)
    wm = re.search(r"\bwith ([a-z /&]+)", t)
    if wm and not ym and not re.search(r"gap|skill|info|detail|score|match|stage|everything|all|their|years", wm.group(1)):
        return None  # "candidates with WMS" -> skill search handles it
    stage = next((st_ for st_ in recruit.STAGES if st_.lower()[:6] in t), None)
    city = find_city(t)
    ym = re.search(r"(?:more than|over|at least|above|>=?)\s*(\d+)\s*(?:\+\s*)?(?:years|yrs)", t)
    rows = []
    jobs = {j["id"]: j for j in recruit.list_jobs()}
    for c in recruit.list_candidates():
        if city and city.lower() not in (c["location"] or "").lower():
            continue
        if ym and c["years"] < float(ym.group(1)):
            continue
        apps = c["applications"] or [None]
        for a in apps:
            if fj and (not a or a["job_id"] != fj["id"]):
                continue
            if stage and (not a or a["stage"] != stage):
                continue
            if a:
                m = recruit.match_one(a["job_id"], c["id"])
                jt, stg, sc = jobs[a["job_id"]]["short"], a["stage"], f"{m['score']}%"
                gaps = ", ".join(m["missing_must"]) or "None"
                listed = [r["skill"] for r in m["rows"] if r["status"] == "Listed" and r["must"]]
                if listed:
                    gaps += f" (only listed: {', '.join(listed)})"
            else:
                jt, stg, sc, gaps = "Talent pool", "—", "—", "—"
            proven = ", ".join(x["skill"] for x in c["skills"] if x["status"] == "Proven") or "None"
            rows.append([c["name"], jt, stg, sc, f"{c['years']:g}", c["location"], proven, gaps])
    if not rows:
        return R("No candidates match that.", badge="Database")
    bits = [b for b in [fj and f"for {fj['short']}", stage and f"in {stage}", city and f"in {city}",
                        ym and f"with {ym.group(1)}+ years"] if b]
    n = len({r[0] for r in rows})
    return R(f"{n} candidate{'s' if n != 1 else ''}{' ' + ' '.join(bits) if bits else ''}. Gaps are missing must-have "
             "skills for that job.", badge="Database",
             table={"head": ["Candidate", "Job", "Stage", "Match", "Years", "City", "Proven skills", "Gaps"],
                    "rows": rows},
             suggestions=["Which candidates are awaiting interviews?", f"Compare {rows[0][0].split()[0]} and "
                          f"{rows[1][0].split()[0]}" if len(rows) > 1 and rows[0][0] != rows[1][0] else None,
                          "Show emails waiting for approval"])


def candidate_gaps(t: str, cs: list[dict], fj: dict | None) -> dict | None:
    if len(cs) != 1 or not re.search(r"\b(gaps?|missing|skills?|strengths?|weak|lacks?)\b", t):
        return None
    c = cs[0]
    jobs_ = [fj] if fj else [recruit.get_job(a["job_id"]) for a in c["applications"]] or [job_of(c)]
    rows = []
    for j in jobs_:
        m = recruit.match_one(j["id"], c["id"])
        for r in m["rows"]:
            rows.append([j["short"], r["skill"], "Must" if r["must"] else "Nice", r["status"], r["evidence"][:90] or "—"])
    j0 = jobs_[0]
    m0 = recruit.match_one(j0["id"], c["id"])
    return R(f"{c['name']} for {j0['title']}: {m0['score']}% match. Gaps: {', '.join(m0['missing_must']) or 'no missing must-haves'}."
             + (f" {m0['tips'][0]}" if m0["tips"] else ""), badge="Database",
             table={"head": ["Job", "Skill", "Type", "Status", "Proof from CV"], "rows": rows},
             link={"page": "candidate", "candidate_id": c["id"], "job_id": j0["id"], "label": f"Open {first(c)}"},
             suggestions=[f"Generate interview questions for {first(c)}", f"Which jobs fit {first(c)}?"])


def email_list(t: str) -> dict | None:
    if not re.search(r"\bemails?\b", t) or not re.search(r"pending|waiting|approv|draft|list|show|sent|all", t) \
            or re.search(r"\b(draft|write) (an?|the)\b", t):
        return None
    status = "Draft" if re.search(r"pending|waiting|draft|not approved", t) else "Sent" if re.search(r"approved|sent", t) else None
    es = assist.list_emails(status=status)
    rows = [[e["candidate"], e["job_title"], e["type_label"], e["status"], e["approved_by"] or "—"] for e in es]
    return R(f"{len(rows)} email{'s' if len(rows) != 1 else ''}{' waiting for approval' if status == 'Draft' else ''}."
             if rows else "No emails here.", badge="Database",
             table={"head": ["Candidate", "Job", "Type", "Status", "Sent by"], "rows": rows} if rows else None)


def data_snapshot() -> str:
    """Compact text copy of the whole database, so the AI can answer anything from any page."""
    out = ["JOBS:"]
    for j in recruit.list_jobs():
        out.append(f"- {j['title']} | {j['location']} | {j['status']} | min {j['min_years']:g} yrs | must: "
                   f"{', '.join(j['must'])} | nice: {', '.join(j['nice'])} | stages: "
                   + ", ".join(f"{k} {v}" for k, v in j["stage_counts"].items() if v))
    out.append("CANDIDATES:")
    for c in recruit.list_candidates():
        out.append(f"- {c['name']} | {c['headline']} | {c['location']} | {c['years']:g} yrs | {c['education']} | "
                   f"proven: {', '.join(x['skill'] for x in c['skills'] if x['status'] == 'Proven') or 'none'} | "
                   f"listed only: {', '.join(x['skill'] for x in c['skills'] if x['status'] == 'Listed') or 'none'}")
        for a in c["applications"]:
            m = recruit.match_one(a["job_id"], c["id"])
            out.append(f"    applied {a['job_title']}: stage {a['stage']}, match {m['score']}%, "
                       f"missing must-haves: {', '.join(m['missing_must']) or 'none'}")
    out.append("INTERVIEWS:")
    for i in interviews.list_all():
        out.append(f"- {i['candidate']} | {i['job_title']} | {i['date']} {i['time']} | {i['mode']} | "
                   f"{i['interviewer']} | {i['status']} | feedback: {'yes' if i['has_feedback'] else 'no'}")
    for f in db.rows("SELECT f.text, f.by_name, c.name, j.title FROM interview_feedback f JOIN applications a ON "
                     "a.id=f.application_id JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id"):
        out.append(f"  feedback on {f['name']} ({f['title']}) by {f['by_name']}: {f['text']}")
    out.append("EMAILS:")
    for e in assist.list_emails():
        if e["direction"] == "in":
            out.append(f"- MESSAGE FROM {e['candidate']} ({e['job_title']}), {'unread' if not e.get('read_at') else 'read'}: "
                       f"{e['body'][:300]}")
        else:
            out.append(f"- {e['type_label']} to {e['candidate']} ({e['job_title']}): {e['status']}")
    for i in db.rows("SELECT i.candidate_response, i.candidate_note, c.name, j.title FROM interviews i JOIN applications a "
                     "ON a.id=i.application_id JOIN candidates c ON c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id "
                     "WHERE i.candidate_response IS NOT NULL"):
        out.append(f"- {i['name']} answered the {i['title']} interview: {i['candidate_response']} {i['candidate_note'] or ''}")
    out.append(criteria.snapshot())
    out.append("NOTES:")
    for n in db.rows("SELECT n.text, c.name FROM notes n JOIN candidates c ON c.id=n.candidate_id"):
        out.append(f"- {n['name']}: {n['text']}")
    return "\n".join(out)


def _days_since(ts: str | None) -> int:
    try:
        return max(0, (date.today() - datetime.fromisoformat(str(ts)[:19]).date()).days)
    except (ValueError, TypeError):
        return 0


def insights(text: str, cs: list[dict], fj: dict | None, ctx: dict) -> dict | None:
    """Specific answers straight from the data. They work with or without the AI key."""
    t = text.lower()
    c = cs[0] if cs else None

    # what needs me today / priorities
    if re.search(r"what (should i|do i|needs? me)|priorit|urgent|to-?do\b|next step|need(s)? (me|my attention)|pending work|do today|for today", t) \
            and not c and not re.search(r"\bask\b|question", t):
        needs = analytics.dashboard()["needs"]
        if not needs:
            return R("You are all caught up. Nothing needs you right now.", badge="Database",
                     suggestions=default_suggestions(ctx))
        kinds = {}
        for n in needs:
            kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
        top = needs[0]
        word = {"Decide": "to decide", "Feedback": "need feedback", "Schedule": "to book", "Screen": "CVs to review"}
        return R(f"{len(needs)} things need you. Start with: {top['text']}. "
                 + ", ".join(f"{v} {word[k]}" for k, v in kinds.items()) + ".", badge="Database",
                 table={"head": ["#", "What to do", "Type"], "rows": [[i + 1, n["text"], n["kind"]] for i, n in enumerate(needs)]},
                 link={"page": "dashboard", "label": "Open Home"},
                 suggestions=default_suggestions(ctx))

    # waiting too long
    if re.search(r"waiting too long|stuck|delayed|overdue|too long|stale|no (action|update)|left behind", t):
        rows = db.rows("SELECT a.stage, a.updated_at, c.name, j.title FROM applications a JOIN candidates c ON "
                       "c.id=a.candidate_id JOIN jobs j ON j.id=a.job_id WHERE a.stage IN ('Applied','Screening','Shortlisted')")
        late = sorted([(r, _days_since(r["updated_at"])) for r in rows], key=lambda x: -x[1])
        late = [x for x in late if x[1] >= 3]
        if not late:
            return R("No one has been waiting more than 2 days. Good.", badge="Database", suggestions=default_suggestions(ctx))
        return R(f"{len(late)} people have waited 3 days or more. The longest is {late[0][0]['name']} ({late[0][1]} days "
                 f"in {ui_label(late[0][0]['stage'])}). Move them on before they accept another offer.", badge="Database",
                 table={"head": ["Candidate", "Job", "Stage", "Days"],
                        "rows": [[r["name"], r["title"], ui_label(r["stage"]), d] for r, d in late]},
                 suggestions=[f"Summarize {r['name'].split()[0]}'s profile" for r, _ in late[:2]] + ["What should I do today?"])

    # who should I hire / overall recommendation
    if re.search(r"who should i (hire|pick|choose|select|call|interview|shortlist)|recommend|best (candidate|person|hire|overall)|"
                 r"hire first|top pick", t) and not c:
        jobs = [fj] if fj else recruit.list_jobs(status="Open")
        rows, picks = [], []
        for j in jobs:
            res = [r for r in recruit.compute_job(j["id"]) if r["stage"] != "Rejected"][:1]
            if not res:
                continue
            r = res[0]
            m = recruit.match_one(j["id"], r["candidate_id"])
            why = (f"{met(m)} must-haves, " if m["rows"] else "") + (f"missing {', '.join(m['missing_must'])}" if m["missing_must"] else "no must-have gaps")
            rows.append([j["title"], r["name"], f"{r['score']}%", why, ui_label(r["stage"])])
            picks.append((r["score"], r["name"], j["title"], bool(m["missing_must"])))
        if not rows:
            return R("No one has applied yet, so there is nobody to recommend.", badge="Database")
        picks.sort(reverse=True)
        s0 = picks[0]
        return R(f"My pick: {s0[1]} for {s0[2]} ({s0[0]}%)"
                 + (" but check the gap first." if s0[3] else ", with no must-have gaps.")
                 + " One top person per job is below. The score is a guide. You decide.", badge="Database",
                 table={"head": ["Job", "Top candidate", "Match", "Why", "Stage"], "rows": rows},
                 suggestions=[f"Why is {s0[1].split()[0]} a good fit?", f"What should I ask {s0[1].split()[0]} in the interview?"])

    # why is X a good fit / explain the score
    if c and re.search(r"\bwhy\b|explain|reason|how (well|good)|good fit|suit|score|strong|weak", t) \
            and not re.search(r"\bask\b|question", t):
        j = job_of(c, fj)
        m = recruit.match_one(j["id"], c["id"])
        proven = [r for r in m["rows"] if r["status"] == "Proven"]
        listed = [r for r in m["rows"] if r["status"] == "Listed"]
        miss = [r for r in m["rows"] if r["status"] == "Missing"]
        fitw = "a strong match" if m["score"] >= 70 else "a fair match" if m["score"] >= 50 else "a weak match"
        pts = [f"Score {m['score']}% for {j['title']}: {fitw}.",
               f"Skills: proven {', '.join(r['skill'] for r in proven) or 'none'}"
               + (f"; only listed (not shown in work) {', '.join(r['skill'] for r in listed)}" if listed else "") + ".",
               f"Gaps: {', '.join(r['skill'] for r in miss) or 'none'}.",
               f"Experience: {c['years']:g} years, the job asks {j['min_years']:g}+ ({'meets it' if m['meets_years'] else 'below it'}).",
               ]
        ev = next((r for r in proven if r.get("evidence")), None)
        if ev:
            pts.append(f"Proof from the CV for {ev['skill']}: \"{str(ev['evidence'])[:140]}\"")
        verdict = ("Worth an interview." if m["score"] >= 60 and not m["missing_must"] else
                   "Interview, but ask about " + ", ".join(m["missing_must"]) + "." if m["score"] >= 50 else
                   "Probably not for this job. Check other jobs.")
        return R(f"{c['name']} is {fitw} for {j['title']} ({m['score']}%). " + verdict, badge="Database",
                 bullets=pts, link={"page": "candidate", "candidate_id": c["id"], "job_id": j["id"], "label": f"Open {first(c)}"},
                 suggestions=[f"What should I ask {first(c)} in the interview?", f"Draft an invitation for {first(c)}",
                              f"Compare {first(c)} and " + (cs[1]["name"].split()[0] if len(cs) > 1 else "another candidate")])

    # interview questions for X
    if c and re.search(r"\bask\b|question|interview (plan|prep)|prepare", t):
        j = job_of(c, fj)
        qs = assist.questions(j["id"], c["id"])["questions"]
        return R(f"{len(qs)} questions for {c['name']} ({j['title']}). Start with the Verification ones: they test the CV claims.",
                 badge="Database", table={"head": ["Type", "Question", "A good answer"],
                                          "rows": [[q.get("type", ""), q["question"], q.get("good_answer", "")] for q in qs]},
                 suggestions=[f"Draft an invitation for {first(c)}", f"Why is {first(c)} a good fit?"])

    # tell me about X (candidate)
    if c and re.search(r"tell me about|who is|about\b|profile|summar|background|details|overview", t):
        j = job_of(c, fj)
        sm = assist.summary(j["id"], c["id"])["text"]
        apps = ", ".join(f"{a['job_title']} ({ui_label(a['stage'])})" for a in c["applications"]) or "not added to any job"
        return R(f"{c['name']}: {c['headline']}, {c['location']}. Applied to: {apps}.\n\n{sm}", badge="Database",
                 link={"page": "candidate", "candidate_id": c["id"], "job_id": j["id"], "label": f"Open {first(c)}"},
                 suggestions=[f"Why is {first(c)} a good fit?", f"What should I ask {first(c)} in the interview?"])

    # tell me about a job
    if fj and not c and re.search(r"tell me about|about\b|details|describe|overview|summar|what does|requirements|needs?|hiring for|status|pipeline|how many", t):
        res = [r for r in recruit.compute_job(fj["id"]) if r["stage"] != "Rejected"]
        sc = ", ".join(f"{v} {ui_label(k).lower()}" for k, v in fj["stage_counts"].items() if v) or "no applicants yet"
        return R(f"{fj['title']} in {fj['location']}. {('Wants ' + format(fj['min_years'], 'g') + '+ years. ') if fj['min_years'] else 'No minimum experience. '}Pipeline: {sc}. "
                 + (f"Best so far: {res[0]['name']} ({res[0]['score']}%)." if res else ""), badge="Database",
                 bullets=[f"Must-have: {', '.join(fj['must']) or 'none'}", f"Nice to have: {', '.join(fj['nice']) or 'none'}"],
                 link={"page": "job", "job_id": fj["id"], "label": f"Open {fj['short']}"},
                 suggestions=[f"Who matches {fj['short']}?", f"Who should I hire for {fj['short']}?"])
    return None


def ui_label(stage: str) -> str:
    return {"Applied": "New", "Screening": "Reviewing", "Selected": "Hired", "Rejected": "Not selected"}.get(stage, stage)


def busy_reply(ctx) -> dict:
    return R("The AI service (Google Gemini free tier) is busy right now, so I could not write this one. "
             "Please try again in a few seconds. Questions about your data still work instantly.",
             suggestions=default_suggestions(ctx))


def menu_reply(ctx: dict) -> dict:
    jobs = recruit.list_jobs(status="Open")
    ex = [f"Who matches {jobs[0]['short']}?"] if jobs else []
    return R("That is not in the data I have, or I did not understand. Here are things I can answer with your real data:",
             bullets=["Who should I hire first and why?", "What should I do today?", "Who is waiting too long?",
                      "Why is <name> a good fit? / What should I ask <name>?", "Compare <name> and <name>",
                      "Which candidates know <skill>? / Policy questions (shifts, notice, joining documents)"],
             suggestions=(ex + ["What should I do today?", "Who should I hire first and why?"])[:4])



def structured(text: str, cs: list[dict], fj: dict | None) -> dict | None:
    t = text.lower()
    for fn in (lambda: everyone_table(t, fj) if len(cs) < 2 else None, lambda: candidate_gaps(t, cs, fj),
               lambda: email_list(t)):
        r = fn()
        if r:
            return r
    if re.search(r"\bcompare\b|\bvs\.?\b|versus", t) and len(cs) >= 2:
        two = cs[:3]
        j = fj or job_of(two[0])
        ms = [recruit.match_one(j["id"], c["id"]) for c in two]
        rows = [["Match", *[f"{m['score']}%" for m in ms]], ["Must-haves proven", *[met(m) for m in ms]],
                ["Experience", *[f"{c['years']:g} yrs" for c in two]],
                ["Stage", *[m["stage"] or "Not added" for m in ms]],
                ["Missing must-haves", *[", ".join(m["missing_must"]) or "None" for m in ms]]]
        lead = max(zip(two, ms), key=lambda x: x[1]["score"])
        return R(f"Comparison for {j['title']}. {lead[0]['name']} leads at {lead[1]['score']}%.", badge="Database",
                 table={"head": ["", *[c["name"] for c in two]], "rows": rows},
                 suggestions=[f"Shortlist {first(lead[0])}", f"Summarize {first(lead[0])}'s profile"])
    if re.search(r"\b(top|best|rank|strongest|shortlist me)\b", t) or \
            (re.search(r"(who|which candidates?).*(match|fit|suit)|match(es)? (for|the)", t) and fj):
        if not fj:
            fm = re.search(r"\bfor (?:an? |the )?([a-z ]+?)(?: role| job| position| opening)?\??$", t)
            if fm:
                titles = ", ".join(j["title"] for j in recruit.list_jobs())
                return R(f"That's not in the data. There is no \"{fm.group(1).strip()}\" job. Open jobs: {titles}.",
                         badge="Database")
            return None
        n = min(10, int((re.search(r"\b(\d{1,2})\b", t) or [None, 5])[1]))
        res = recruit.compute_job(fj["id"])[:n]
        sg = [s for s in recruit.compute_job(fj["id"], "suggested") if s["score"] >= 50][:2]
        if not res:
            msg = f"No one has applied to {fj['title']} yet."
        else:
            msg = f"For {fj['title']}, {res[0]['name']} leads with {res[0]['score']}%."
        if sg:
            msg += f" {' and '.join(s['name'] for s in sg)} from your talent pool also fit."
        sugg = []
        if res:
            sugg.append(f"Shortlist {res[0]['name'].split()[0]} for {fj['short']}")
        if len(res) > 1:
            sugg.append(f"Compare {res[0]['name'].split()[0]} and {res[1]['name'].split()[0]}")
        if sg:
            sugg.append(f"Add {sg[0]['name'].split()[0]} to {fj['short']}")
        return R(msg, badge="Database", link={"page": "job", "job_id": fj["id"], "label": f"Open {fj['short']}"},
                 table={"head": ["#", "Candidate", "Match", "Must-haves", "Stage"],
                        "rows": [[i + 1, r["name"], f"{r['score']}%", met(r), r["stage"]] for i, r in enumerate(res)]},
                 suggestions=sugg)
    if "interview" in t and re.search(r"await|waiting|pending|upcoming|scheduled|who|which|list|this week|today", t) \
            and "question" not in t:
        ivs = interviews.list_all("upcoming") if not re.search(r"\ball\b", t) else interviews.list_all()
        if "this week" in t:
            end = str(date.today() + timedelta(days=7))
            ivs = [i for i in ivs if i["date"] <= end]
        if "today" in t:
            ivs = [i for i in ivs if i["date"] == str(date.today())]
        rows = [[i["candidate"], i["job_title"], f"{i['date']} {i['time']}", i["interviewer"] or "—", i["status"]]
                for i in ivs]
        no_iv = db.rows("SELECT c.name, j.title FROM applications a JOIN candidates c ON c.id=a.candidate_id JOIN jobs j "
                        "ON j.id=a.job_id WHERE a.stage IN ('Shortlisted','Interview') AND a.id NOT IN "
                        "(SELECT application_id FROM interviews)")
        rows += [[r["name"], r["title"], "Not scheduled", "—", "Needs a slot"] for r in no_iv]
        msg = f"{len(rows)} candidate{'s' if len(rows) != 1 else ''} awaiting interviews." if rows else \
            "No one is waiting for an interview."
        return R(msg, badge="Database", table={"head": ["Candidate", "Job", "When", "Interviewer", "Status"], "rows": rows}
                 if rows else None, suggestions=[f"Draft a reminder for {rows[0][0].split()[0]}"] if rows else [])
    if re.search(r"screen|new applicant|\bapplied\b", t) and re.search(r"await|waiting|pending|need|who|which|not|list", t):
        r = db.rows("SELECT c.name, j.title, a.stage, m.score FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                    "JOIN jobs j ON j.id=a.job_id LEFT JOIN match_results m ON m.application_id=a.id "
                    "WHERE a.stage IN ('Applied','Screening') ORDER BY m.score DESC")
        return R(f"{len(r)} awaiting screening." if r else "Nobody is waiting for screening.", badge="Database",
                 table={"head": ["Candidate", "Job", "Stage", "Match"],
                        "rows": [[x["name"], x["title"], x["stage"], f"{x['score']}%"] for x in r]} if r else None)
    if re.search(r"(most|highest|fewest|least) (applica|candidates)|applications (per|by) job|which job.*(popular|busiest)"
                 r"|how many (applica|candidates)", t):
        js = sorted(recruit.list_jobs(), key=lambda j: -j["applicants"])
        total = db.one("SELECT COUNT(*) n FROM candidates")["n"]
        return R(f"You have {total} candidates and {sum(j['applicants'] for j in js)} applications across "
                 f"{len(js)} jobs. {js[0]['title']} has the most.", badge="Database",
                 table={"head": ["Job", "Applications", "Shortlisted+"],
                        "rows": [[j["title"], j["applicants"], j["stage_counts"]["Shortlisted"] + j["stage_counts"]["Interview"]
                                  + j["stage_counts"]["Selected"]] for j in js]})
    if re.search(r"(list|show|which|what).*(open )?(jobs|roles|openings)\b", t) and not cs:
        js = recruit.list_jobs()
        return R(f"You have {len(js)} jobs.", badge="Database",
                 table={"head": ["Job", "Location", "Min years", "Applicants", "Status"],
                        "rows": [[j["title"], j["location"], f"{j['min_years']:g}+", j["applicants"], j["status"]] for j in js]},
                 suggestions=[f"Who matches {js[0]['short']}?"] if js else [])
    sk = re.search(r"(?:candidates?|people|who) (?:with|has|have|knows?) ([a-z /&]+?)\??$", t)
    if sk and not cs and len(sk.group(1).split()) <= 3 and \
            not re.search(r"\b(most|least|best|and|what|which|more|less)\b", sk.group(1)):
        skill = sk.group(1).strip()
        found = recruit.list_candidates(skill=skill) or [c for c in recruit.list_candidates()
                                                       if any(skill in s["skill"].lower() for s in c["skills"])]
        rows = []
        for c in found:
            s = next((x for x in c["skills"] if skill.lower() in x["skill"].lower()), None)
            rows.append([c["name"], c["headline"], s["status"] if s else "—"])
        return R(f"{len(rows)} candidate{'s' if len(rows) != 1 else ''} with {skill}." if rows else
                 f"No candidate shows {skill} in their CV.", badge="Database",
                 table={"head": ["Candidate", "Current role", "Proof"], "rows": rows} if rows else None)
    if re.search(r"which jobs? fits?|best job for|jobs? for", t) and cs:
        c = cs[0]
        rows = []
        for j in recruit.list_jobs(status="Open"):
            m = recruit.match_one(j["id"], c["id"])
            rows.append([j["title"], f"{m['score']}%", met(m), m["stage"] or "Not added"])
        rows.sort(key=lambda r: -int(r[1][:-1]))
        return R(f"Best fit for {c['name']}: {rows[0][0]} ({rows[0][1]}).", badge="Database",
                 table={"head": ["Job", "Match", "Must-haves", "Stage"], "rows": rows},
                 suggestions=[f"Add {first(c)} to {rows[0][0].split(' /')[0]}"] if rows[0][3] == "Not added" else [])
    if re.search(r"summar|tell me about|profile of|who is", t) and cs:
        c = cs[0]
        j = job_of(c, fj)
        s = assist.summary(j["id"], c["id"])
        m = recruit.match_one(j["id"], c["id"])
        return R(f"{c['name']} for {j['title']} ({m['score']}% match):\n{s['text']}", badge="Database",
                 link={"page": "candidate", "candidate_id": c["id"], "job_id": j["id"], "label": f"Open {first(c)}"},
                 suggestions=[f"Generate interview questions for {first(c)}", f"Shortlist {first(c)}",
                              f"Draft an invitation for {first(c)}"])
    if "question" in t and (cs or fj):
        c = cs[0] if cs else None
        j = fj or job_of(c)
        if c:
            qs = assist.questions(j["id"], c["id"])["questions"]
        else:
            qs = [{"type": "Technical", "skill": s, "question": f"Walk me through how you handled {s.lower()} on a busy day."}
                  for s in j["must"][:3]] + [{"type": "HR", "skill": "Teamwork",
                                              "question": "Tell me about a conflict in your team and how you solved it."}]
        return R(f"Interview questions for {c['name'] + ' · ' if c else ''}{j['title']}:", badge="Database",
                 table={"head": ["Type", "Skill", "Question"], "rows": [[q.get("type", ""), q.get("skill", ""),
                                                                        q.get("question", "")] for q in qs]},
                 suggestions=[f"Draft an invitation for {first(c)}"] if c else [])
    return None


# ================================================================ screening criteria (rules)
ALL_JOBS = r"\b(all (jobs|roles|positions)|every (job|role)|whole (process|hiring)|global|all hiring|every candidate)\b"


def criteria_intent(text: str, t: str, fj: dict | None, ctx: dict, st: dict, by: str) -> dict | None:
    # careful: "rules for rescheduling" is a policy question, not a screening rule
    is_rule = re.search(r"criteri|\b(shortlist\w*|screening|hiring|matching|job|my|these|extra) rules?\b|\brule\s*#?\s*\d"
                        r"|\brules? for (all|every)|\b(add|set|create|new|make|save|remove|delete|turn off|disable|enable"
                        r"|turn on)\b (a |an |new |the |this |that )*(shortlisting |screening )?rule\b|^\s*rule\s*:", t) \
        or (re.search(r"\brules?\b", t) and fj and not re.search(r"reschedul|leave|shift|joining|policy", t))
    # --- who meets / fails the rules
    if is_rule and re.search(r"\b(meet|meets|fail|fails|passes|pass|match(es)?)\b", t) and \
            re.search(r"\b(who|which|list|show|candidates?)\b", t):
        j = fj or (recruit.get_job(ctx["job_id"]) if ctx.get("job_id") else None)
        if not j:
            return R("Which job? For example: \"Who doesn't meet the criteria for Store Manager?\"")
        res = recruit.compute_job(j["id"])
        rules = criteria.list_for(j["id"], active_only=True)
        if not rules:
            return R(f"{j['title']} has no extra criteria yet. Add one like: "
                     f"\"Add rule for {j['short']}: must live in Delhi NCR\".", suggestions=[
                         f"Add rule for {j['short']}: prefer candidates with festive season experience +10 points"])
        rows = [[r["name"], f"{r['score']}%", f"{r['criteria_adj']:+d}",
                 "Yes" if r["meets_criteria"] else "No: " + "; ".join(r["criteria_failed"]),
                 "; ".join(f"{c['text'][:30]}: {c['status']}" for c in r["criteria"])] for r in res]
        bad = [r for r in res if not r["meets_criteria"]]
        return R(f"{len(res) - len(bad)} of {len(res)} applicants for {j['title']} meet every must-have rule.",
                 badge="Database", table={"head": ["Candidate", "Match", "Rules +/-", "Meets must rules", "Each rule"],
                                          "rows": rows},
                 suggestions=[f"Show the criteria for {j['short']}"])
    # --- list rules
    if is_rule and re.search(r"\b(show|list|what|which|see|view)\b", t) and not re.search(r"\b(add|set|create)\b", t):
        if re.search(ALL_JOBS, t) or not (fj or ctx.get("job_id")):
            rows_ = criteria.list_all()
            title = "all jobs"
        else:
            j = fj or recruit.get_job(ctx["job_id"])
            rows_ = criteria.list_for(j["id"])
            title = j["title"]
        if not rows_:
            return R(f"No extra criteria for {title} yet. Tell me one, like \"Add rule for all jobs: must be "
                     "Class 12 or above\".", suggestions=["Add rule for all jobs: prefer candidates in Delhi NCR +5 points"])
        return R(f"{len(rows_)} rule{'s' if len(rows_) != 1 else ''} for {title}. Must rules flag people who miss them "
                 "(they're listed last, never auto-rejected). Bonus/penalty rules change the score.", badge="Database",
                 table={"head": ["#", "Applies to", "Rule", "How it's checked", "On"],
                        "rows": [[r["id"], r.get("job_title") or ("All jobs" if r["job_id"] is None else title),
                                  r["text"], r["how"], "Yes" if r["active"] else "No"] for r in rows_]},
                 suggestions=[f"Remove rule {rows_[0]['id']}", "Who doesn't meet the criteria?"])
    # --- remove / turn off
    m = re.search(r"\b(remove|delete|drop|turn off|disable|turn on|enable)\b", t)
    if is_rule and m:
        num = re.search(r"\b(?:rule|criteri\w*)\s*#?\s*(\d+)\b", t)
        target = None
        if num:
            target = db.one("SELECT * FROM criteria WHERE id=?", (int(num.group(1)),))
        else:
            words = [w for w in re.findall(r"[a-z]+", t) if len(w) > 3 and w not in
                     ("remove", "delete", "drop", "turn", "rule", "rules", "criteria", "criterion", "disable", "enable")]
            best, bs = None, 0
            for r in db.rows("SELECT * FROM criteria"):
                sc = sum(w in r["text"].lower() for w in words)
                if sc > bs:
                    best, bs = r, sc
            target = best
        if not target:
            return R("I couldn't tell which rule. Say \"show the criteria\" and use its number, like \"remove rule 2\".")
        if m.group(1) in ("turn off", "disable", "turn on", "enable"):
            on = m.group(1) in ("turn on", "enable")
            criteria.update(target["id"], by, active=on)
            return R(f"Turned {'on' if on else 'off'}: \"{target['text']}\". Scores are updated.", badge="Action")
        st["pending"] = {"type": "delete_rule", "id": target["id"], "title": target["text"]}
        return R(f"Remove the rule \"{target['text']}\"? Scores will be updated.", awaiting_yes=True,
                 suggestions=["Yes, remove it", "Cancel"])
    # --- AI guidelines for the whole process
    g = re.search(r"\b(add|set|save)\b.*\b(guideline|instruction)s?\b\s*:?(.*)", text, re.I)
    if g and g.group(3).strip():
        cur = criteria.guidelines()
        new = (cur + "\n" if cur else "") + "- " + g.group(3).strip().lstrip(":").strip()
        db.set_setting("ai_guidelines", new[:3000])
        return R("Saved. The AI will follow this in summaries, questions, emails and answers. "
                 "You can edit all guidelines in Settings → Screening rules.", badge="Action")
    # --- add a rule
    if is_rule and re.search(r"\b(add|set|create|new|make|save)\b", t) or re.match(r"^\s*(rule|criteri\w*)\s*:", t):
        body = text.split(":", 1)[1].strip() if ":" in text else re.sub(
            r"^.*?\b(rules?|criteri\w*|conditions?)\b\s*(for [^,]+?(,|that|to)\s*)?", "", text, flags=re.I).strip()
        if len(body) < 3:
            return R("Tell me the rule after a colon, for example: \"Add rule for Cashier: must live in Ghaziabad\".")
        head = text.split(":", 1)[0].lower() if ":" in text else t
        job = None if re.search(ALL_JOBS, head) else (find_job(head) or (recruit.get_job(ctx["job_id"])
                                                                          if ctx.get("job_id") else None))
        c = criteria.create(body, job["id"] if job else None, by)
        where = job["title"] if job else "all jobs"
        jid = job["id"] if job else None
        rank = recruit.compute_job(jid) if jid else []
        top = f" {rank[0]['name']} now leads at {rank[0]['score']}%." if rank else ""
        return R(f"Added a rule for {where}: \"{c['text']}\".\nHow I check it: {c['how']}.{top}", badge="Action",
                 link={"page": "job", "job_id": jid, "label": f"Open {job['short']}"} if job else None,
                 suggestions=[f"Who doesn't meet the criteria for {job['short']}?" if job else "Show the criteria for all jobs",
                              f"Remove rule {c['id']}"])
    return None


# ================================================================ router
FOLLOW = re.compile(r"^(and |also |then |ok |okay |now |so )?(write|make|give|turn|rewrite|shorten|expand|explain|summari[sz]e|elaborate|"
                    r"continue|more|why|how come|what about|can you|could you|please|tell me more|in short|short|simpler|"
                    r"in simple|a paragraph|one line|bullet|list them|compare them|which one|who among)\b")


def _is_followup(t: str, cs: list, fj) -> bool:
    """Short messages that lean on the chat so far ('write a paragraph', 'make it shorter')."""
    if len(t.split()) > 14 or cs or fj:
        return False
    if re.search(r"\b(jd|job description|email|mail|interview|schedule|shortlist|reject|add|create|delete|upload)\b", t):
        return False
    return bool(FOLLOW.search(t))


def _hist_text(st: dict, n: int = 6) -> str:
    out = []
    for m in (st.get("history") or [])[-n:]:
        if m["role"] == "user":
            out.append(f"Recruiter: {m.get('text', '')}")
        else:
            line = m.get("reply") or m.get("text") or ""
            tb = m.get("table")
            if tb and tb.get("rows"):
                line += " Table: " + "; ".join(" | ".join(str(c) for c in r) for r in tb["rows"][:8])
            if m.get("bullets"):
                line += " " + " ".join(str(b) for b in m["bullets"][:6])
            out.append(f"Assistant: {line[:700]}")
    return "\n".join(out) or "none"


NEXT_RULE = ("\nLAST LINE: write 'NEXT:' then 3 short, useful follow-up questions the recruiter may ask next, "
             "separated by ' | '. Nothing after it.")


def _split_next(full: str) -> tuple[str, list[str]]:
    """Separate the AI's text from its 'NEXT: a | b | c' follow-up ideas."""
    m = re.search(r"\n?\s*NEXT:\s*(.*)$", full or "", re.S)
    if not m:
        return (full or "").strip(), []
    sug = [x.strip(" -*\"'") for x in re.split(r"\s*\|\s*|\n", m.group(1)) if x.strip(" -*\"'")]
    return full[:m.start()].strip(), [x for x in sug if len(x) < 90][:3]


def _wrap_prompt(out: dict, text: str, st: dict) -> str | None:
    """Ask the AI to explain a ready data answer in friendly words (so every answer is AI-written)."""
    if not llm.get_llm() or out.get("badge") not in ("Database", "Documents") or out.get("email") or out.get("doc") \
            or out.get("awaiting_yes") or st.get("pending") or not out.get("reply"):
        return None
    data = out["reply"]
    if out.get("bullets"):
        data += "\n" + "\n".join(f"- {b}" for b in out["bullets"][:8])
    tb = out.get("table")
    if tb and tb.get("rows"):
        data += "\nTable columns: " + ", ".join(tb["head"]) + "\n" + "\n".join(" | ".join(str(c) for c in r) for r in tb["rows"][:10])
    return ("You are HireMate, a friendly recruiting assistant for the Vishal Mega Mart HR team. The system already looked up "
            "the facts below from the database. Explain them like ChatGPT would: very simple words, warm and clear. "
            "FORMAT (markdown): '**Answer:** one short sentence', then '### Why' with 2 to 4 bullets (bold the names), then "
            "'### Next step' with one action. Use ONLY the facts in DATA; never invent names or numbers. A table is shown "
            "separately, so do not repeat it. Under 120 words." + NEXT_RULE +
            f"\n\nCONVERSATION SO FAR:\n{_hist_text(st, 4)}\n\nRECRUITER ASKED: {text}\n\nDATA:\n{data[:2500]}")


def _apply_wrap(out: dict, ai_text: str) -> dict:
    body, sug = _split_next(ai_text)
    if not body:
        return out
    out = dict(out)
    out.update(reply=body, bullets=None, badge="AI + Database")
    if sug:
        out["suggestions"] = sug
    return out


WRITE = re.compile(r"\b(write|draft|compose|rewrite|rephrase|reword|proofread|translate|improve|polish|paragraph|message|"
                   r"announcement|speech|post|caption|template|tips?|ideas?|advice)\b")
DATA = re.compile(r"\b(candidates?|applicants?|jobs?|roles?|scores?|match(es|ed)?|interviews?|stages?|shortlist\w*|"
                  r"applied|knowledge|polic(y|ies)|our|waiting|pending|today|top|who|whom|which|experience|notice|years?|salary|"
                  r"hire|hired|email|them|him|her|his|their|this|these|those|it)\b")


def _pure_writing(text: str) -> bool:
    """A general writing / advice request that needs no database facts (so no borrowed names)."""
    t = text.lower()
    return bool(WRITE.search(t)) and not DATA.search(t)


def _llm_answer(text: str, st: dict, ctx: dict) -> dict | None:
    if _pure_writing(text) and not _is_followup(text.lower(), [], None):
        prompt = ("You are HireMate, a friendly writing and HR assistant for the Vishal Mega Mart HR team. Answer like ChatGPT: "
                  "do exactly what the recruiter asks, in very simple words, in clean markdown.\n"
                  "RULES: This is a general task. Do NOT use any real candidate, employee or job names from anywhere; "
                  "use placeholders like [Name], [Store], [City], [Date] where a detail is needed. Never invent facts, "
                  "numbers or policies. No citations. No filler. Do not repeat the question. "
                  "For writing tasks, give only the finished text (short, ready to use). For advice, use 3 to 6 short bullets." + NEXT_RULE + "\n\n"
                  f"CONVERSATION SO FAR:\n{_hist_text(st, 4)}\n\nRECRUITER NOW: {text}")
        if getattr(_MODE, "stream", False):
            return {"_stream": {"prompt": prompt, "src": [], "ctx": dict(ctx), "badge": "AI writing"}}
        out = llm.generate(prompt, max_tokens=700)
        if not out:
            return None
        body, sug = _split_next(out)
        return R(body, badge="AI writing", suggestions=sug or default_suggestions(ctx))
    hits = knowledge.retrieve(text, k=3)
    docs = "\n".join(f"[{i + 1}] {h['meta']['title']}: {h['text']}" for i, h in enumerate(hits))
    prompt = ("You are HireMate, a sharp, friendly recruiting assistant for the Vishal Mega Mart HR team. Talk like ChatGPT: "
              "understand what the recruiter means from the conversation so far, and do what they ask, including writing tasks "
              "(a paragraph, a summary, a message, a comparison, advice) using ONLY the data below for facts. "
              "Short follow-ups such as 'write a paragraph', 'make it shorter' or 'why' refer to your last answer.\n"
              "Write in very simple words. Always name the specific people, jobs, scores, skills and dates. Never invent people or numbers. "
              "No filler, do not repeat the question.\n"
              "FORMAT (markdown): for questions, use '**Answer:** one short sentence', then '### Why' with 2 to 4 bullets (bold the names), "
              "then '### Next step' with one action. For writing tasks (paragraph, summary, message) just write the text, no headings. "
              "Use a markdown table only when comparing 2 or more people. Keep it under 150 words. Cite documents like [1]. "
              "If the data really has no answer, say 'That is not in the data.' and list what you can answer, as bullets." + NEXT_RULE +
              f"\n\nCONVERSATION SO FAR:\n{_hist_text(st)}\n\nDATABASE:\n{data_snapshot()}\n\nDOCUMENTS:\n{docs or 'none'}"
              f"\n\nRECRUITER NOW: {text}")
    src = [{"n": i + 1, "title": h["meta"]["title"], "type": h["meta"]["type"], "key": h["meta"]["doc_key"]}
           for i, h in enumerate(hits)]
    if getattr(_MODE, "stream", False):
        return {"_stream": {"prompt": prompt, "src": src, "ctx": dict(ctx)}}
    out = llm.generate(prompt, max_tokens=700)
    if out:
        body, sug = _split_next(out)
        return R(body, badge="Database + Documents", sources=src, suggestions=sug or default_suggestions(ctx))
    return None




def route(text: str, attachments: list[dict], st: dict, user: dict, page: dict | None = None) -> dict:
    by = user["name"]
    ctx = st["ctx"]
    page = page or {}
    if page.get("job_id"):
        ctx["job_id"] = page["job_id"]
    if page.get("candidate_id"):
        ctx["cand_id"] = page["candidate_id"]
    text = (text or "").strip()
    t = text.lower()
    cs = find_cands(t)
    fj = find_job(t)
    # "this candidate / her / this job" -> whatever is open on screen
    if not cs and ctx.get("cand_id") and re.search(r"\bthis (candidate|person|profile|cv)\b|\b(him|her|them|his|their)\b", t):
        try:
            cs = [recruit.get_candidate(ctx["cand_id"])]
        except recruit.NotFound:
            pass
    if not fj and ctx.get("job_id") and re.search(r"\bthis (job|role|opening)\b", t):
        try:
            fj = recruit.get_job(ctx["job_id"])
        except recruit.NotFound:
            pass

    # ---- confirmations
    if st.get("pending") and re.search(YES, t) and not attachments:
        return do_pending(st, by)
    if st.get("pending") and re.search(NO, t):
        st["pending"] = None
        return R("No problem, I've left it as it is.", suggestions=default_suggestions(ctx))
    if re.search(r"^(hi|hello|hey|help|what can you do)\b", t) and not attachments:
        return R(f"Hi {by.split()[0]}. I can create jobs from a JD, add CVs as candidates, find who matches a job, "
                 "move people through stages, schedule interviews, draft emails, write JDs you can download, and look "
                 "after your knowledge store. Attach a file or just tell me what you need.",
                 suggestions=["Who matches Store Manager?", "Write a JD for a cashier in Ghaziabad",
                              "Show the knowledge store", "Which jobs have the most applications?"])

    # ---- follow-up that leans on the chat so far: let the AI answer with the history
    if not attachments and st.get("history") and llm.get_llm() and _is_followup(t, cs, fj):
        out = _llm_answer(text, st, ctx)
        if out:
            return out

    # ---- attachments
    if attachments:
        kinds = {"JD": [], "CV": [], "Policy": []}
        for a in attachments:
            if a.get("error"):
                return R(f"I couldn't read {a['name']}: {a['error']}")
            kinds[classify(a["text"])].append(a)
        jds, cvs, docs = kinds["JD"], kinds["CV"], kinds["Policy"]
        if re.search(r"knowledge|policy|faq|save (it|this|these) (to|in)", t) or (docs and not jds and not cvs):
            added = [knowledge.create_doc(re.sub(r"\.[a-z]+$", "", a["name"], flags=re.I).replace("_", " "), a["text"],
                                          "FAQ" if re.search("faq", a["name"] + t, re.I) else "Policy", by,
                                          file_name=a["name"], source="Ask AI") for a in attachments]
            return R(f"Saved {len(added)} document{'s' if len(added) > 1 else ''} to the knowledge store. I'll use "
                     f"{'them' if len(added) > 1 else 'it'} when answering questions.", badge="Action",
                     link={"page": "knowledge", "label": "Open knowledge store"},
                     suggestions=["Show the knowledge store", f"What does {added[0]['title']} say?"])
        if jds:
            a = jds[0]
            p = parse_jd(a["text"])
            ctx["jd"] = {"title": p["title"], "text": a["text"], "file_name": a["name"]}
            if re.search(r"(create|make|add|open|publish|post|set up).*(job|role|opening)|make (it|this) a job", t):
                return do_create_job(a["text"], by, st, a["name"])
            if re.search(r"who|match|fit|rank|best", t):
                st["pending"] = {"type": "createJob", "text": a["text"], "file_name": a["name"]}
                return rank_text(a["text"])
            st["pending"] = {"type": "createJob", "text": a["text"], "file_name": a["name"]}
            return R(f"This looks like a job description for \"{p['title']}\" ({p['location']}). I found "
                     f"{len(p['must'])} must-haves: {', '.join(p['must']) or 'none'}"
                     + (f", and {p['min_years']:g}+ years" if p['min_years'] else "") + ". Shall I create the job?",
                     awaiting_yes=True, suggestions=["Yes, create the job", "Who matches this JD?",
                                                     "Save it to the knowledge store", "Check this JD for bias"])
        if cvs:
            jid = fj["id"] if fj else (ctx.get("job_id") if re.search(r"to (this|the) job", t) else None)
            ctx["cvs"] = [{"text": a["text"], "name": a["name"]} for a in cvs]
            if re.search(r"\b(add|save|create|upload|store)\b", t):
                return do_add_cands(ctx["cvs"], jid, by, st)
            lines = []
            for a in cvs:
                try:
                    p = parse_cv(a["text"])
                except ParseError as e:
                    lines.append(f"• {a['name']}: {e}")
                    continue
                dup = recruit.find_duplicate(p["name"], p["email"])
                bj, bs = best_job(a["text"], p["years"], p["name"])
                lines.append(f"• {p['name']}: {p['headline'] or 'role not found'}, {p['years']:g} yrs, {p['location']}. "
                             f"Best fit {bj['short'] if bj else '—'} ({bs}%)" + (". Already in your talent pool" if dup else ""))
            st["pending"] = {"type": "addCands", "job_id": jid}
            bj0 = best_job(cvs[0]["text"], 0)[0]
            return R(f"I read {len(cvs)} CV{'s' if len(cvs) > 1 else ''}:\n" + "\n".join(lines) +
                     f"\nShall I add {'them' if len(cvs) > 1 else 'this person'} as candidate{'s' if len(cvs) > 1 else ''}?",
                     awaiting_yes=True,
                     suggestions=[f"Yes, add all {len(cvs)}" if len(cvs) > 1 else "Yes, add as a candidate",
                                  f"Add to {bj0['short']}" if bj0 else None, "Which jobs fit?"])

    # ---- screening criteria / rules
    cr = criteria_intent(text, t, fj, ctx, st, by)
    if cr:
        return cr

    # ---- follow-ups about CVs just attached
    if ctx.get("cvs") and re.search(r"^(add|yes)|add (as|to)|which jobs fit", t):
        if "which jobs fit" in t:
            cv = ctx["cvs"][0]["text"]
            p = parse_cv(cv)
            rows = []
            for j in recruit.list_jobs(status="Open"):
                s = recruit.score_texts(j, [{"id": None, "name": p["name"], "cv_text": cv, "years": p["years"]}])[0]
                rows.append([j["title"], f"{s['score']}%", met(s)])
            rows.sort(key=lambda r: -int(r[1][:-1]))
            return R(f"Best fits for {p['name']}:", badge="Database",
                     table={"head": ["Job", "Match", "Must-haves"], "rows": rows},
                     suggestions=[f"Add to {rows[0][0].split(' /')[0]}", "Add to the talent pool only"])
        st["pending"] = None
        return do_add_cands(ctx["cvs"], fj["id"] if fj else None, by, st)

    # ---- write a JD
    if re.search(r"\b(write|make|create|draft|prepare|generate)\b.*\b(jd|job description)\b|\b(jd|job description) for\b", t) \
            and not re.search(r"create (the|this) job", t):
        jd_text, used_ai = write_jd(text)
        doc = jd_doc(jd_text)
        st["pending"] = {"type": "createJob", "text": jd_text}
        ctx["jd"] = {"title": doc["title"], "text": jd_text}
        return R(f"Here's a draft JD for \"{doc['title']}\". Have a look, download it if you like, and say "
                 "\"ok, create the job\" when you're happy.", doc=doc, awaiting_yes=True, badge="Action",
                 suggestions=["Ok, create the job", "Make it shorter" if llm.get_llm() else None,
                              "Check this JD for bias"])
    if st.get("pending", {}) and st["pending"].get("type") == "createJob" and \
            re.search(r"^(make|add|change|remove|edit|shorten|rewrite|include)\b", t):
        nt = revise_jd(st["pending"]["text"], text)
        if nt:
            st["pending"]["text"] = nt
            doc = jd_doc(nt)
            ctx["jd"] = {"title": doc["title"], "text": nt}
            return R("Updated. Here's the new version.", doc=doc, awaiting_yes=True,
                     suggestions=["Ok, create the job", "Check this JD for bias"])
        return R("I need an AI model connected to rewrite the JD. You can edit the requirements on the job page "
                 "after creating it.", suggestions=["Ok, create the job"])
    if re.search(r"(create|make|post|publish).*(job|role)", t) and ctx.get("jd"):
        return do_create_job(ctx["jd"]["text"], by, st, ctx["jd"].get("file_name"))
    if re.search(r"bias|check (this|the) jd", t) and (ctx.get("jd") or fj):
        if ctx.get("jd") and not fj:
            p = parse_jd(ctx["jd"]["text"])
            flags = jd_check(p["description"], p["must"], p["location"])
        else:
            flags = recruit.job_check(fj["id"])
        return R("\n".join(f"{'✓' if f['level'] == 'good' else '•'} {f['title']}. {f['fix']}." for f in flags),
                 badge="Database", suggestions=["Ok, create the job"] if st.get("pending") else default_suggestions(ctx))

    # ---- match against the JD in context
    if re.search(r"(who|which candidates?).*(match|fit|suit)|match(es)? (this|the jd)|best (people|candidates)|^rank", t):
        if ctx.get("jd") and (re.search(r"this|the jd|attached|\bit\b", t) or not fj):
            return rank_text(ctx["jd"]["text"])

    # ---- add an existing candidate to a job
    if re.search(r"\badd\b", t) and cs and fj:
        for c in cs:
            recruit.apply(fj["id"], c["id"], by)
        ctx.update(job_id=fj["id"], cand_id=cs[0]["id"])
        return R(f"Added {' and '.join(c['name'] for c in cs)} to {fj['title']}.", badge="Action",
                 suggestions=[f"Shortlist {first(cs[0])}", f"Who matches {fj['short']}?"])

    # ---- stage moves
    verb = re.search(r"\b(shortlist|reject|select|screen|hire|move)\b", t)
    if verb and cs and not re.search(r"\b(email|mail|draft)\b", t):
        to = {"shortlist": "Shortlisted", "reject": "Rejected", "select": "Selected", "hire": "Selected",
              "screen": "Screening"}.get(verb.group(1))
        if verb.group(1) == "move":
            to = next((s for s in recruit.STAGES if s.lower() in t or s.lower()[:-2] in t), None)
            if not to:
                return R("Which stage should I move them to?",
                         suggestions=[f"Move {first(cs[0])} to {s}" for s in ("Screening", "Shortlisted", "Interview")])
        c = cs[0]
        j = job_of(c, fj)
        a = recruit.app_for(j["id"], c["id"]) or recruit.apply(j["id"], c["id"], by)
        ctx.update(job_id=j["id"], cand_id=c["id"])
        if to == "Rejected":
            st["pending"] = {"type": "stage", "app_id": a["id"], "stage": to, "cid": c["id"]}
            return R(f"Reject {c['name']} for {j['short']}? AI never rejects on its own, so I need your yes.",
                     awaiting_yes=True, suggestions=["Yes, reject", "Cancel"])
        lines = []
        for cc in cs:
            jj = job_of(cc, fj)
            aa = recruit.app_for(jj["id"], cc["id"]) or recruit.apply(jj["id"], cc["id"], by)
            recruit.set_stage(aa["id"], to, by)
            lines.append(f"{cc['name']} → {to} for {jj['short']}")
        f = first(c)
        sugg = {"Shortlisted": [f"Schedule an interview for {f} on Tuesday at 11am", f"Draft an invitation for {f}"],
                "Selected": [f"Draft a selection email for {f}"]}.get(to, [f"Summarize {f}'s profile"])
        return R("\n".join(lines), badge="Action", suggestions=sugg,
                 link={"page": "candidate", "candidate_id": c["id"], "job_id": j["id"], "label": f"Open {f}"})

    # ---- schedule
    if re.search(r"\b(schedule|book|set up|fix|arrange|reschedule)\b.*interview|interview\b.*\b(on|at|tomorrow)\b", t) and cs:
        c = cs[0]
        j = job_of(c, fj)
        d, tm = parse_when(t)
        mode = "Video call" if re.search(r"video|online|zoom|meet", t) else "Phone" if re.search(r"phone|call", t) else "In person"
        who = re.search(r"\bwith (?:the )?([a-z ,]+?)(?: on| at| tomorrow|$)", t)
        interviewer = who.group(1).strip().title() if who and not find_cands(who.group(1)) else "Area Manager"
        iv = interviews.schedule(j["id"], c["id"], d, tm, mode, interviewer, by)
        ctx.update(job_id=j["id"], cand_id=c["id"])
        return R(f"Booked: {c['name']}, {assist.fmt_when(iv)}, {mode.lower()} with the {interviewer}, for {j['short']}.",
                 badge="Action", suggestions=[f"Draft an invitation for {first(c)}",
                                              f"Generate interview questions for {first(c)}"])

    # ---- emails
    em = re.search(r"\b(invit\w*|reminder|remind|rejection|reject|selection|select|offer|follow[- ]?up|assessment)\b", t)
    if re.search(r"draft|write|prepare|send|email|mail", t) and em and cs:
        c = cs[0]
        j = job_of(c, fj)
        w = em.group(1)
        etype = ("invite" if w.startswith("invit") else "rejection" if w.startswith("reject") else
                 "selection" if w.startswith("select") or w == "offer" else "followup" if w.startswith("follow") else
                 "reminder" if w.startswith("remind") else "assessment")
        lang = "Hindi" if "hindi" in t else "English"
        e = assist.draft_email(j["id"], c["id"], etype, lang, by)
        st["pending"] = {"type": "approve", "email_id": e["id"]}
        ctx.update(job_id=j["id"], cand_id=c["id"])
        return R(f"Here's the {e['type_label'].lower()} email for {c['name']}. Say \"send\" to send it, or edit it "
                 "on the profile first. Nothing goes out until you say so.", email=e, awaiting_yes=True, badge="Action",
                 suggestions=["Send", f"Open {first(c)}'s profile"])
    if re.search(r"open .*profile", t) and cs:
        c = cs[0]
        return R(f"Here's {c['name']}'s profile.", link={"page": "candidate", "candidate_id": c["id"],
                                                         "job_id": job_of(c, fj)["id"], "label": f"Open {first(c)}"})

    # ---- feedback & notes
    if "feedback" in t and cs and ":" in text:
        c = cs[0]
        j = job_of(c, fj)
        body = text.split(":", 1)[1].strip()
        interviews.save_feedback(j["id"], c["id"], {}, body, by)
        return R(f"Saved the feedback for {c['name']}.", badge="Action",
                 suggestions=[f"Select {first(c)}", f"Reject {first(c)}"])
    if re.search(r"\bnote\b", t) and cs:
        c = cs[0]
        body = re.split(r":|\bthat\b", text, maxsplit=1)[-1].strip() or text
        j = job_of(c, fj)
        db.run("INSERT INTO notes(candidate_id,job_id,text,by_name,created_at) VALUES(?,?,?,?,?)",
               (c["id"], j["id"], body, by, db.now()))
        db.log("Note added", body[:80], by, candidate_id=c["id"], job_id=j["id"])
        return R(f"Noted on {c['name']}'s profile.", badge="Action")

    # ---- knowledge store
    if re.search(r"(show|list|what('s| is) in|open).*(knowledge|documents|docs|policies)", t):
        ds = knowledge.all_docs()
        pol = [d for d in ds if d["kind"] not in ("JD", "CV")]
        return R(f"You have {len(pol)} policy and FAQ documents, plus {sum(d['kind'] == 'JD' for d in ds)} job "
                 f"descriptions and {sum(d['kind'] == 'CV' for d in ds)} CVs in the knowledge store.", badge="Database",
                 table={"head": ["Document", "Type"], "rows": [[d["title"], d["kind"]] for d in pol]},
                 link={"page": "knowledge", "label": "Open knowledge store"},
                 suggestions=["Add a policy: Notice period is 30 days for store staff", "Delete the hiring time FAQ"])
    if re.search(r"(add|save|create|new).*(policy|faq|document|doc)", t) and ":" in text:
        body = text.split(":", 1)[1].strip()
        title = re.split(r"[.!?]", body)[0][:50].strip()
        d = knowledge.create_doc(title, body, "FAQ" if "faq" in t else "Policy", by, source="Ask AI")
        return R(f"Added \"{d['title']}\" to the knowledge store.", badge="Action",
                 suggestions=["Show the knowledge store", f"What does {d['title']} say?"])
    if re.search(r"\b(delete|remove)\b", t) and re.search(r"doc|document|policy|faq|jd|job description|cv|job|candidate", t):
        target = None
        if re.search(r"\bcv\b|candidate", t) and cs:
            target = ("cand", cs[0]["id"], cs[0]["name"])
        elif re.search(r"\bjob\b|\bjd\b|job description", t) and fj and not re.search(r"faq|policy", t):
            target = ("job", fj["id"], fj["title"])
        else:
            words = [w for w in re.sub(r"delete|remove|the|document|doc|policy|faq|please|from|knowledge|store|"
                                       r"job description|\bjd\b|\bcv\b", " ", t).split() if len(w) > 2]
            best, bs = None, 0
            for d in db.rows("SELECT id, title FROM knowledge_docs"):
                s = sum(w in d["title"].lower() for w in words)
                if s > bs:
                    best, bs = d, s
            if best:
                target = ("doc", best["id"], best["title"])
        if not target:
            return R("I couldn't tell which document you mean. Can you give me its name?",
                     link={"page": "knowledge", "label": "Open knowledge store"})
        st["pending"] = {"type": "delete", "kind": target[0], "id": target[1], "title": target[2]}
        warn = {"job": "This also removes the job and its pipeline.", "cand": "This removes the candidate from every job.",
                "doc": "I won't use it for answers after this."}[target[0]]
        return R(f"Delete \"{target[2]}\"? {warn}", awaiting_yes=True, suggestions=["Yes, delete it", "Cancel"])

    # ---- database questions
    s = structured(text, cs, fj)
    if s:
        if fj:
            ctx["job_id"] = fj["id"]
        if cs:
            ctx["cand_id"] = cs[0]["id"]
        if not s["suggestions"]:
            s["suggestions"] = default_suggestions(ctx)
        return s

    # ---- specific answers from the data (no AI key needed)
    ins = insights(text, cs, fj, ctx)
    if ins:
        if fj:
            ctx["job_id"] = fj["id"]
        if cs:
            ctx["cand_id"] = cs[0]["id"]
        return ins

    # ---- anything else: with AI on, answer from the whole database + documents + the chat so far
    if llm.get_llm():
        out = _llm_answer(text, st, ctx)
        if out:
            return out

    # ---- documents (RAG)
    a = knowledge.answer(text)
    if not a["ai"] and a["sources"] and a["sources"][0]["type"] in ("CV", "JD"):
        return menu_reply(ctx)
    if not a["grounded"]:
        return busy_reply(ctx) if llm.get_llm() else menu_reply(ctx)
    return R(a["text"], badge="Documents" if a["grounded"] else None, sources=a["sources"],
             suggestions=default_suggestions(ctx) if a["grounded"] else
             ["What can you do?", *default_suggestions(ctx)[:2]])


def chat(sid: str, user: dict, text: str, attachments: list[dict], page: dict | None = None) -> dict:
    st = load_state(sid)
    try:
        out = route(text, attachments, st, user, page)
        wp = _wrap_prompt(out, text, st)
        if wp:
            ai = llm.generate(wp, max_tokens=500)
            if ai:
                out = _apply_wrap(out, ai)
    except (ValueError, recruit.NotFound, ParseError) as e:
        out = R(f"I couldn't do that: {e}")
    st["history"].append({"role": "user", "text": text, "files": [a["name"] for a in attachments]})
    st["history"].append({"role": "assistant", **out})
    save_state(sid, user["id"], st)
    return out


def chat_stream(sid: str, user: dict, text: str, attachments: list[dict], page: dict | None = None):
    """Yield {"delta": text} pieces while the AI writes, then {"final": reply}. Quick answers come as one final."""
    st = load_state(sid)
    _MODE.stream = True
    try:
        try:
            out = route(text, attachments, st, user, page)
        except (ValueError, recruit.NotFound, ParseError) as e:
            out = R(f"I couldn't do that: {e}")
    finally:
        _MODE.stream = False
    spec = out.pop("_stream", None) if isinstance(out, dict) else None
    wrap = None
    if not spec:
        wp = _wrap_prompt(out, text, st)
        if wp:
            wrap = out
            spec = {"prompt": wp, "src": [], "ctx": dict(st["ctx"]), "badge": "AI + Database"}
    if spec:
        parts, sent = [], 0
        for piece in llm.stream(spec["prompt"], max_tokens=700):
            parts.append(piece)
            full = "".join(parts)
            i = full.find("NEXT:")
            lim = i if i >= 0 else max(0, len(full) - 5)
            if lim > sent:
                yield {"delta": full[sent:lim]}
                sent = lim
        full = "".join(parts).strip()
        body, sug = _split_next(full)
        if len(body) > sent and "NEXT:" not in full:
            yield {"delta": body[sent:]}
        if body and wrap is not None:
            out = _apply_wrap(wrap, full)
        elif body:
            out = R(body, badge=spec.get("badge", "Database + Documents"), sources=spec["src"],
                    suggestions=sug or default_suggestions(spec["ctx"]))
        elif wrap is not None:
            out = wrap   # AI failed: the data answer is still correct, keep it
        else:   # AI failed: use the document / menu answer instead
            a = knowledge.answer(text)
            out = (R(a["text"], badge="Documents", sources=a["sources"], suggestions=default_suggestions(spec["ctx"]))
                   if a["grounded"] and a["sources"] and a["sources"][0]["type"] not in ("CV", "JD") else busy_reply(spec["ctx"]))
    st["history"].append({"role": "user", "text": text, "files": [a["name"] for a in attachments]})
    st["history"].append({"role": "assistant", **out})
    save_state(sid, user["id"], st)
    yield {"final": out}


def history(sid: str) -> list[dict]:
    return load_state(sid)["history"]
