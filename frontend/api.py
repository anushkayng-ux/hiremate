"""Thin client for the FastAPI backend. The frontend never touches the database or AI keys."""
from __future__ import annotations

import os

import requests
import streamlit as st

# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and waits ~2 s per request.
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/").replace("//localhost", "//127.0.0.1")


@st.cache_resource
def _session() -> requests.Session:
    """One kept-alive connection pool for all calls (no new TCP connection per request)."""
    s = requests.Session()
    a = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=32)
    s.mount("http://", a)
    s.trust_env = False  # skip proxy lookups for the local API
    return s


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _headers() -> dict:
    tok = st.session_state.get("token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


import time as _time

STATS = {"n": 0, "ms": 0.0, "calls": []}


def _call(method: str, path: str, **kw):
    t0 = _time.perf_counter()
    try:
        return _call_inner(method, path, **kw)
    finally:
        d = (_time.perf_counter() - t0) * 1000
        STATS["n"] += 1
        STATS["ms"] += d
        STATS["calls"].append(f"{method} {path} {d:.0f}ms")


def _call_inner(method: str, path: str, **kw):
    try:
        r = _session().request(method, API_URL + path, headers=_headers(), timeout=120, **kw)
    except requests.ConnectionError:
        raise ApiError(0, "Can't reach the HireMate server. Is the backend running?") from None
    if r.status_code == 401 and st.session_state.get("token"):
        st.session_state.clear()
        st.rerun()
    if r.status_code >= 400:
        try:
            d = r.json().get("detail", r.text)
        except ValueError:
            d = r.text
        if isinstance(d, list):
            d = "; ".join(x.get("msg", str(x)) for x in d)
        raise ApiError(r.status_code, str(d))
    ct = r.headers.get("content-type", "")
    return r.json() if "json" in ct else r.content


_NO_CACHE = ("/ai/", "/assistant", "/settings/logs", "/knowledge/files", "/export")
_TTL = 12.0   # seconds. Every click re-runs the page, so repeat reads are served from memory.


def get(path, **params):
    q = {k: v for k, v in params.items() if v not in (None, "")}
    if any(x in path for x in _NO_CACHE):
        return _call("GET", path, params=q)
    cache = st.session_state.setdefault("_gc", {})
    key = (path, tuple(sorted(q.items())))
    hit = cache.get(key)
    now = _time.monotonic()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    out = _call("GET", path, params=q)
    if len(cache) > 80:
        cache.clear()
    cache[key] = (now, out)
    return out


def _fresh():
    st.session_state.pop("_gc", None)   # any change makes cached reads stale


def post(path, json=None, data=None, files=None):
    _fresh()
    return _call("POST", path, json=json, data=data, files=files)


def patch(path, json=None, **params):
    _fresh()
    return _call("PATCH", path, json=json, params=params or None)


def put(path, json=None, **params):
    _fresh()
    return _call("PUT", path, json=json, params=params or None)


def delete(path):
    _fresh()
    return _call("DELETE", path)


def login(email: str, password: str) -> dict:
    r = _session().post(API_URL + "/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        raise ApiError(r.status_code, r.json().get("detail", "Sign-in failed"))
    return r.json()


def portal_login(email: str, password: str) -> dict:
    r = _session().post(API_URL + "/portal/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        raise ApiError(r.status_code, r.json().get("detail", "Sign-in failed"))
    return r.json()


def public_jobs() -> list[dict]:
    return _session().get(API_URL + "/portal/jobs/public", timeout=15).json()


def portal_signup(name: str, email: str, password: str, job_id: int | None, f, consent: bool = False,
                  source: str | None = None) -> dict:
    data = {"name": name, "email": email, "password": password, "consent": str(bool(consent)).lower()}
    if source:
        data["source"] = source
    if job_id:
        data["job_id"] = str(job_id)
    r = _session().post(API_URL + "/portal/signup", data=data, files={"file": (f.name, f.getvalue())}, timeout=120)
    if r.status_code != 200:
        raise ApiError(r.status_code, r.json().get("detail", "Sign-up failed"))
    return r.json()


def stream_chat(data, files=None):
    """Generator: yields ("delta", text) while the AI writes, then ("final", reply dict)."""
    import json as _json
    _fresh()
    try:
        r = _session().post(API_URL + "/assistant/chat/stream", headers=_headers(), data=data, files=files,
                            stream=True, timeout=120)
    except requests.ConnectionError:
        raise ApiError(0, "Can't reach the HireMate server. Is the backend running?") from None
    if r.status_code == 401 and st.session_state.get("token"):
        st.session_state.clear()
        st.rerun()
    if r.status_code >= 400:
        try:
            d = r.json().get("detail", r.text)
        except ValueError:
            d = r.text
        raise ApiError(r.status_code, str(d))

    event = ""
    try:   # Server-Sent Events: "event: x" then "data: {json}" then a blank line
        for line in r.iter_lines(chunk_size=1, decode_unicode=True):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                payload = _json.loads(line[5:].strip())
                if event == "delta":
                    yield "delta", payload
                elif event == "final":
                    yield "final", payload
                    return
                elif event == "error":
                    break
    except (requests.RequestException, ValueError):
        pass
    # the stream broke before a final answer: ask the normal way
    try:
        r2 = _session().post(API_URL + "/assistant/chat", headers=_headers(), data=data, files=files, timeout=120)
        r2.raise_for_status()
        yield "final", r2.json()
    except requests.RequestException:
        raise ApiError(0, "The AI could not answer just now. Please try again.") from None
