"""Candidate portal endpoints. Candidates only see their own data, never scores or drafts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..core.parsing import ParseError, read_file
from ..security import current_candidate
from ..services import portal as svc

portal = APIRouter(prefix="/portal", tags=["candidate portal"])


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    phone: str | None = None
    location: str | None = None


class ReplyIn(BaseModel):
    body: str


class RespondIn(BaseModel):
    response: str
    note: str = ""


class ApplyIn(BaseModel):
    job_id: int


def _err(fn, *a):
    try:
        return fn(*a)
    except svc.PortalError as e:
        raise HTTPException(422, str(e)) from None


async def _cv_text(file: UploadFile | None, text: str | None) -> tuple[str, str | None]:
    if file is not None:
        try:
            return read_file(await file.read(), file.filename or "cv.txt"), file.filename
        except ParseError as e:
            raise HTTPException(422, str(e)) from None
    return text or "", None


@portal.post("/login")
def login(body: LoginIn):
    try:
        return svc.login(body.email, body.password)
    except svc.PortalError as e:
        raise HTTPException(401, str(e)) from None


@portal.post("/signup")
async def signup(name: str = Form(...), email: str = Form(...), password: str = Form(...),
                 job_id: int | None = Form(None), text: str | None = Form(None), file: UploadFile | None = File(None)):
    cv, fname = await _cv_text(file, text)
    return _err(svc.signup, name, email, password, cv, job_id, fname)


@portal.get("/jobs/public")
def public_jobs():
    """Open jobs anyone can see before signing up."""
    from ..services import recruit
    return [{"id": j["id"], "title": j["title"], "location": j["location"], "min_years": j["min_years"]}
            for j in recruit.list_jobs(status="Open")]


@portal.get("/me")
def me(c=Depends(current_candidate)):
    return svc.profile(c["candidate_id"])


@portal.patch("/me")
def update_me(body: ProfileIn, c=Depends(current_candidate)):
    return svc.update_profile(c["candidate_id"], body.phone, body.location)


@portal.post("/me/cv")
async def new_cv(file: UploadFile | None = File(None), text: str | None = Form(None), c=Depends(current_candidate)):
    cv, fname = await _cv_text(file, text)
    return _err(svc.replace_cv, c["candidate_id"], cv, fname)


@portal.get("/applications")
def applications(c=Depends(current_candidate)):
    return svc.applications(c["candidate_id"])


@portal.get("/jobs")
def jobs(c=Depends(current_candidate)):
    return svc.open_jobs(c["candidate_id"])


@portal.post("/apply")
def apply(body: ApplyIn, c=Depends(current_candidate)):
    return _err(svc.apply, c["candidate_id"], body.job_id)


@portal.get("/messages")
def messages(c=Depends(current_candidate)):
    return svc.messages(c["candidate_id"])


@portal.post("/messages/{eid}/read")
def read(eid: int, c=Depends(current_candidate)):
    _err(svc.mark_read, c["candidate_id"], eid)
    return {"ok": True}


@portal.post("/messages/{eid}/reply")
def reply(eid: int, body: ReplyIn, c=Depends(current_candidate)):
    return _err(svc.reply, c["candidate_id"], eid, body.body)


@portal.post("/interviews/{iid}/respond")
def respond(iid: int, body: RespondIn, c=Depends(current_candidate)):
    return _err(svc.respond_interview, c["candidate_id"], iid, body.response, body.note)
