"""Endpoints for the gap features: screening questions, offers, WhatsApp, calendar, sources, CSV, privacy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..security import RECRUITERS, current_candidate, current_user, require
from ..services import extras as svc
from ..services import recruit

x = APIRouter(prefix="/x", tags=["more features"])
px = APIRouter(prefix="/portal", tags=["candidate portal"])
rec = require(*RECRUITERS)
admin = require("Admin")


def _err(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (svc.ExtraError, ValueError) as e:
        raise HTTPException(422, str(e)) from None


class QIn(BaseModel):
    question: str
    kind: str = "yesno"
    ideal: str | None = None
    knockout: bool = False


class AnswersIn(BaseModel):
    answers: dict[int, str]


class OfferIn(BaseModel):
    application_id: int
    ctc: int
    joining_date: str
    designation: str | None = None
    reporting_to: str | None = None
    probation_months: int = 6


class OfferText(BaseModel):
    letter: str


class SourceIn(BaseModel):
    source: str
    referred_by: str | None = None


class RespondIn(BaseModel):
    response: str
    note: str = ""


# ------------------------------------------------------------ screening questions
@x.get("/jobs/{jid}/questions")
def list_q(jid: int, u=Depends(current_user)):
    return svc.questions(jid)


@x.get("/jobs/{jid}/questions/suggest")
def suggest_q(jid: int, u=Depends(current_user)):
    return svc.suggest_questions(jid)


@x.post("/jobs/{jid}/questions")
def add_q(jid: int, body: QIn, u=Depends(rec)):
    return _err(svc.add_question, jid, body.question, body.kind, body.ideal, body.knockout, u["name"])


@x.delete("/questions/{qid}")
def del_q(qid: int, u=Depends(rec)):
    svc.delete_question(qid, u["name"])
    return {"ok": True}


@x.get("/applications/{aid}/answers")
def answers(aid: int, u=Depends(current_user)):
    return svc.answers_for(aid)


@x.get("/jobs/{jid}/knockouts")
def knockouts(jid: int, u=Depends(current_user)):
    return {str(k): v for k, v in svc.job_knockouts(jid).items()}


# ------------------------------------------------------------ offers
@x.post("/offers")
def draft_offer(body: OfferIn, u=Depends(rec)):
    return _err(svc.draft_offer, body.application_id, body.ctc, body.joining_date, u["name"], body.designation,
                body.reporting_to, body.probation_months)


@x.get("/offers")
def list_offers(application_id: int | None = None, candidate_id: int | None = None, u=Depends(current_user)):
    return svc.offers_for(application_id, candidate_id)


@x.patch("/offers/{oid}")
def edit_offer(oid: int, body: OfferText, u=Depends(rec)):
    return _err(svc.update_offer_text, oid, body.letter)


@x.post("/offers/{oid}/send")
def send_offer(oid: int, u=Depends(rec)):
    return svc.send_offer(oid, u["name"])


@x.get("/offers/{oid}/docx")
def offer_docx(oid: int, u=Depends(current_user)):
    return Response(svc.offer_docx(oid), media_type="application/vnd.openxmlformats-officedocument."
                                                     "wordprocessingml.document")


# ------------------------------------------------------------ WhatsApp + calendar
@x.get("/emails/{eid}/whatsapp")
def whatsapp(eid: int, u=Depends(current_user)):
    return svc.whatsapp_for_email(eid)


@x.get("/interviews/{iid}/ics")
def ics(iid: int, u=Depends(current_user)):
    return Response(svc.ics(iid), media_type="text/calendar")


# ------------------------------------------------------------ sources, metrics, export
@x.get("/sources")
def sources(u=Depends(current_user)):
    return svc.SOURCES


@x.patch("/applications/{aid}/source")
def set_source(aid: int, body: SourceIn, u=Depends(rec)):
    return _err(svc.set_source, aid, body.source, body.referred_by, u["name"])


@x.get("/metrics")
def metrics(u=Depends(current_user)):
    return svc.metrics()


@x.get("/jobs/{jid}/export.csv")
def export(jid: int, u=Depends(current_user)):
    return Response(svc.job_csv(jid), media_type="text/csv")


# ------------------------------------------------------------ privacy (admin)
@x.get("/privacy")
def privacy(days: int = 180, u=Depends(admin)):
    return svc.privacy_status(days)


@x.post("/privacy/purge")
def purge(days: int = 180, u=Depends(admin)):
    return svc.purge_old(days, u["name"])


@x.post("/candidates/{cid}/erase")
def erase(cid: int, u=Depends(admin)):
    return svc.erase_candidate(cid, u["name"])


# ------------------------------------------------------------ candidate portal side
def _own_app(cid: int, aid: int) -> dict:
    a = recruit.get_app(aid)
    if a["candidate_id"] != cid:
        raise HTTPException(404, "Application not found")
    return a


@px.get("/applications/{aid}/questions")
def my_questions(aid: int, c=Depends(current_candidate)):
    _own_app(c["candidate_id"], aid)
    r = svc.answers_for(aid)
    # candidates never see the 'ideal' answer or whether they passed
    return [{"id": q["id"], "question": q["question"], "kind": q["kind"], "answer": q["answer"]} for q in r["items"]]


@px.post("/applications/{aid}/answers")
def my_answers(aid: int, body: AnswersIn, c=Depends(current_candidate)):
    _own_app(c["candidate_id"], aid)
    svc.save_answers(aid, body.answers)
    return {"ok": True}


@px.get("/offers")
def my_offers(c=Depends(current_candidate)):
    return [{k: o[k] for k in ("id", "application_id", "job_title", "designation", "ctc_text", "joining_date",
                                "location", "letter", "status", "sent_at", "responded_at")}
            for o in svc.offers_for(cid=c["candidate_id"]) if o["status"] != "Draft"]


@px.get("/offers/{oid}/docx")
def my_offer_docx(oid: int, c=Depends(current_candidate)):
    o = svc.get_offer(oid)
    if o["candidate_id"] != c["candidate_id"] or o["status"] == "Draft":
        raise HTTPException(404, "Offer not found")
    return Response(svc.offer_docx(oid), media_type="application/vnd.openxmlformats-officedocument."
                                                     "wordprocessingml.document")


@px.post("/offers/{oid}/respond")
def respond_offer(oid: int, body: RespondIn, c=Depends(current_candidate)):
    return _err(svc.respond_offer, c["candidate_id"], oid, body.response, body.note)


@px.get("/interviews/{iid}/ics")
def my_ics(iid: int, c=Depends(current_candidate)):
    from ..services import interviews
    if interviews.get(iid)["candidate_id"] != c["candidate_id"]:
        raise HTTPException(404, "Interview not found")
    return Response(svc.ics(iid), media_type="text/calendar")


@px.post("/me/erase")
def erase_me(c=Depends(current_candidate)):
    return svc.erase_candidate(c["candidate_id"], "Candidate (self)")
