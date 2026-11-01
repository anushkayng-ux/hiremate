"""End-to-end API tests on a fresh synthetic database. Run: pytest -q"""
import os
import tempfile
import uuid

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["LLM_PROVIDER"] = "template"  # tests must not depend on an API key
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("EMBEDDER", "hashing")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

NEW_JD = """Visual Merchandiser
Location: Noida, Sector 18 store
About the role: Make the store look great and help sales.
Responsibilities:
- Plan window displays and planograms for each season.
- Work with the store team on festive launches.
Must have: visual merchandising, customer service, team management
Nice to have: Hindi, Excel reporting
Qualification: Graduate
Experience: 2+ years in retail."""

NEW_CV = """Meera Joshi
Email: meera.joshi@example.com
Location: Noida
Summary: Visual merchandiser in fashion retail.
Experience:
Visual Merchandiser | Trendz Fashion, Noida | Jan 2022 – Present
- Planned window displays for 12 festive launches.
- Built planograms for a 10,000 sq ft store and trained the store team.
- Handled customer queries on the floor during sales.
Education: BBA, 2021
Skills: visual merchandising, customer service, Hindi, Excel"""


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        r = client.post("/auth/login", json={"email": "admin@hiremate.demo", "password": "recruit123"})
        assert r.status_code == 200
        client.headers["Authorization"] = "Bearer " + r.json()["token"]
        yield client


def chat(c, msg, sid, files=None, **page):
    data = {"session_id": sid, "message": msg, **{k: str(v) for k, v in page.items()}}
    r = c.post("/assistant/chat", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_auth_required():
    with TestClient(app) as anon:
        assert anon.get("/jobs").status_code == 401
        assert anon.post("/auth/login", json={"email": "admin@hiremate.demo", "password": "x"}).status_code == 401


def test_seed_and_ranking(c):
    jobs = c.get("/jobs").json()
    assert len(jobs) == 3
    sm = next(j for j in jobs if j["title"] == "Store Manager")
    assert "Store operations" in sm["must"] and sm["min_years"] == 5
    ranked = c.get(f"/match/job/{sm['id']}").json()
    assert ranked[0]["name"] == "Priya Nair"
    assert all(r["score"] >= ranked[i + 1]["score"] for i, r in enumerate(ranked[:-1]))
    row = next(r for r in ranked[0]["rows"] if r["skill"] == "Store operations")
    assert row["status"] == "Proven" and row["evidence"]


def test_jd_upload_check_and_edit(c):
    r = c.post("/jobs/upload", files={"file": ("vm.txt", NEW_JD.encode(), "text/plain")})
    assert r.status_code == 200
    j = r.json()
    assert j["title"] == "Visual Merchandiser" and "Visual merchandising" in j["must"]
    assert c.get(f"/jobs/{j['id']}/check").json()[0]["level"] == "good"
    j2 = c.patch(f"/jobs/{j['id']}", json={"must": ["Visual merchandising", "Customer service"], "min_years": 1}).json()
    assert j2["must"] == ["Visual merchandising", "Customer service"] and j2["min_years"] == 1
    bad = c.post("/jobs/preview", data={"text": "Young energetic girls needed for billing. Must have: POS"}).json()
    assert any(f["level"] == "bad" for f in bad["check"])


def test_cv_upload_duplicate_and_pipeline(c):
    r = c.post("/candidates/upload", files=[("files", ("meera.txt", NEW_CV.encode(), "text/plain"))]).json()
    assert r[0]["ok"] and r[0]["candidate"]["name"] == "Meera Joshi"
    cid = r[0]["candidate"]["id"]
    dup = c.post("/candidates/upload", files=[("files", ("meera2.txt", NEW_CV.encode(), "text/plain"))]).json()
    assert not dup[0]["ok"] and "duplicate" in dup[0]["error"].lower()
    sm = next(j for j in c.get("/jobs").json() if j["title"] == "Store Manager")
    a = c.post("/applications", json={"job_id": sm["id"], "candidate_id": cid}).json()
    assert c.patch(f"/applications/{a['id']}", json={"stage": "Shortlisted"}).json()["stage"] == "Shortlisted"
    assert c.patch(f"/applications/{a['id']}", json={"stage": "Nope"}).status_code == 422
    assert c.get("/candidates", params={"skill": "Visual"}).json()


def test_interview_feedback_email_flow(c):
    wh = next(j for j in c.get("/jobs").json() if j["title"] == "Warehouse Supervisor")
    arjun = next(x for x in c.get("/candidates").json() if x["name"] == "Arjun Mehta")
    iv = c.post("/interviews", json={"job_id": wh["id"], "candidate_id": arjun["id"], "date": "2030-01-07",
                                     "time": "10:30", "mode": "Video call", "interviewer": "Area Manager"}).json()
    assert iv["stage"] == "Interview"
    qs = c.get("/ai/questions", params={"job_id": wh["id"], "candidate_id": arjun["id"]}).json()["questions"]
    assert {q["type"] for q in qs} >= {"Technical", "HR", "Verification"}
    fb = c.post("/interviews/feedback", json={"job_id": wh["id"], "candidate_id": arjun["id"],
                                              "scores": {"WMS software": 5, "Safety compliance": 4},
                                              "text": "Strong on WMS. Recommend."}).json()
    assert fb["readiness"] > 50
    s = c.get("/ai/feedback-summary", params={"job_id": wh["id"], "candidate_id": arjun["id"]}).json()
    assert "Recommendation" in s["text"]
    e = c.post("/emails", json={"job_id": wh["id"], "candidate_id": arjun["id"], "type": "invite"}).json()
    assert e["status"] == "Draft" and "AI tool" in e["body"] and "2030" in e["body"]
    e2 = c.post(f"/emails/{e['id']}/send").json()
    assert e2["status"] == "Sent" and e2["sent_by"] == "Demo Admin"
    hi = c.post("/emails", json={"job_id": wh["id"], "candidate_id": arjun["id"], "type": "selection", "lang": "Hindi"}).json()
    assert "प्रिय" in hi["body"]


def test_knowledge_crud_and_rag(c):
    d = c.post("/knowledge", json={"title": "Notice period", "text": "Store staff serve a 30 day notice period.",
                                   "type": "Policy"}).json()
    ans = c.post("/knowledge/ask", json={"question": "What is the notice period for store staff?"}).json()
    assert ans["grounded"] and "30 day" in ans["text"] and ans["sources"][0]["title"] == "Notice period"
    assert c.post("/knowledge/ask", json={"question": "zebra quantum banana"}).json()["grounded"] is False
    c.patch(f"/knowledge/{d['id']}", json={"text": "Store staff serve a 45 day notice period."})
    assert "45" in c.post("/knowledge/ask", json={"question": "notice period store staff"}).json()["text"]
    assert c.delete(f"/knowledge/{d['id']}").json()["ok"]
    kinds = {x["kind"] for x in c.get("/knowledge").json()}
    assert {"JD", "CV", "Policy", "FAQ"} <= kinds


def test_asha_full_flow(c):
    sid = str(uuid.uuid4())
    r = chat(c, "Who matches Store Manager?", sid)
    assert r["table"] and r["table"]["rows"][0][1] == "Priya Nair"
    # attach a JD -> match -> create
    jd2 = NEW_JD.replace("Visual Merchandiser", "Floor Supervisor")
    r = chat(c, "who matches this JD?", sid, files=[("files", ("floor.txt", jd2.encode(), "text/plain"))])
    assert r["table"] and r["suggestions"][0] == "Yes, create the job"
    r = chat(c, "Yes, create the job", sid)
    assert "has been created" in r["reply"] and r["link"]["page"] == "job"
    # attach a CV -> add
    cv = NEW_CV.replace("Meera Joshi", "Tara Singh").replace("meera.joshi", "tara.singh")
    r = chat(c, "", sid, files=[("files", ("tara.txt", cv.encode(), "text/plain"))])
    assert r["awaiting_yes"] and "Tara Singh" in r["reply"]
    r = chat(c, "Yes, add as a candidate", sid)
    assert "Added Tara Singh" in r["reply"]
    # write a JD -> docx -> create
    r = chat(c, "Write a JD for a cashier in Gurugram with 1+ years", sid)
    assert r["doc"] and r["doc"]["file_name"].endswith(".docx")
    assert c.get(f"/knowledge/files/{r['doc']['file_id']}").status_code == 200
    r = chat(c, "ok, create the job", sid)
    assert "has been created" in r["reply"]
    # stage, schedule, email, approve
    assert "Shortlisted" in chat(c, "Shortlist Kavya for Store Manager", sid)["reply"]
    r = chat(c, "Schedule an interview for Kavya on Tuesday at 3pm", sid)
    assert "Booked" in r["reply"] and "3:00 PM" in r["reply"]
    r = chat(c, "Draft an invitation for Kavya", sid)
    assert r["email"] and r["awaiting_yes"]
    assert "Sent to" in chat(c, "send", sid)["reply"]
    # reject needs a yes
    r = chat(c, "Reject Imran for Store Manager", sid)
    assert r["awaiting_yes"]
    assert "Rejected" in chat(c, "yes", sid)["reply"]
    # database + documents + knowledge management
    assert chat(c, "Which candidates are awaiting interviews?", sid)["badge"] == "Database"
    r = chat(c, "How many days' notice do I need to reschedule an interview?", sid)
    assert r["badge"] == "Documents" and "24 hours" in r["reply"]
    assert "Added" in chat(c, "Add a policy: Notice period is 30 days for store staff", sid)["reply"]
    r = chat(c, "Delete the hiring time FAQ", sid)
    assert r["awaiting_yes"] and "Hiring time" in r["reply"]
    assert "Deleted" in chat(c, "yes", sid)["reply"]
    r = chat(c, "Compare Priya and Rohit", sid)
    assert r["table"]["head"][1:] == ["Priya Nair", "Rohit Verma"]
    assert "not in the data" in chat(c, "What is the CEO's favourite colour?", sid)["reply"].lower()


def test_dashboard_analytics_settings(c):
    d = c.get("/analytics/dashboard").json()
    assert d["kpis"]["open_roles"] >= 3 and d["roles"]
    a = c.get("/analytics").json()
    assert a["funnel"][0]["stage"] == "Applied" and a["talent_groups"]["points"]
    w = c.put("/settings/weights", json={"skills": 70, "text": 10, "exp": 20}).json()
    assert w["skills"] == 70
    s = c.get("/settings").json()
    assert s["llm"]["connected"] is False


def test_interviewer_cannot_change_stage(c):
    with TestClient(app) as iv:
        tok = iv.post("/auth/login", json={"email": "interviewer@hiremate.demo", "password": "recruit123"}).json()["token"]
        iv.headers["Authorization"] = "Bearer " + tok
        assert iv.patch("/applications/1", json={"stage": "Selected"}).status_code == 403
        assert iv.get("/interviews").status_code == 200


class FakeLLM:
    name = "Fake"

    def generate(self, prompt, system="", max_tokens=900):
        if "JSON" in prompt:
            return '[{"type":"Technical","skill":"WMS software","question":"How do you use the WMS?","follow_up":"Example?","good_answer":"Specific steps."}]'
        if "Subject:" in prompt or "email" in prompt.lower():
            return "Subject: Interview invite\n\nDear Arjun,\nSee you soon.\nDrafted with an AI tool and checked by a recruiter."
        if "job description" in prompt.lower() and "Request:" in prompt:
            return "Cashier\nLocation: Gurugram\nAbout the role: Bill customers.\nResponsibilities:\n- Bill\nMust have: POS billing, cash handling\nNice to have: Hindi\nQualification: Class 12\nExperience: 1+ years."
        return "• Answer from sources [1]"


def test_llm_paths(c, monkeypatch):
    from backend.app.adapters import llm
    monkeypatch.setattr(llm, "get_llm", lambda: FakeLLM())
    wh = next(j for j in c.get("/jobs").json() if j["title"] == "Warehouse Supervisor")
    arjun = next(x for x in c.get("/candidates").json() if x["name"] == "Arjun Mehta")
    q = c.get("/ai/questions", params={"job_id": wh["id"], "candidate_id": arjun["id"]}).json()
    assert q["ai"] and q["questions"][0]["skill"] == "WMS software"
    e = c.post("/emails", json={"job_id": wh["id"], "candidate_id": arjun["id"], "type": "invite"}).json()
    assert e["ai"] and e["subject"] == "Interview invite"
    s = c.get("/ai/summary", params={"job_id": wh["id"], "candidate_id": arjun["id"]}).json()
    assert s["ai"]
    r = chat(c, "Write a JD for a cashier in Gurugram", str(uuid.uuid4()))
    assert r["doc"]["title"] == "Cashier"
    a = c.post("/knowledge/ask", json={"question": "reschedule interview notice"}).json()
    assert a["text"].startswith("• Answer") and a["sources"]
    r = chat(c, "Who has the most experience and what is their notice period?", str(uuid.uuid4()))
    assert r["badge"] == "Database + Documents"


def test_ai_settings_free_default_and_paid_key(c):
    ai = c.get("/settings/ai").json()
    assert ai["plan"] == "free"
    r = c.put("/settings/ai", json={"provider": "claude", "anthropic_key": "sk-ant-secret-1234"}).json()
    assert r["plan"] == "paid" and r["anthropic_key"] == "•••• 1234"
    assert "secret" not in str(c.get("/settings/ai").json())
    assert c.get("/settings").json()["llm"]["connected"] is True
    with TestClient(app) as rc:
        tok = rc.post("/auth/login", json={"email": "recruiter@hiremate.demo", "password": "recruit123"}).json()["token"]
        rc.headers["Authorization"] = "Bearer " + tok
        assert rc.put("/settings/ai", json={"provider": "template"}).status_code == 403
    r = c.put("/settings/ai", json={"provider": "template", "clear_keys": True}).json()
    assert r["provider"] == "template" and r["anthropic_key"] == ""
    assert c.post("/settings/ai/test").json()["ok"]
    assert c.get("/settings").json()["llm"]["connected"] is False


def test_ai_reads_everything(c):
    sid = str(uuid.uuid4())
    r = chat(c, "List all candidates with their skills and gaps", sid)
    assert r["table"]["head"][-1] == "Gaps" and len(r["table"]["rows"]) >= 7
    r = chat(c, "show shortlisted candidates", sid)
    assert all(row[2] == "Shortlisted" for row in r["table"]["rows"])
    r = chat(c, "list candidates in Noida with more than 5 years", sid)
    assert all(row[5] == "Noida" and float(row[4]) >= 5 for row in r["table"]["rows"])
    r = chat(c, "What are Kavya's gaps?", sid)
    assert "Gaps" in r["reply"] and r["table"]
    sm = next(j for j in c.get("/jobs").json() if j["title"] == "Store Manager")
    kav = next(x for x in c.get("/candidates").json() if x["name"] == "Kavya Rao")
    r = chat(c, "what skills is this candidate missing?", sid, candidate_id=kav["id"], job_id=sm["id"])
    assert r["reply"].startswith("Kavya Rao")
    assert chat(c, "show candidates with WMS", sid)["table"]["rows"]
    assert chat(c, "Show emails waiting for approval", sid)["badge"] == "Database"


def test_screening_criteria(c):
    sm = next(j for j in c.get("/jobs").json() if j["title"] == "Store Manager")
    before = {r["name"]: r["score"] for r in c.get(f"/match/job/{sm['id']}").json()}
    p = c.post("/criteria/preview", json={"text": "Must live in Noida"}).json()
    assert p["kind"] == "must" and p["check_type"] == "city" and p["value"] == "Noida"
    must = c.post("/criteria", json={"text": "Must live in Noida", "job_id": sm["id"]}).json()
    bonus = c.post("/criteria", json={"text": "Prefer Hindi speakers +5 points", "job_id": sm["id"]}).json()
    assert bonus["check_type"] == "skill" and bonus["points"] == 5 and bonus["text"] == "Prefer Hindi speakers"
    glob = c.post("/criteria", json={"text": "prefer candidates with festive season experience"}).json()
    assert glob["job_id"] is None and glob["check_type"] == "custom"
    ranked = c.get(f"/match/job/{sm['id']}").json()
    # people outside Noida are flagged and listed after those who meet every must rule
    flags = [r["meets_criteria"] for r in ranked]
    assert flags == sorted(flags, reverse=True)
    rohit = next(r for r in ranked if r["name"] == "Rohit Verma")
    assert not rohit["meets_criteria"] and "Must live in Noida" in rohit["criteria_failed"]
    priya = next(r for r in ranked if r["name"] == "Priya Nair")
    assert priya["meets_criteria"] and priya["score"] > before["Priya Nair"]  # Hindi + festive bonus
    fest = next(x for x in priya["criteria"] if x["check"] == "custom")
    assert fest["status"] == "met" and "festive" in fest["evidence"].lower()
    # rules list: this job + all-job rules
    assert {x["id"] for x in c.get("/criteria", params={"job_id": sm["id"]}).json()} == {must["id"], bonus["id"], glob["id"]}
    # turn off, then remove
    c.patch(f"/criteria/{must['id']}", json={"active": False})
    assert all(r["meets_criteria"] for r in c.get(f"/match/job/{sm['id']}").json())
    for x in (must, bonus, glob):
        assert c.delete(f"/criteria/{x['id']}").json()["ok"]
    assert c.post("/criteria", json={"text": "x", "check_type": "years", "value": "lots"}).status_code == 422
    g = c.put("/settings/guidelines", json={"text": "Always mention the store address."}).json()
    assert "store address" in g["text"]
    c.put("/settings/guidelines", json={"text": ""})


def test_smart_helpers(c):
    jobs = c.get("/jobs").json()
    jid = next(j["id"] for j in jobs if c.get(f"/match/job/{j['id']}").json())
    ranked = c.get(f"/match/job/{jid}").json()
    r = next(x for x in ranked if x["stage"] in ("Applied", "Screening", "Shortlisted"))
    # things to check on a CV
    flags = c.get(f"/smart/flags/{r['candidate_id']}", params={"job_id": jid}).json()
    assert isinstance(flags, list)
    # next step for a job is plain words with a kind
    nx = c.get(f"/smart/next/{jid}").json()
    assert nx["kind"] in {"add", "review", "book", "decide", "wait", "done"} and nx["text"]
    # free slots never clash
    sl = c.get("/smart/slots", params={"job_id": jid, "candidate_id": r["candidate_id"]}).json()
    assert len(sl) == 3 and len({(s["date"], s["time"]) for s in sl}) == 3
    # move to Not selected drafts a rejection; undo puts it back and removes the draft
    old = r["stage"]
    mv = c.post(f"/smart/move/{r['application_id']}", json={"stage": "Rejected"}).json()
    assert mv["old_stage"] == old and mv["email_id"]
    c.post(f"/smart/undo/{r['application_id']}", json={"old_stage": old, "email_id": mv["email_id"]})
    again = c.get(f"/match/job/{jid}/candidate/{r['candidate_id']}").json()
    assert again["stage"] == old
    assert all(e["id"] != mv["email_id"] for e in c.get("/emails").json())
    # booking sets stage to Interview and drafts the invite
    bk = c.post("/smart/book", json={"job_id": jid, "candidate_id": r["candidate_id"], "date": sl[0]["date"],
                                          "time": sl[0]["time"]}).json()
    assert bk["email_id"]
    assert c.get(f"/match/job/{jid}/candidate/{r['candidate_id']}").json()["stage"] in ("Interview", "Selected")
    assert isinstance(c.get("/smart/waiting").json(), list)



def test_candidate_portal_full_loop(c):
    """Recruiter drafts -> sends -> candidate sees it -> replies -> recruiter inbox -> AI reply draft."""
    from fastapi.testclient import TestClient as TC
    p = TC(app)
    # wrong password refused; demo password works
    assert p.post("/portal/login", json={"email": "arjun.mehta@example.com", "password": "nope"}).status_code == 401
    r = p.post("/portal/login", json={"email": "arjun.mehta@example.com", "password": "candidate123"})
    assert r.status_code == 200
    ph = {"Authorization": "Bearer " + r.json()["token"]}
    cid = r.json()["candidate"]["id"]
    # a candidate token can never open recruiter pages
    assert p.get("/candidates", headers=ph).status_code == 403
    assert p.get("/match/job/1", headers=ph).status_code == 403
    apps = p.get("/portal/applications", headers=ph).json()
    assert apps and "score" not in apps[0]
    jid = apps[0]["job_id"]
    # drafts are invisible to the candidate until the recruiter presses Send
    d = c.post("/emails", json={"job_id": jid, "candidate_id": cid, "type": "followup"}).json()
    assert all(m["id"] != d["id"] for m in p.get("/portal/messages", headers=ph).json())
    c.post(f"/emails/{d['id']}/send")
    msgs = p.get("/portal/messages", headers=ph).json()
    assert any(m["id"] == d["id"] for m in msgs)
    # candidate replies -> recruiter inbox
    p.post(f"/portal/messages/{d['id']}/reply", json={"body": "Thanks! Can I come on Saturday instead?"}, headers=ph)
    inbox = c.get("/emails/inbox/list").json()
    msg = next(m for m in inbox if "Saturday" in m["body"])
    assert msg["direction"] == "in" and msg["candidate_id"] == cid
    # AI drafts the reply (template without a key); it stays a draft
    rep = c.post(f"/emails/{msg['id']}/ai-reply").json()
    assert rep["status"] == "Draft" and rep["parent_id"] == msg["id"]
    th = c.get("/emails/thread/list", params={"job_id": jid, "candidate_id": cid}).json()
    assert any(m["direction"] == "in" for m in th)
    # interview answer comes back as a message too
    iv = next((a["interview"] for a in apps if a["interview"]), None)
    if iv:
        p.post(f"/portal/interviews/{iv['id']}/respond", json={"response": "Confirmed"}, headers=ph)
        assert any("confirmed" in m["subject"].lower() for m in c.get("/emails/inbox/list").json())
    # sign-up with a CV creates a candidate who is matched to the job
    cv = ("Ravi Kumar\nLocation: Noida\nSummary: Store supervisor.\nExperience:\nStore Supervisor | ShopRite, Noida | "
          "Jan 2019 – Present\n- Led a team of 12 associates on the floor.\n- Ran weekly inventory counts.\n"
          "Skills: store operations, team management, inventory, customer service, POS, Excel")
    s = p.post("/portal/signup", data={"name": "Ravi Kumar", "email": "ravi.k@example.com", "password": "secret1",
                                       "job_id": jid, "text": cv})
    assert s.status_code == 200, s.text
    nh = {"Authorization": "Bearer " + s.json()["token"]}
    assert p.get("/portal/applications", headers=nh).json()[0]["job_id"] == jid
    assert any(x["name"] == "Ravi Kumar" for x in c.get(f"/match/job/{jid}").json())


def test_team_management(c):
    users = {u["email"]: u for u in c.get("/settings/users").json()}
    assert users["admin@hiremate.demo"]["name"] == "Demo Admin"
    assert users["recruiter@hiremate.demo"]["name"] == "Demo Recruiter"
    # add, change role, turn off, new password
    n = c.post("/settings/users", json={"name": "Test Person", "email": "t.person@hiremate.demo", "role": "Interviewer",
                                        "password": "temp123"}).json()
    r = c.patch(f"/settings/users/{n['id']}", json={"role": "Recruiter"})
    assert r.status_code == 200 and r.json()["role"] == "Recruiter"
    r = c.patch(f"/settings/users/{n['id']}", json={"active": False})
    assert r.json()["active"] == 0
    with TestClient(app) as t:
        assert t.post("/auth/login", json={"email": "t.person@hiremate.demo", "password": "temp123"}).status_code == 401
        c.patch(f"/settings/users/{n['id']}", json={"active": True, "password": "newpass1"})
        ok = t.post("/auth/login", json={"email": "t.person@hiremate.demo", "password": "newpass1"})
        assert ok.status_code == 200
        t.headers["Authorization"] = "Bearer " + ok.json()["token"]
        assert t.patch(f"/settings/users/{n['id']}", json={"role": "Admin"}).status_code == 403  # not an Admin
    # the last Admin can't be turned off or demoted, and you can't turn off yourself
    me = users["admin@hiremate.demo"]["id"]
    assert c.patch(f"/settings/users/{me}", json={"active": False}).status_code == 409
    assert c.patch(f"/settings/users/{me}", json={"role": "Recruiter"}).status_code == 409
