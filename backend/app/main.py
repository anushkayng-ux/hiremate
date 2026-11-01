"""HireMate API. Run: uvicorn backend.app.main:app --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db
from .adapters import llm
from .adapters.embedder import get_embedder
from .adapters.vectorstore import get_store
from .routers import portal as rp
from .routers import assist as ra
from .routers import core as rc
from .routers import extras as rx
from .plus import ensure_schema as plus_schema
from .plus import router as rplus
from .seed import ensure_seeded
from .services import recruit

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("hiremate")


def rebuild_index() -> None:
    """SQLite is the source of truth; rebuild the vector index if the embedder changed or it's empty."""
    emb = get_embedder().name
    if db.get_setting("index_embedder") == emb and db.get_setting("index_store") == get_store().name and \
            get_store().name != "in-memory":
        return
    store = get_store()
    store.clear()
    for j in db.rows("SELECT id FROM jobs"):
        recruit.index_job(j["id"])
    for c in db.rows("SELECT id, name, cv_text FROM candidates"):
        store.upsert(f"cand:{c['id']}", c["cv_text"], {"type": "CV", "title": c["name"], "ref_id": c["id"]})
    for d in db.rows("SELECT * FROM knowledge_docs"):
        store.upsert(f"doc:{d['id']}", f"{d['title']}\n{d['text']}", {"type": d["type"], "title": d["title"],
                                                                        "ref_id": d["id"]})
    db.set_setting("index_embedder", emb)
    db.set_setting("index_store", store.name)
    log.info("Vector index rebuilt with %s on %s", emb, store.name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.conn()
    plus_schema()
    ensure_seeded()
    from .services import portal
    portal.ensure_all_accounts()  # older databases: give every candidate a portal account
    rebuild_index()
    log.info("LLM: %s", llm.status()["provider"])
    yield


app = FastAPI(title="HireMate API", version="1.0", lifespan=lifespan,
              description="AI recruiter assistant for an HR recruitment team. Synthetic data only.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (rc.auth, rc.jobs, rc.cands, rc.apps, rc.match, ra.ivs, ra.emails, ra.ai, ra.kb, ra.bot, ra.stats, ra.sets,
          ra.crit, ra.sm, rp.portal, rx.x, rx.px, rplus.plus, rplus.pplus):
    app.include_router(r)


@app.exception_handler(recruit.NotFound)
async def not_found(_: Request, e: recruit.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(e)})


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.status(), "embedder": get_embedder().name, "vector_store": get_store().name}
