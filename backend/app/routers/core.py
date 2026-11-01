"""Auth, jobs, candidates, applications and matching endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import db
from ..core.parsing import ParseError, read_file
from ..security import RECRUITERS, check_pw, current_user, make_token, require
from ..services import recruit

auth = APIRouter(prefix="/auth", tags=["auth"])
jobs = APIRouter(prefix="/jobs", tags=["jobs"])
cands = APIRouter(prefix="/candidates", tags=["candidates"])
apps = APIRouter(prefix="/applications", tags=["applications"])
match = APIRouter(prefix="/match", tags=["match"])

rec = require(*RECRUITERS)


# ------------------------------------------------------------- auth
class Login(BaseModel):
    email: str
    password: str


@auth.post("/login")
def login(body: Login):
    u = db.one("SELECT * FROM users WHERE lower(email)=lower(?)", (body.email.strip(),))
    if not u or not check_pw(body.password, u["password_hash"]):
        db.log("Sign-in failed", f"Wrong email or password for {body.email.strip()[:60]}", "Unknown", entity="auth")
        raise HTTPException(401, "Wrong email or password")
    if u.get("active") == 0:
        raise HTTPException(401, "This account is turned off. Ask an Admin.")
    db.run("UPDATE users SET last_login=? WHERE id=?", (db.now(), u["id"]))
    db.log("Signed in", f"{u['role']} signed in", u["name"], entity="auth", entity_id=u["id"])
    return {"token": make_token(u), "user": {k: u[k] for k in ("id", "email", "name", "role")}}


@auth.get("/me")
def me(u: dict = Depends(current_user)):
    return u


# ------------------------------------------------------------- jobs
class JobText(BaseModel):
    text: str = Field(min_length=20)
    title: str | None = None


class JobUpdate(BaseModel):
    title: str | None = None
    location: str | None = None
    min_years: float | None = None
    qualification: str | None = None
    status: str | None = None
    description: str | None = None
    must: list[str] | None = None
    nice: list[str] | None = None


async def _read(f: UploadFile) -> str:
    try:
        return read_file(await f.read(), f.filename or "file.txt")
    except ParseError as e:
        raise HTTPException(422, str(e)) from None


@jobs.get("")
def list_jobs(status: str | None = None, q: str | None = None, u=Depends(current_user)):
    return recruit.list_jobs(status, q)


@jobs.post("")
def create_job(body: JobText, u=Depends(rec)):
    try:
        return recruit.create_job(body.text, u["name"], source="Pasted", title=body.title)
    except ParseError as e:
        raise HTTPException(422, str(e)) from None


@jobs.post("/upload")
async def upload_job(file: UploadFile = File(...), u=Depends(rec)):
    text = await _read(file)
    try:
        return recruit.create_job(text, u["name"], source="Upload", file_name=file.filename)
    except ParseError as e:
        raise HTTPException(422, str(e)) from None


@jobs.post("/preview")
async def preview_job(file: UploadFile | None = File(None), text: str | None = Form(None), u=Depends(rec)):
    from ..core.jdcheck import jd_check
    from ..core.parsing import parse_jd
    t = await _read(file) if file else (text or "")
    try:
        p = parse_jd(t)
    except ParseError as e:
        raise HTTPException(422, str(e)) from None
    return {**p, "check": jd_check(p["description"], p["must"], p["location"])}


@jobs.get("/{job_id}")
def get_job(job_id: int, u=Depends(current_user)):
    return recruit.get_job(job_id)


@jobs.patch("/{job_id}")
def update_job(job_id: int, body: JobUpdate, u=Depends(rec)):
    j = recruit.update_job(job_id, u["name"], **body.model_dump())
    recruit.compute_job(job_id)
    return j


@jobs.delete("/{job_id}")
def delete_job(job_id: int, u=Depends(rec)):
    recruit.delete_job(job_id, u["name"])
    return {"ok": True}


@jobs.get("/{job_id}/check")
def check_job(job_id: int, u=Depends(current_user)):
    return recruit.job_check(job_id)


# ------------------------------------------------------------- candidates
class CandText(BaseModel):
    text: str = Field(min_length=20)
    job_id: int | None = None
    allow_duplicate: bool = False


@cands.get("")
def list_candidates(q: str | None = None, skill: str | None = None, city: str | None = None, job_id: int | None = None,
                    stage: str | None = None, min_years: float | None = None, edu_level: str | None = None,
                    u=Depends(current_user)):
    return recruit.list_candidates(q, skill, city, job_id, stage, min_years, edu_level)


@cands.post("")
def create_candidate(body: CandText, u=Depends(rec)):
    try:
        return recruit.create_candidate(body.text, u["name"], source="Pasted", job_id=body.job_id,
                                        allow_duplicate=body.allow_duplicate)
    except (ValueError, ParseError) as e:
        raise HTTPException(409 if "duplicate" in str(e).lower() else 422, str(e)) from None


@cands.post("/preview")
async def preview_cvs(files: list[UploadFile] = File(...), u=Depends(rec)):
    """Read several CVs and show what was found before saving (with duplicate check)."""
    out = []
    for f in files:
        try:
            text = read_file(await f.read(), f.filename or "cv.txt")
            p = recruit.preview_cv(text)
            out.append({"file_name": f.filename, "ok": True, **p})
        except ParseError as e:
            out.append({"file_name": f.filename, "ok": False, "error": str(e)})
    return out


@cands.post("/upload")
async def upload_cvs(files: list[UploadFile] = File(...), job_id: int | None = Form(None),
                     allow_duplicate: bool = Form(False), source: str | None = Form(None),
                     referred_by: str | None = Form(None), u=Depends(rec)):
    out = []
    for f in files:
        try:
            text = read_file(await f.read(), f.filename or "cv.txt")
            c = recruit.create_candidate(text, u["name"], source="Upload", file_name=f.filename, job_id=job_id,
                                         allow_duplicate=allow_duplicate)
            if job_id and source:
                a = recruit.app_for(job_id, c["id"])
                if a:
                    db.run("UPDATE applications SET source=?, referred_by=? WHERE id=?",
                           (source, referred_by if source == "Referral" else None, a["id"]))
            out.append({"file_name": f.filename, "ok": True, "candidate": c})
        except (ValueError, ParseError) as e:
            out.append({"file_name": f.filename, "ok": False, "error": str(e)})
    return out


@cands.get("/{cid}")
def get_candidate(cid: int, u=Depends(current_user)):
    return recruit.get_candidate(cid)


@cands.delete("/{cid}")
def delete_candidate(cid: int, u=Depends(rec)):
    recruit.delete_candidate(cid, u["name"])
    return {"ok": True}


@cands.get("/{cid}/similar")
def similar(cid: int, u=Depends(current_user)):
    return recruit.similar_candidates(cid)


@cands.get("/{cid}/activity")
def activity(cid: int, u=Depends(current_user)):
    return db.rows("SELECT l.*, j.title job_title FROM activity_logs l LEFT JOIN jobs j ON j.id=l.job_id "
                   "WHERE l.candidate_id=? ORDER BY l.id DESC", (cid,))


class NoteIn(BaseModel):
    text: str = Field(min_length=1)
    job_id: int | None = None


@cands.get("/{cid}/notes")
def notes(cid: int, u=Depends(current_user)):
    return db.rows("SELECT * FROM notes WHERE candidate_id=? ORDER BY id DESC", (cid,))


@cands.post("/{cid}/notes")
def add_note(cid: int, body: NoteIn, u=Depends(current_user)):
    recruit.get_candidate(cid)
    nid = db.run("INSERT INTO notes(candidate_id,job_id,text,by_name,created_at) VALUES(?,?,?,?,?)",
                 (cid, body.job_id, body.text, u["name"], db.now()))
    db.log("Note added", body.text[:80], u["name"], candidate_id=cid, job_id=body.job_id)
    return db.one("SELECT * FROM notes WHERE id=?", (nid,))


# ------------------------------------------------------------- applications
class ApplyIn(BaseModel):
    job_id: int
    candidate_id: int
    source: str | None = None
    referred_by: str | None = None


class StageIn(BaseModel):
    stage: str


class BulkIn(BaseModel):
    application_ids: list[int]
    stage: str


@apps.post("")
def apply(body: ApplyIn, u=Depends(rec)):
    return recruit.apply(body.job_id, body.candidate_id, u["name"], source=body.source, referred_by=body.referred_by)


@apps.patch("/{app_id}")
def set_stage(app_id: int, body: StageIn, u=Depends(rec)):
    try:
        return recruit.set_stage(app_id, body.stage, u["name"])
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@apps.post("/bulk")
def bulk(body: BulkIn, u=Depends(rec)):
    return [recruit.set_stage(a, body.stage, u["name"]) for a in body.application_ids]


@apps.delete("/{app_id}")
def remove(app_id: int, u=Depends(rec)):
    recruit.remove_app(app_id, u["name"])
    return {"ok": True}


# ------------------------------------------------------------- matching
@match.get("/job/{job_id}")
def ranked(job_id: int, scope: str = "pool", u=Depends(current_user)):
    if scope not in ("pool", "all", "suggested"):
        raise HTTPException(422, "scope must be pool, all or suggested")
    return recruit.compute_job(job_id, scope)


@match.get("/job/{job_id}/candidate/{cid}")
def one(job_id: int, cid: int, u=Depends(current_user)):
    return recruit.match_one(job_id, cid)


@match.get("/compare")
def compare(job_id: int, ids: str, u=Depends(current_user)):
    return recruit.compare(job_id, [int(x) for x in ids.split(",") if x.strip()])
