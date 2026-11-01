"""Tests for HireMate Plus (backend/app/plus): the 40 extra features."""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ["LLM_PROVIDER"] = "template"
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("EMBEDDER", "hashing")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


def _login(c, email, pw="recruit123", path="/auth/login"):
    return {"Authorization": "Bearer " + c.post(path, json={"email": email, "password": pw}).json()["token"]}


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        h = _login(client, "admin@hiremate.demo")
        client.post("/settings/reset-demo", headers=h)
        client.headers.update(_login(client, "admin@hiremate.demo"))
        yield client


def ids(c):
    jobs = {j["title"].split()[0]: j["id"] for j in c.get("/jobs").json()}
    cands = {}
    for x in c.get("/candidates").json():
        cands.setdefault(x["name"], x["id"])
    return jobs, cands


def test_briefing_and_dropout(c):
    b = c.get("/plus/briefing").json()
    assert "Replies waiting" in b["text"]
    risks = c.get("/plus/dropout").json()
    assert any(r["name"] == "Priya Nair" and r["level"] != "Low" for r in risks)
    nudge = c.get(f"/plus/dropout/{risks[0]['application_id']}/nudge").json()
    assert risks[0]["name"].split()[0] in nudge["text"]


def test_best_fit_elsewhere_and_move(c):
    bf = c.get("/plus/best-fit").json()
    imran = next(x for x in bf if x["name"] == "Deepak Singh")
    assert imran["to_score"] >= imran["from_score"] + 10
    r = c.post("/plus/best-fit/move", json={"job_id": imran["to_job_id"], "candidate_id": imran["candidate_id"]})
    assert r.status_code == 200


def test_candidate_panel_has_everything(c):
    jobs, cands = ids(c)
    p = c.get(f"/plus/candidate/{cands['Rohit Verma']}", params={"job_id": jobs["Cashier"]}).json()
    for k in ("commute", "salary", "train", "success", "integrity", "career", "why_not", "panel", "risk"):
        assert k in p
    assert p["salary"]["level"] == "high"  # expects ₹40,000 vs a ₹15–22k band
    assert p["commute"]["known"]


def test_commute_and_pay_band(c):
    from backend.app.plus import insights
    assert insights.commute("Faridabad", "Noida, Sector 18 store")["minutes"] > 45
    assert insights.commute("Indirapuram", "Ghaziabad, Raj Nagar store")["level"] == "ok"
    assert insights.commute("Mars", "Noida")["known"] is False
    jobs, _ = ids(c)
    assert c.put(f"/plus/pay-band/{jobs['Store']}", json={"min": 50000, "max": 40000}).status_code == 422
    assert c.put(f"/plus/pay-band/{jobs['Store']}", json={"min": 45000, "max": 72000}).json()["max"] == 72000


def test_ask_cv_quotes_or_says_not_there(c):
    _, cands = ids(c)
    a = c.post(f"/plus/ask-cv/{cands['Anjali Sharma']}", json={"question": "How many customers did she bill a day?"}).json()
    assert any("250" in q for q in a["quotes"])
    n = c.post(f"/plus/ask-cv/{cands['Anjali Sharma']}", json={"question": "Does she know Python programming?"}).json()
    assert n["quotes"] == [] and "Not" in n["answer"]


def test_talent_insights(c):
    jobs, cands = ids(c)
    assert c.get("/plus/hidden-gems").json()
    assert c.get(f"/plus/jd-reality/{jobs['Store']}").json()["skills"]
    assert len(c.get("/plus/pool-health").json()) == 3
    assert any(s["gap"] == "short" for s in c.get("/plus/skill-demand").json())
    assert c.get("/plus/offer-risk").json()[0]["name"] == "Priya Nair"
    so = c.get("/plus/second-opinion", params={"job_id": jobs["Store"], "candidate_id": cands["Priya Nair"]}).json()
    assert so["side"] == "Reasons to slow down" and so["points"]
    wn = c.get(f"/plus/candidate/{cands['Imran Qureshi']}", params={"job_id": jobs["Store"]}).json()["why_not"]
    assert wn["best_fix"]["gain"] > 0


def test_duplicates_and_merge(c):
    d = c.get("/plus/duplicates").json()
    assert d and "same phone" in d[0]["why"]
    r = c.post("/plus/duplicates/merge", json={"keep_id": d[0]["keep_id"], "dup_id": d[0]["dup_id"]}).json()
    assert r["ok"]
    assert c.get("/plus/duplicates").json() == []


def test_interview_tools(c):
    jobs, cands = ids(c)
    card = c.post("/plus/notes-to-scorecard", json={"job_id": jobs["Cashier"], "candidate_id": cands["Anjali Sharma"],
                                                    "notes": "Very quick and accurate on POS billing. Struggled with "
                                                             "customer service, needs coaching."}).json()
    by = {r["skill"]: r["rating"] for r in card["rows"]}
    assert by["POS systems"] > by["Customer service"]
    nq = c.post("/plus/next-question", json={"job_id": jobs["Cashier"], "candidate_id": cands["Anjali Sharma"],
                                             "asked": [], "notes": "POS was fine"}).json()
    assert nq["skill"] in ("Cash handling", "Customer service")
    gaps = c.get(f"/plus/candidate/{cands['Anjali Sharma']}", params={"job_id": jobs["Cashier"]}).json()["panel"]["gaps"]
    assert gaps and gaps[0]["skill"] == "Customer service"
    assert c.get(f"/plus/roleplay/{jobs['Cashier']}").json()
    bank = c.get(f"/plus/bank/{jobs['Cashier']}").json()
    q = bank[-1]
    c.post(f"/plus/bank/vote/{q['id']}", json={"useful": True})
    c.post(f"/plus/bank/vote/{q['id']}", json={"useful": True})
    c.post(f"/plus/bank/vote/{q['id']}", json={"useful": True})
    assert c.get(f"/plus/bank/{jobs['Cashier']}").json()[0]["id"] == q["id"]  # most useful rises to the top


def test_messages_tools(c):
    jobs, cands = ids(c)
    inbox = c.get("/emails/inbox/list", params={"all": "true"}).json()
    arjun = next(e for e in inbox if e["candidate"] == "Arjun Mehta")
    pa = c.post(f"/plus/policy-answer/{arjun['id']}").json()
    assert "Interview day guide" in pa["sources"] and "parking" in pa["text"].lower()
    pv = c.get(f"/plus/bulk/{jobs['Store']}", params={"stage": "Screening"}).json()
    assert pv and all(p["name"].split()[0] in p["body"] for p in pv)
    made = c.post(f"/plus/bulk/{jobs['Store']}?stage=Screening").json()
    assert made["drafts"] == len(pv)
    draft = next(e for e in c.get("/emails", params={"status": "Draft"}).json())
    short = c.post(f"/plus/tone/{draft['id']}", json={"tone": "Short"}).json()
    assert len(short["body"]) < len(draft["body"])
    posts = c.get(f"/plus/job-posts/{jobs['Cashier']}").json()["posts"]
    assert set(posts) == {"Naukri", "LinkedIn", "Apna", "WhatsApp"} and "₹" in posts["WhatsApp"]


def test_hindi_cv(c):
    txt = ("नाम: रमेश यादव\nशहर: नोएडा\nफोन: +91 90000 11111\nअनुभव:\nकैशियर | न्यू मार्ट, नोएडा | जनवरी 2021 से वर्तमान\n"
           "- प्रतिदिन 200 ग्राहकों की बिलिंग और नकद संभाला\nशिक्षा: बारहवीं, 2019\nकौशल: बिलिंग, ग्राहक सेवा, हिंदी")
    pv = c.post("/plus/hindi-cv/preview", data={"text": txt}).json()
    assert pv["hindi"] and "Ramesh Yadav" in pv["text"] and "Noida" in pv["text"]
    r = c.post("/plus/hindi-cv", json={"text": pv["text"]}).json()
    skills = {s["skill"] for s in r["candidate"]["skills"]}
    assert {"POS systems", "Customer service"} & skills


def test_decisions_blind_and_team(c):
    jobs, cands = ids(c)
    j = c.get("/plus/journal").json()
    assert j["missing"] and j["entries"]
    assert c.post("/plus/decision", json={"job_id": jobs["Cashier"], "candidate_id": cands["Rohit Verma"],
                                          "decision": "Not selected", "reason": "x"}).status_code == 422
    c.post("/plus/decision", json={"job_id": jobs["Cashier"], "candidate_id": cands["Rohit Verma"],
                                   "decision": "Not selected", "reason": "Over-qualified; expects ₹40k vs ₹22k band"})
    assert not any(m["name"] == "Rohit Verma" for m in c.get("/plus/journal").json()["missing"])
    c.put("/plus/blind-first", json={"on": True})
    card = c.get(f"/plus/blind-card/{cands['Sana Khan']}", params={"job_id": jobs["Cashier"]}).json()
    assert "Sana" not in str(card)
    c.post(f"/plus/reveal/{cands['Sana Khan']}")
    assert cands["Sana Khan"] in c.get("/plus/blind-first").json()["revealed"]
    c.put("/plus/blind-first", json={"on": False})
    perf = c.get("/plus/recruiters").json()
    assert {p["recruiter"] for p in perf} >= {"Demo Admin", "Demo Recruiter"}


def test_runners_up_and_silver(c):
    jobs, _ = ids(c)
    ru = c.get(f"/plus/runners-up/{jobs['Cashier']}").json()
    names = [r["name"] for r in ru]
    assert len(names) == len(set(names))
    assert len(c.get("/plus/silver").json()) <= 5


def test_portal_cv_builder_and_coach(c):
    b = c.post("/portal/plus/build-cv", json={"answers": {"name": "Ramesh Yadav", "city": "Noida",
                                                          "jobs": "Cashier, New Mart, Noida, Jan 2021 to now",
                                                          "daily": "POS billing, cash tally, helping customers",
                                                          "proud": "billed 200 customers a day"}}).json()
    assert "Cashier | New Mart" in b["text"] and "Jan 2021 – Present" in b["text"]
    h = _login(c, "sana.khan@example.com", "candidate123", "/portal/login")
    jobs, _ = ids(c)
    co = c.get(f"/portal/plus/coach/{jobs['Store']}", headers=h).json()
    assert co["tips"] and "score" not in str(co).lower()  # candidates never see scores


def test_portal_screening_test_slots_and_joining(c):
    h = _login(c, "sana.khan@example.com", "candidate123", "/portal/login")
    aid = c.get("/portal/applications", headers=h).json()[0]["application_id"]
    qs = c.get(f"/portal/plus/screen/{aid}", headers=h).json()["questions"]
    c.post(f"/portal/plus/screen/{aid}", headers=h, json={"answers": ["I billed 120 customers a day on the POS."] * len(qs)})
    assert c.get(f"/portal/plus/screen/{aid}", headers=h).json()["done"]
    t = c.post(f"/portal/plus/test/{aid}/start", headers=h).json()
    from backend.app.plus import portal_tools
    from backend.app import db
    import random
    seed = db.one("SELECT seed FROM plus_tests WHERE id=?", (t["test_id"],))["seed"]
    right = [q["answer"] for q in portal_tools._make_items(random.Random(seed))]
    assert c.post(f"/portal/plus/test/submit/{t['test_id']}", headers=h, json={"answers": right}).json()["right"] == 8
    # someone else can't touch Sana's application
    other = _login(c, "priya.nair@example.com", "candidate123", "/portal/login")
    assert c.get(f"/portal/plus/screen/{aid}", headers=other).status_code == 422
    # Priya is shortlisted: she picks her own slot
    pa = c.get("/portal/applications", headers=other).json()[0]["application_id"]
    sl = c.get(f"/portal/plus/slots/{pa}", headers=other).json()
    assert sl
    assert c.post(f"/portal/plus/slots/{pa}", headers=other, json={"date": sl[0]["date"], "time": sl[0]["time"]}).json()["ok"]
    assert c.get("/portal/applications", headers=other).json()[0]["stage"] == "Interview"
    # joining checklist opens only after an accepted offer
    jobs, cands = ids(c)
    an = next(r for r in c.get(f"/match/job/{jobs['Cashier']}").json() if r["name"] == "Anjali Sharma")
    ah = _login(c, "anjali.sharma@example.com", "candidate123", "/portal/login")
    up = c.post(f"/portal/plus/joining/{an['application_id']}", headers=ah, data={"doc": "PAN card"},
                files={"file": ("pan.pdf", b"%PDF-1.4")})
    assert up.status_code == 422
    o = c.post("/x/offers", json={"application_id": an["application_id"], "ctc": 264000, "joining_date": "2026-12-01"}).json()
    c.post(f"/x/offers/{o['id']}/send")
    c.post(f"/portal/offers/{o['id']}/respond", headers=ah, json={"response": "Accepted"})
    up = c.post(f"/portal/plus/joining/{an['application_id']}", headers=ah, data={"doc": "PAN card"},
                files={"file": ("pan.pdf", b"%PDF-1.4")})
    assert up.status_code == 200
    v = c.post(f"/plus/joining/{an['application_id']}/verify", params={"doc": "PAN card"}).json()
    assert v["done"] == 1
