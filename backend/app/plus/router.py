"""HTTP endpoints for HireMate Plus. Staff routes under /plus, candidate routes under /portal/plus."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..core.parsing import ParseError, read_file
from ..security import RECRUITERS, current_candidate, current_user, require
from . import hr_tools as hr
from . import insights as ins
from . import portal_tools as pt
from . import talent as tl

plus = APIRouter(prefix="/plus", tags=["HireMate Plus"])
pplus = APIRouter(prefix="/portal/plus", tags=["HireMate Plus (candidate)"])
rec = require(*RECRUITERS)


def _e(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


class JobCand(BaseModel):
    job_id: int
    candidate_id: int


class Ask(BaseModel):
    question: str


class Band(BaseModel):
    min: int
    max: int


class Notes(BaseModel):
    job_id: int
    candidate_id: int
    notes: str


class Scorecard(Notes):
    rows: list[dict]


class BankQ(BaseModel):
    question: str
    qtype: str = "General"


class Vote(BaseModel):
    useful: bool


class NextQ(BaseModel):
    job_id: int
    candidate_id: int
    asked: list[str] = []
    notes: str = ""


class Panel(BaseModel):
    job_id: int
    candidate_id: int
    rater: str
    scores: dict[str, int]


class Tone(BaseModel):
    tone: str


class Decision(BaseModel):
    job_id: int
    candidate_id: int
    decision: str
    reason: str


class Merge(BaseModel):
    keep_id: int
    dup_id: int


class Ids(BaseModel):
    candidate_ids: list[int]


class Toggle(BaseModel):
    on: bool


class HindiIn(BaseModel):
    text: str
    job_id: int | None = None


class CVAnswers(BaseModel):
    answers: dict[str, str]


class ScreenIn(BaseModel):
    answers: list[str]


class SlotIn(BaseModel):
    date: str
    time: str
    mode: str = "In person"


class TestIn(BaseModel):
    answers: list


# ============================================================ overview pages
@plus.get("/briefing")
def briefing(u=Depends(current_user)):
    return ins.briefing(u["name"])


@plus.get("/candidate/{cid}")
def candidate_panel(cid: int, job_id: int, u=Depends(current_user)):
    out = ins.candidate_panel(cid, job_id)
    out["success"] = tl.success_profile(job_id, cid)
    out["integrity"] = tl.integrity(cid)
    out["career"] = tl.career_path(cid)
    out["why_not"] = tl.why_not(job_id, cid)
    out["panel"] = hr.panel_check(job_id, cid)
    from ..services import recruit
    a = recruit.app_for(job_id, cid)
    if a:
        out["screening"] = pt.screening_result(a["id"])
        out["test"] = pt.test_result(a["id"])
        out["joining"] = pt.checklist(a["id"])
    return out


# ============================================================ insights
@plus.get("/best-fit")
def best_fit(u=Depends(current_user)):
    return ins.best_fit_elsewhere()


@plus.post("/best-fit/move")
def best_fit_move(body: JobCand, u=Depends(rec)):
    return ins.move_to_better_fit(body.candidate_id, body.job_id, u["name"])


@plus.get("/dropout")
def dropout(u=Depends(current_user)):
    return ins.dropout_list()


@plus.get("/dropout/{app_id}/nudge")
def nudge(app_id: int, u=Depends(current_user)):
    return ins.nudge_message(app_id)


@plus.get("/pay-band/{job_id}")
def get_band(job_id: int, u=Depends(current_user)):
    from ..services import recruit
    lo, hi = ins.pay_band(recruit.get_job(job_id))
    return {"min": lo, "max": hi}


@plus.put("/pay-band/{job_id}")
def put_band(job_id: int, body: Band, u=Depends(rec)):
    return _e(ins.set_pay_band, job_id, body.min, body.max, u["name"])


@plus.post("/ask-cv/{cid}")
def ask_cv(cid: int, body: Ask, u=Depends(current_user)):
    return ins.ask_cv(cid, body.question)


# ============================================================ talent
@plus.get("/hidden-gems")
def gems(u=Depends(current_user)):
    return tl.hidden_gems()


@plus.get("/jd-reality/{job_id}")
def jd_reality(job_id: int, u=Depends(current_user)):
    return tl.jd_reality(job_id)


@plus.get("/runners-up/{job_id}")
def runners(job_id: int, u=Depends(current_user)):
    return tl.runners_up(job_id)


@plus.post("/runners-up/{job_id}/invite")
def invite(job_id: int, body: Ids, u=Depends(rec)):
    return tl.invite_runners_up(job_id, body.candidate_ids, u["name"])


@plus.get("/silver")
def silver(u=Depends(current_user)):
    return tl.silver_list()


@plus.get("/offer-risk")
def offer_risk(u=Depends(current_user)):
    return tl.offer_at_risk()


@plus.get("/second-opinion")
def second(job_id: int, candidate_id: int, u=Depends(current_user)):
    return tl.second_opinion(job_id, candidate_id)


@plus.get("/pool-health")
def pool(u=Depends(current_user)):
    return tl.pool_health()


@plus.get("/skill-demand")
def demand(u=Depends(current_user)):
    return tl.skill_demand()


@plus.get("/duplicates")
def dups(u=Depends(current_user)):
    return tl.duplicates()


@plus.post("/duplicates/merge")
def merge(body: Merge, u=Depends(rec)):
    return _e(tl.merge, body.keep_id, body.dup_id, u["name"])


# ============================================================ HR tools
@plus.get("/job-posts/{job_id}")
def posts(job_id: int, u=Depends(current_user)):
    return hr.job_posts(job_id)


@plus.post("/notes-to-scorecard")
def notes(body: Notes, u=Depends(current_user)):
    return hr.notes_to_scorecard(body.job_id, body.candidate_id, body.notes)


@plus.post("/scorecard/save")
def save_card(body: Scorecard, u=Depends(current_user)):
    return hr.save_scorecard(body.job_id, body.candidate_id, body.rows, body.notes, u["name"])


@plus.get("/bank/{job_id}")
def bank(job_id: int, u=Depends(current_user)):
    return hr.bank(job_id)


@plus.post("/bank/{job_id}")
def bank_add(job_id: int, body: BankQ, u=Depends(current_user)):
    return _e(hr.bank_add, job_id, body.question, body.qtype, u["name"])


@plus.post("/bank/vote/{qid}")
def bank_vote(qid: int, body: Vote, u=Depends(current_user)):
    return hr.bank_vote(qid, body.useful)


@plus.post("/bank/{job_id}/import/{cid}")
def bank_import(job_id: int, cid: int, u=Depends(current_user)):
    return hr.bank_import_generated(job_id, cid, u["name"])


@plus.post("/hindi-cv/preview")
async def hindi_preview(file: UploadFile | None = File(None), text: str | None = Form(None), u=Depends(rec)):
    t = text or ""
    if file is not None:
        try:
            t = read_file(await file.read(), file.filename or "cv.txt")
        except ParseError as e:
            raise HTTPException(422, str(e)) from None
    return {"hindi": hr.is_hindi(t), "original": t, **hr.hindi_to_english(t)}


@plus.post("/hindi-cv")
def hindi_add(body: HindiIn, u=Depends(rec)):
    return _e(hr.add_hindi_cv, body.text, body.job_id, u["name"])


@plus.get("/recruiters")
def recruiters(u=Depends(current_user)):
    return hr.recruiter_performance()


@plus.post("/next-question")
def next_q(body: NextQ, u=Depends(current_user)):
    return hr.next_question(body.job_id, body.candidate_id, body.asked, body.notes)


@plus.post("/panel")
def panel(body: Panel, u=Depends(current_user)):
    return _e(hr.add_panel_rating, body.job_id, body.candidate_id, body.rater, body.scores, u["name"])


@plus.get("/roleplay/{job_id}")
def roleplay(job_id: int, u=Depends(current_user)):
    return hr.roleplay(job_id)


@plus.post("/tone/{eid}")
def tone(eid: int, body: Tone, u=Depends(rec)):
    return _e(hr.tone_switch, eid, body.tone, u["name"])


@plus.post("/policy-answer/{eid}")
def policy(eid: int, draft: bool = False, u=Depends(rec)):
    return hr.policy_answer(eid, u["name"], draft)


@plus.get("/bulk/{job_id}")
def bulk_prev(job_id: int, stage: str, u=Depends(current_user)):
    return hr.bulk_preview(job_id, stage)


@plus.post("/bulk/{job_id}")
def bulk(job_id: int, stage: str, u=Depends(rec)):
    return hr.bulk_create(job_id, stage, u["name"])


@plus.post("/decision")
def decision(body: Decision, u=Depends(rec)):
    return _e(hr.log_decision, body.job_id, body.candidate_id, body.decision, body.reason, u["name"])


@plus.get("/journal")
def journal(u=Depends(current_user)):
    return hr.journal()


@plus.get("/blind-first")
def blind_first(u=Depends(current_user)):
    return {"on": hr.blind_first_on(), "revealed": hr.revealed()}


@plus.put("/blind-first")
def set_blind(body: Toggle, u=Depends(rec)):
    return hr.set_blind_first(body.on, u["name"])


@plus.post("/reveal/{cid}")
def reveal(cid: int, u=Depends(current_user)):
    return hr.reveal(cid, u["name"])


@plus.get("/blind-card/{cid}")
def blind_card(cid: int, job_id: int, u=Depends(current_user)):
    return hr.blind_card(cid, job_id)


@plus.get("/joining")
def joining(u=Depends(current_user)):
    return pt.joining_overview()


@plus.post("/joining/{app_id}/verify")
def verify(app_id: int, doc: str, u=Depends(rec)):
    return pt.verify_doc(app_id, doc, u["name"])


@plus.get("/joining/{app_id}/file")
def joining_file(app_id: int, doc: str, u=Depends(current_user)):
    f = pt.doc_file(app_id, doc)
    if not f:
        raise HTTPException(404, "File not found")
    return Response(f[1], media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{f[0]}"'})


# ============================================================ candidate portal side
def _cid(c):
    return c["candidate_id"]


@pplus.get("/cv-questions")
def cv_questions():
    return pt.CV_QUESTIONS


@pplus.post("/build-cv")
def build_cv(body: CVAnswers):
    """Open to everyone (also before sign-up): makes CV text from simple answers."""
    return _e(pt.build_cv, body.answers)


@pplus.get("/coach/{job_id}")
def coach(job_id: int, c=Depends(current_candidate)):
    return ins.cv_coach(_cid(c), job_id)


@pplus.get("/timing")
def timing(c=Depends(current_candidate)):
    return pt.status_timing(_cid(c))


@pplus.get("/screen/{app_id}")
def screen_q(app_id: int, c=Depends(current_candidate)):
    _e(pt._own, _cid(c), app_id)
    done = pt.screening_result(app_id) is not None
    return {"done": done, "questions": [] if done else pt.screen_questions(app_id)}


@pplus.post("/screen/{app_id}")
def screen_submit(app_id: int, body: ScreenIn, c=Depends(current_candidate)):
    return _e(pt.submit_screening, _cid(c), app_id, body.answers)


@pplus.get("/slots/{app_id}")
def slots(app_id: int, c=Depends(current_candidate)):
    return _e(pt.my_slots, _cid(c), app_id)


@pplus.post("/slots/{app_id}")
def book(app_id: int, body: SlotIn, c=Depends(current_candidate)):
    return _e(pt.book_my_slot, _cid(c), app_id, body.date, body.time, body.mode)


@pplus.get("/joining/{app_id}")
def my_join(app_id: int, c=Depends(current_candidate)):
    _e(pt._own, _cid(c), app_id)
    return pt.checklist(app_id)


@pplus.post("/joining/{app_id}")
async def my_upload(app_id: int, doc: str = Form(...), file: UploadFile = File(...), c=Depends(current_candidate)):
    return _e(pt.upload_doc, _cid(c), app_id, doc, file.filename or "file", await file.read())


@pplus.get("/test/{app_id}")
def test_info(app_id: int, c=Depends(current_candidate)):
    _e(pt._own, _cid(c), app_id)
    return {"applies": pt.test_applies(app_id), "done": pt.test_result(app_id) is not None}


@pplus.post("/test/{app_id}/start")
def test_start(app_id: int, c=Depends(current_candidate)):
    return _e(pt.start_test, _cid(c), app_id)


@pplus.post("/test/submit/{tid}")
def test_submit(tid: int, body: TestIn, c=Depends(current_candidate)):
    return _e(pt.submit_test, _cid(c), tid, body.answers)
