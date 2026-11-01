"""bcrypt passwords + JWT tokens. Two kinds of sign-in: staff (recruiters) and candidates (portal).
A candidate token can never open a staff endpoint, and the other way round."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import db
from .config import JWT_HOURS, JWT_SECRET

bearer = HTTPBearer(auto_error=False)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), h.encode())
    except ValueError:
        return False


def make_token(user: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS)
    return jwt.encode({"sub": str(user["id"]), "role": user["role"], "kind": "staff", "exp": exp}, JWT_SECRET,
                      algorithm="HS256")


def make_candidate_token(cid: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=JWT_HOURS)
    return jwt.encode({"sub": str(cid), "kind": "cand", "exp": exp}, JWT_SECRET, algorithm="HS256")


def _decode(cred: HTTPAuthorizationCredentials | None) -> dict:
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first")
    try:
        return jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.") from None


def current_candidate(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Candidate portal sign-in. Returns {candidate_id, email, name}."""
    data = _decode(cred)
    if data.get("kind") != "cand":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This page is for candidates")
    a = db.one("SELECT a.candidate_id, a.email, c.name FROM candidate_accounts a JOIN candidates c ON c.id=a.candidate_id "
               "WHERE a.candidate_id=?", (int(data["sub"]),))
    if not a:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found")
    return a


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Staff sign-in (Admin / Recruiter / Interviewer). Candidate tokens are refused here."""
    data = _decode(cred)
    if data.get("kind") == "cand":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Candidates can't open the recruiter portal")
    u = db.one("SELECT id, email, name, role, active FROM users WHERE id=?", (int(data["sub"]),))
    if not u:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    if u.get("active") == 0:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is turned off. Ask an Admin.")
    u.pop("active", None)
    return u


def require(*roles: str):
    def dep(u: dict = Depends(current_user)) -> dict:
        if u["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Needs role: {' or '.join(roles)}")
        return u
    return dep


RECRUITERS = ("Admin", "Recruiter")
