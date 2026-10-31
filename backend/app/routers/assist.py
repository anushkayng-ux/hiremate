"""Interviews, emails, AI writing, knowledge, assistant, analytics and settings endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db
from ..adapters import llm
from ..adapters.embedder import get_embedder
from ..adapters.vectorstore import get_store
from ..core import ml
from ..core.parsing import ParseError, read_file
from ..security import RECRUITERS, current_user, hash_pw, require
from ..services import analytics, assist, assistant, files, interviews, knowledge, recruit

ivs = APIRouter(prefix="/interviews", tags=["interviews"])
emails = APIRouter(prefix="/emails", tags=["emails"])
ai = APIRouter(prefix="/ai", tags=["ai"])
kb = APIRouter(prefix="/knowledge", tags=["knowledge"])
bot = APIRouter(prefix="/assistant", tags=["assistant"])
stats = APIRouter(prefix="/analytics", tags=["analytics"])
sets = APIRouter(prefix="/settings", tags=["settings"])

rec = require(*RECRUITERS)
admin = require("Admin")


# ------------------------------------------------------------- interviews
class ScheduleIn(BaseModel):
    job_id: int
    candidate_id: int
    date: str
    time: str
    mode: str = "In person"
    interviewer: str = "Area Manager"


class FeedbackIn(BaseModel):
    job_id: int
    candidate_id: int
    scores: dict[str, int] = {}
    text: str = ""


@ivs.get("")
def list_interviews(when: str | None = None, candidate_id: int | None = None, job_id: int | None = None,
                    u=Depends(current_user)):
    return interviews.list_all(when, candidate_id, job_id)


@ivs.post("")
def schedule(body: ScheduleIn, u=Depends(rec)):
    try:
        return interviews.schedule(body.job_id, body.candidate_id, body.date, body.time, body.mode, body.interviewer,
                                   u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@ivs.patch("/{iid}")
def set_status(iid: int, status: str, u=Depends(current_user)):
    return interviews.set_status(iid, status, u["name"])


@ivs.post("/feedback")
def feedback(body: FeedbackIn, u=Depends(current_user)):
    return interviews.save_feedback(body.job_id, body.candidate_id, body.scores, body.text, u["name"])


@ivs.get("/feedback")
def get_feedback(job_id: int, candidate_id: int, u=Depends(current_user)):
    return interviews.get_feedback(job_id, candidate_id)


# ------------------------------------------------------------- AI writing
@ai.get("/summary")
def summary(job_id: int, candidate_id: int, u=Depends(current_user)):
    return assist.summary(job_id, candidate_id)


@ai.get("/questions")
def questions(job_id: int, candidate_id: int, u=Depends(current_user)):
    return assist.questions(job_id, candidate_id)


@ai.get("/assessment")
def assessment(job_id: int, candidate_id: int | None = None, u=Depends(current_user)):
    return assist.assessment(job_id, candidate_id)


@ai.get("/feedback-summary")
def fb_summary(job_id: int, candidate_id: int, u=Depends(current_user)):
    a = recruit.app_for(job_id, candidate_id)
    if not a:
        raise HTTPException(404, "Candidate is not in this job")
    return assist.feedback_summary(a["id"])


# ------------------------------------------------------------- emails
class DraftIn(BaseModel):
    job_id: int
    candidate_id: int
    type: str
    lang: str = "English"


class EmailEdit(BaseModel):
    subject: str | None = None
    body: str | None = None


@emails.get("")
def list_emails(candidate_id: int | None = None, job_id: int | None = None, status: str | None = None,
                u=Depends(current_user)):
    return assist.list_emails(candidate_id, job_id, status)


@emails.get("/types")
def email_types():
    return assist.EMAIL_TYPES


@emails.post("")
def draft(body: DraftIn, u=Depends(rec)):
    try:
        return assist.draft_email(body.job_id, body.candidate_id, body.type, body.lang, u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@emails.patch("/{eid}")
def edit(eid: int, body: EmailEdit, u=Depends(rec)):
    try:
        return assist.update_email(eid, body.subject, body.body)
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@emails.post("/{eid}/approve")
def approve(eid: int, u=Depends(rec)):
    return send(eid, u)


@emails.post("/{eid}/send")
def send(eid: int, u=Depends(rec)):
    """Recruiter presses Send. Goes to the candidate portal (and real email if SMTP is set)."""
    try:
        return assist.send_email(eid, u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@emails.delete("/{eid}")
def delete_draft(eid: int, u=Depends(rec)):
    """Only drafts can be deleted. Sent emails stay in the record."""
    e = assist.get_email(eid)
    if e["status"] != "Draft":
        raise HTTPException(422, "Only drafts can be deleted.")
    db.run("DELETE FROM emails WHERE id=?", (eid,))
    return {"ok": True}


@emails.get("/inbox/list")
def inbox(all: bool = False, u=Depends(current_user)):
    return assist.inbox(unread_only=not all)


@emails.get("/thread/list")
def thread(job_id: int, candidate_id: int, u=Depends(current_user)):
    a = recruit.app_for(job_id, candidate_id)
    return assist.thread(a["id"]) if a else []


@emails.post("/{eid}/read")
def read(eid: int, u=Depends(current_user)):
    assist.mark_read(eid)
    return {"ok": True}


@emails.post("/{eid}/ai-reply")
def ai_reply(eid: int, u=Depends(rec)):
    try:
        return assist.draft_reply(eid, u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


# ------------------------------------------------------------- knowledge
class DocIn(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    type: str = "Policy"


class DocEdit(BaseModel):
    title: str | None = None
    text: str | None = None
    type: str | None = None


class AskIn(BaseModel):
    question: str


@kb.get("")
def all_docs(kind: str | None = None, q: str | None = None, u=Depends(current_user)):
    return knowledge.all_docs(kind, q)


@kb.post("")
def create_doc(body: DocIn, u=Depends(rec)):
    return knowledge.create_doc(body.title, body.text, body.type, u["name"])


@kb.post("/upload")
async def upload_docs(files_: list[UploadFile] = File(..., alias="files"), u=Depends(rec)):
    """Upload any mix of JDs, CVs and policies; each is auto-sorted."""
    from ..core.parsing import classify
    out = []
    for f in files_:
        try:
            text = read_file(await f.read(), f.filename or "doc.txt")
            kind = classify(text)
            if kind == "JD":
                r = recruit.create_job(text, u["name"], source="Upload", file_name=f.filename)
                out.append({"file_name": f.filename, "ok": True, "kind": "JD", "title": r["title"]})
            elif kind == "CV":
                r = recruit.create_candidate(text, u["name"], source="Upload", file_name=f.filename)
                out.append({"file_name": f.filename, "ok": True, "kind": "CV", "title": r["name"]})
            else:
                title = (f.filename or "Document").rsplit(".", 1)[0].replace("_", " ")
                r = knowledge.create_doc(title, text, "FAQ" if "faq" in title.lower() else "Policy", u["name"],
                                         file_name=f.filename, source="Upload")
                out.append({"file_name": f.filename, "ok": True, "kind": r["type"], "title": r["title"]})
        except (ValueError, ParseError) as e:
            out.append({"file_name": f.filename, "ok": False, "error": str(e)})
    return out


@kb.post("/ask")
def ask(body: AskIn, u=Depends(current_user)):
    return knowledge.answer(body.question)


@kb.get("/{did}")
def get_doc(did: int, u=Depends(current_user)):
    return knowledge.get_doc(did)


@kb.patch("/{did}")
def edit_doc(did: int, body: DocEdit, u=Depends(rec)):
    return knowledge.update_doc(did, u["name"], body.title, body.text, body.type)


@kb.delete("/{did}")
def delete_doc(did: int, u=Depends(rec)):
    knowledge.delete_doc(did, u["name"])
    return {"ok": True}


class DocxIn(BaseModel):
    title: str
    text: str


@kb.post("/docx")
def to_docx(body: DocxIn, u=Depends(current_user)):
    return files.make_docx(body.title, body.text)


@kb.get("/files/{fid}")
def download(fid: int, u=Depends(current_user)):
    f = files.get_file(fid)
    if not f:
        raise HTTPException(404, "File not found")
    return FileResponse(f["path"], media_type=f["mime"], filename=f["name"])


# ------------------------------------------------------------- assistant
@bot.post("/chat")
async def chat(session_id: str = Form(...), message: str = Form(""), job_id: int | None = Form(None),
               candidate_id: int | None = Form(None), files_: list[UploadFile] | None = File(None, alias="files"),
               u=Depends(current_user)):
    atts = []
    for f in files_ or []:
        try:
            atts.append({"name": f.filename, "text": read_file(await f.read(), f.filename or "file.txt")})
        except ParseError as e:
            atts.append({"name": f.filename, "text": "", "error": str(e)})
    if u["role"] == "Interviewer" and atts:
        raise HTTPException(403, "Interviewers can't upload files")
    return assistant.chat(session_id, u, message, atts, {"job_id": job_id, "candidate_id": candidate_id})


@bot.get("/history/{session_id}")
def history(session_id: str, u=Depends(current_user)):
    return assistant.history(session_id)


@bot.delete("/history/{session_id}")
def clear(session_id: str, u=Depends(current_user)):
    assistant.clear(session_id)
    return {"ok": True}


# ------------------------------------------------------------- analytics
@stats.get("/dashboard")
def dashboard(u=Depends(current_user)):
    return analytics.dashboard()


@stats.get("")
def all_stats(u=Depends(current_user)):
    return analytics.analytics()


# ------------------------------------------------------------- settings
class Weights(BaseModel):
    skills: int = Field(ge=0, le=100)
    text: int = Field(ge=0, le=100)
    exp: int = Field(ge=0, le=100)


class UserIn(BaseModel):
    email: str
    name: str
    role: str
    password: str = Field(min_length=6)


@sets.get("")
def get_settings(u=Depends(current_user)):
    return {"weights": recruit.weights(), "blind": db.get_setting("blind", False), "llm": llm.status(),
            "embedder": get_embedder().name, "vector_store": get_store().name,
            "ml": {"logistic_regression_train_accuracy": round(ml.lr_accuracy(), 2)}}


@sets.put("/weights")
def set_weights(body: Weights, u=Depends(rec)):
    if body.skills + body.text + body.exp == 0:
        raise HTTPException(422, "At least one weight must be above 0")
    db.set_setting("weights", body.model_dump())
    recruit.recompute_all()
    db.log("Score weights changed", str(body.model_dump()), u["name"])
    return recruit.weights()


class AIIn(BaseModel):
    provider: str
    model: str | None = None
    gemini_key: str | None = None
    anthropic_key: str | None = None
    ollama_url: str | None = None
    clear_keys: bool = False


@sets.get("/ai")
def get_ai(u=Depends(current_user)):
    return llm.public_settings()


@sets.put("/ai")
def set_ai(body: AIIn, u=Depends(admin)):
    try:
        out = llm.save_settings(body.provider, body.model, body.gemini_key, body.anthropic_key, body.ollama_url,
                                body.clear_keys)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    db.log("AI model changed", out["label"], u["name"])
    return out


@sets.post("/ai/test")
def test_ai(u=Depends(admin)):
    return llm.test_connection()


@sets.put("/blind")
def set_blind(on: bool, u=Depends(rec)):
    db.set_setting("blind", on)
    return {"blind": on}


@sets.get("/users")
def users(u=Depends(current_user)):
    return db.rows("SELECT id, email, name, role, created_at FROM users ORDER BY id")


@sets.post("/users")
def add_user(body: UserIn, u=Depends(admin)):
    if body.role not in ("Admin", "Recruiter", "Interviewer"):
        raise HTTPException(422, "Role must be Admin, Recruiter or Interviewer")
    if db.one("SELECT id FROM users WHERE lower(email)=lower(?)", (body.email,)):
        raise HTTPException(409, "That email already has an account")
    uid = db.run("INSERT INTO users(email,name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
                 (body.email, body.name, body.role, hash_pw(body.password), db.now()))
    return db.one("SELECT id, email, name, role FROM users WHERE id=?", (uid,))


@sets.post("/reset-demo")
def reset_demo(u=Depends(admin)):
    from ..seed import reset_and_seed
    reset_and_seed()
    return {"ok": True}


@sets.get("/activity")
def activity(limit: int = 50, u=Depends(current_user)):
    return db.rows("SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,))


# ------------------------------------------------------------- screening criteria
from ..services import criteria as crit_svc  # noqa: E402

crit = APIRouter(prefix="/criteria", tags=["criteria"])


class CritIn(BaseModel):
    text: str = Field(min_length=2)
    job_id: int | None = None
    kind: str | None = None
    check_type: str | None = None
    value: str | None = None
    points: int | None = Field(None, ge=0, le=50)


class CritEdit(BaseModel):
    text: str | None = None
    kind: str | None = None
    check_type: str | None = None
    value: str | None = None
    points: int | None = Field(None, ge=0, le=50)
    active: bool | None = None


class TextIn(BaseModel):
    text: str


@crit.get("")
def list_criteria(job_id: int | None = None, scope: str = "job", u=Depends(current_user)):
    """scope=job: this job's rules + rules for all jobs. scope=global: only all-job rules. scope=all: everything."""
    if scope == "all":
        return crit_svc.list_all()
    return crit_svc.list_for(None if scope == "global" else job_id, include_global=scope != "global")


@crit.post("/preview")
def preview(body: TextIn, u=Depends(current_user)):
    p = crit_svc.parse(body.text)
    return {**p, "how": crit_svc.describe(p)}


@crit.post("")
def add_criterion(body: CritIn, u=Depends(rec)):
    try:
        return crit_svc.create(body.text, body.job_id, u["name"], body.kind, body.check_type, body.value, body.points)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@crit.patch("/{cid}")
def edit_criterion(cid: int, body: CritEdit, u=Depends(rec)):
    try:
        return crit_svc.update(cid, u["name"], **body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@crit.delete("/{cid}")
def delete_criterion(cid: int, u=Depends(rec)):
    crit_svc.delete(cid, u["name"])
    return {"ok": True}


@sets.get("/guidelines")
def get_guidelines(u=Depends(current_user)):
    return {"text": crit_svc.guidelines()}


@sets.put("/guidelines")
def set_guidelines(body: TextIn, u=Depends(rec)):
    db.set_setting("ai_guidelines", body.text.strip()[:3000])
    db.log("AI guidelines updated", body.text.strip()[:80], u["name"])
    return {"text": crit_svc.guidelines()}


# ------------------------------------------------------------------ smart helpers (time savers)
from ..services import smart  # noqa: E402

sm = APIRouter(prefix="/smart", tags=["smart"])


class MoveIn(BaseModel):
    stage: str
    draft: bool = True


class UndoIn(BaseModel):
    old_stage: str
    email_id: int | None = None


class BookIn(BaseModel):
    job_id: int
    candidate_id: int
    date: str
    time: str
    mode: str = "In person"
    interviewer: str = "Store Manager"


@sm.get("/flags/{cid}")
def flags(cid: int, job_id: int | None = None, u=Depends(current_user)):
    return smart.red_flags(cid, job_id)


@sm.get("/slots")
def slots(job_id: int, candidate_id: int, interviewer: str | None = None, u=Depends(current_user)):
    return smart.free_slots(job_id, candidate_id, interviewer)


@sm.post("/book")
def book(body: BookIn, u=Depends(require(*RECRUITERS))):
    try:
        return smart.book(body.job_id, body.candidate_id, body.date, body.time, body.mode, body.interviewer, u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@sm.post("/move/{app_id}")
def move(app_id: int, body: MoveIn, u=Depends(require(*RECRUITERS))):
    try:
        return smart.move(app_id, body.stage, u["name"], body.draft)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@sm.post("/undo/{app_id}")
def undo(app_id: int, body: UndoIn, u=Depends(require(*RECRUITERS))):
    return smart.undo(app_id, body.old_stage, body.email_id, u["name"])


@sm.get("/waiting")
def waiting(u=Depends(current_user)):
    return smart.waiting()


@sm.get("/next/{job_id}")
def next_action(job_id: int, u=Depends(current_user)):
    return smart.next_action(job_id)
