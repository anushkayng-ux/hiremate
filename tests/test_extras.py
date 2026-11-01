"""Tests for the gap features: screening questions, offers, WhatsApp, calendar, sources, CSV, privacy."""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
os.environ["LLM_PROVIDER"] = "template"
os.environ.setdefault("VECTOR_STORE", "memory")
os.environ.setdefault("EMBEDDER", "hashing")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        client.post("/settings/reset-demo", headers=_h(client))
        client.headers["Authorization"] = _h(client)["Authorization"]
        yield client


def _h(client):
    t = client.post("/auth/login", json={"email": "admin@hiremate.demo", "password": "recruit123"}).json()["token"]
    return {"Authorization": "Bearer " + t}


def _cand(client, email):
    t = client.post("/portal/login", json={"email": email, "password": "candidate123"}).json()["token"]
    return {"Authorization": "Bearer " + t}


def _job(c, word):
    return next(j for j in c.get("/jobs").json() if word in j["title"])


def test_screening_questions_flag_but_never_reject(c):
    sm = _job(c, "Store Manager")
    qs = c.get(f"/x/jobs/{sm['id']}/questions").json()
    assert qs and any(q["knockout"] for q in qs)
    ko = c.get(f"/x/jobs/{sm['id']}/knockouts").json()
    assert ko  # one seeded person answered a 'must' question the other way
    flagged = int(next(iter(ko)))
    ranked = c.get(f"/match/job/{sm['id']}").json()
    person = next(r for r in ranked if r["candidate_id"] == flagged)
    assert person["stage"] != "Rejected"  # a flag, not a rejection


def test_add_and_validate_question(c):
    j = _job(c, "Cashier")
    r = c.post(f"/x/jobs/{j['id']}/questions", json={"question": "Years on a POS counter?", "kind": "number",
                                                     "ideal": ">= 1", "knockout": True})
    assert r.status_code == 200
    bad = c.post(f"/x/jobs/{j['id']}/questions", json={"question": "Years?", "kind": "number", "ideal": "lots"})
    assert bad.status_code == 422
    c.delete(f"/x/questions/{r.json()['id']}")


def test_candidate_answers_hide_ideal(c):
    h = _cand(c, "rohit.verma@example.com")
    apps = c.get("/portal/applications", headers=h).json()
    qs = c.get(f"/portal/applications/{apps[0]['application_id']}/questions", headers=h).json()
    assert qs and "ideal" not in qs[0] and "ok" not in qs[0]
    r = c.post(f"/portal/applications/{apps[0]['application_id']}/answers", headers=h,
               json={"answers": {str(qs[0]["id"]): "Yes"}})
    assert r.status_code == 200
    # can't answer for someone else's application
    other = _cand(c, "priya.nair@example.com")
    assert c.post(f"/portal/applications/{apps[0]['application_id']}/answers", headers=other,
                  json={"answers": {}}).status_code == 404


def test_offer_flow_numbers_are_kept(c):
    j = _job(c, "Cashier")
    ranked = c.get(f"/match/job/{j['id']}").json()
    anjali = next(r for r in ranked if r["name"] == "Anjali Sharma")
    o = c.post("/x/offers", json={"application_id": anjali["application_id"], "ctc": 276000,
                                  "joining_date": "2026-12-01"}).json()
    assert "₹2,76,000" in o["letter"] and o["status"] == "Draft"
    h = _cand(c, "anjali.sharma@example.com")
    assert c.get("/portal/offers", headers=h).json() == []  # drafts are never shown
    assert c.post(f"/x/offers/{o['id']}/send").json()["status"] == "Sent"
    mine = c.get("/portal/offers", headers=h).json()
    assert mine and mine[0]["ctc_text"] == "₹2,76,000"
    assert c.get(f"/x/offers/{o['id']}/docx").content[:2] == b"PK"
    r = c.post(f"/portal/offers/{o['id']}/respond", headers=h, json={"response": "Accepted", "note": "Thank you"})
    assert r.json()["status"] == "Accepted"
    assert c.get("/x/metrics").json()["offers"]["acceptance_rate"] == 100
    inbox = c.get("/emails/inbox/list").json()
    assert any("Offer accepted" in (e.get("subject") or "") for e in inbox)


def test_whatsapp_and_calendar(c):
    em = c.get("/emails").json()
    wa = c.get(f"/x/emails/{em[0]['id']}/whatsapp").json()
    assert wa["text"] and len(wa["text"]) < 700
    iv = c.get("/interviews").json()[0]
    ics = c.get(f"/x/interviews/{iv['id']}/ics").text
    assert "BEGIN:VEVENT" in ics and "Asia/Kolkata" in ics


def test_sources_metrics_and_csv(c):
    m = c.get("/x/metrics").json()
    assert {s["source"] for s in m["by_source"]} >= {"Referral", "Naukri"}
    assert m["time_to_interview_days"] is not None
    j = _job(c, "Store Manager")
    csv_ = c.get(f"/x/jobs/{j['id']}/export.csv").content.decode("utf-8-sig")
    assert csv_.startswith("Rank,Name") and "Priya Nair" in csv_
    ranked = c.get(f"/match/job/{j['id']}").json()
    r = c.patch(f"/x/applications/{ranked[0]['application_id']}/source", json={"source": "Walk-in"})
    assert r.json()["source"] == "Walk-in"
    assert c.patch(f"/x/applications/{ranked[0]['application_id']}/source",
                   json={"source": "Carrier pigeon"}).status_code == 422


def test_signup_needs_consent(c):
    files = {"file": ("cv.txt", b"Test Person\nLocation: Noida\nSummary: Cashier with five years of billing and "
                                b"customer service experience in supermarkets and pharmacies across Noida.\n"
                                b"Skills: POS billing, cash handling, customer service")}
    no = c.post("/portal/signup", data={"name": "Test Person", "email": "t1@example.com", "password": "secret1"},
                files=files)
    assert no.status_code == 422
    yes = c.post("/portal/signup", data={"name": "Test Person", "email": "t2@example.com", "password": "secret1",
                                         "consent": "true"}, files=files)
    assert yes.status_code == 200


def test_erase_my_data(c):
    h = _cand(c, "sana.khan@example.com")
    cid = c.get("/portal/me", headers=h).json()["id"]
    assert c.post("/portal/me/erase", headers=h).json()["ok"]
    cand = c.get(f"/candidates/{cid}").json()
    assert cand["email"] is None and "erased" in cand["cv_text"]
    assert c.post("/portal/login", json={"email": "sana.khan@example.com", "password": "candidate123"}).status_code == 401


def test_privacy_admin_only(c):
    rec = c.post("/auth/login", json={"email": "recruiter@hiremate.demo", "password": "recruit123"}).json()["token"]
    assert c.get("/x/privacy", headers={"Authorization": "Bearer " + rec}).status_code == 403
    assert c.get("/x/privacy?days=1").json()["total"] >= 1
