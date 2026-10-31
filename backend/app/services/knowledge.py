"""Knowledge store: one place for JDs, CVs, policies and FAQs + grounded search (RAG)."""
from __future__ import annotations

from .. import db
from ..adapters import llm
from ..adapters.vectorstore import get_store
from ..core.nlp import bm25_search
from . import recruit

DOC_TYPES = ["Policy", "FAQ", "Other"]


def _index(did: int) -> None:
    d = get_doc(did)
    get_store().upsert(f"doc:{did}", f"{d['title']}\n{d['text']}", {"type": d["type"], "title": d["title"], "ref_id": did})


def get_doc(did: int) -> dict:
    d = db.one("SELECT * FROM knowledge_docs WHERE id=?", (did,))
    if not d:
        raise recruit.NotFound("Document not found")
    return d


def find_doc(text: str) -> dict | None:
    t = text.lower()
    best = None
    for d in db.rows("SELECT * FROM knowledge_docs"):
        title = d["title"].lower()
        core = title.replace("faq:", "").strip()
        if title in t or (core and core in t):
            if not best or len(d["title"]) > len(best["title"]):
                best = d
    return best


def create_doc(title: str, text: str, dtype: str, by: str, file_name: str | None = None, source: str = "Created") -> dict:
    if not title.strip() or not text.strip():
        raise ValueError("Title and text are required.")
    dtype = dtype if dtype in DOC_TYPES else "Other"
    did = db.run("INSERT INTO knowledge_docs(title,type,text,source,file_name,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                 (title.strip(), dtype, text.strip(), source, file_name, db.now(), db.now()))
    _index(did)
    db.log("Document added", title, by, entity="doc", entity_id=did)
    return get_doc(did)


def update_doc(did: int, by: str, title: str | None = None, text: str | None = None, dtype: str | None = None) -> dict:
    get_doc(did)
    db.run("UPDATE knowledge_docs SET title=COALESCE(?,title), text=COALESCE(?,text), type=COALESCE(?,type), "
           "updated_at=? WHERE id=?", (title, text, dtype, db.now(), did))
    _index(did)
    db.log("Document edited", title or "", by, entity="doc", entity_id=did)
    return get_doc(did)


def delete_doc(did: int, by: str) -> None:
    d = get_doc(did)
    db.run("DELETE FROM knowledge_docs WHERE id=?", (did,))
    get_store().delete(f"doc:{did}")
    db.log("Document deleted", d["title"], by)


def all_docs(kind: str | None = None, q: str | None = None) -> list[dict]:
    """Unified list across JDs, CVs and policy docs."""
    out = []
    for j in db.rows("SELECT id, title, location, description, source, file_name, created_at FROM jobs"):
        out.append({"key": f"job:{j['id']}", "kind": "JD", "id": j["id"], "title": j["title"],
                    "subtitle": j["location"], "text": j["description"], "source": j["source"],
                    "file_name": j["file_name"], "created_at": j["created_at"]})
    for c in db.rows("SELECT id, name, headline, cv_text, source, file_name, created_at FROM candidates"):
        out.append({"key": f"cand:{c['id']}", "kind": "CV", "id": c["id"], "title": c["name"], "subtitle": c["headline"],
                    "text": c["cv_text"], "source": c["source"], "file_name": c["file_name"], "created_at": c["created_at"]})
    for d in db.rows("SELECT * FROM knowledge_docs"):
        out.append({"key": f"doc:{d['id']}", "kind": d["type"], "id": d["id"], "title": d["title"], "subtitle": "",
                    "text": d["text"], "source": d["source"], "file_name": d["file_name"], "created_at": d["created_at"]})
    if kind:
        out = [d for d in out if d["kind"] == kind]
    if q:
        ql = q.lower()
        out = [d for d in out if ql in (d["title"] + " " + d["text"]).lower()]
    return sorted(out, key=lambda d: d["created_at"] or "", reverse=True)


def _chunks() -> list[dict]:
    from ..adapters.vectorstore import chunk_text
    out = []
    for d in all_docs():
        for i, c in enumerate(chunk_text(d["text"])):
            out.append({"id": f"{d['key']}#{i}", "text": c, "meta": {"title": d["title"], "type": d["kind"],
                                                                      "doc_key": d["key"]}})
    return out


def retrieve(query: str, k: int = 5, policy_only: bool = False) -> list[dict]:
    """Hybrid retrieval: BM25 (keywords) + vector search, merged with reciprocal-rank fusion."""
    chunks = _chunks()
    if policy_only:
        chunks = [c for c in chunks if c["meta"]["type"] in ("Policy", "FAQ", "Other")]
    kw = bm25_search(chunks, query, k=10)
    try:
        vec = get_store().search(query, k=10)
        if policy_only:
            vec = [v for v in vec if v["meta"].get("type") in ("Policy", "FAQ", "Other")]
    except Exception:  # noqa: BLE001
        vec = []
    fused: dict[str, dict] = {}
    for rank, r in enumerate(kw):
        fused.setdefault(r["id"], {**r, "rrf": 0, "bm25": r["score"]})["rrf"] += 1 / (60 + rank)
    for rank, r in enumerate(vec):
        e = fused.setdefault(r["id"], {**r, "rrf": 0, "bm25": 0})
        e["rrf"] += 1 / (60 + rank)
        e["vec"] = r["score"]
    res = sorted(fused.values(), key=lambda x: -x["rrf"])
    # grounding gate: need some keyword overlap
    return [r for r in res if r.get("bm25", 0) > 0.5][:k]


def answer(question: str) -> dict:
    hits = retrieve(question, k=3)
    if not hits:
        return {"text": "That is not in the data I have. Try asking about the hiring process, shifts, assessments, "
                        "joining documents, or a specific job or candidate.", "sources": [], "grounded": False, "ai": False}
    ctx = "\n\n".join(f"[{i + 1}] {h['meta']['title']}: {h['text']}" for i, h in enumerate(hits))
    out = llm.generate(
        "Answer the recruiter's question using ONLY the sources below. Cite sources like [1]. If the sources do not "
        "answer it, say 'That is not in the data.' Keep it under 90 words, in simple points.\n\n"
        f"SOURCES:\n{ctx}\n\nQUESTION: {question}")
    if not out:
        top = hits[0]
        body = top['text'].split(chr(10), 1)[-1] if top['text'].startswith(top['meta']['title']) else top['text']
        if top["meta"]["type"] in ("CV", "JD"):
            # no AI: don't pretend a CV/JD snippet is an answer
            return {"text": f"The closest match is in {top['meta']['title']}'s "
                            f"{'CV' if top['meta']['type'] == 'CV' else 'job description'}:\n> "
                            + body.replace(chr(10), ' ')[:300] + "\n\nTurn on the free AI key (Settings → AI model) "
                            "to get a full answer to open questions like this.",
                    "sources": [{"n": 1, "title": top["meta"]["title"], "type": top["meta"]["type"],
                                 "key": top["meta"]["doc_key"]}], "grounded": True, "ai": False}
        out = f"{body} [1]"
        if len(hits) > 1 and hits[1]["bm25"] > hits[0]["bm25"] * 0.75:
            out += f"\n\nAlso relevant: {hits[1]['text'].split(chr(10), 1)[-1]} [2]"
    seen, sources = set(), []
    for i, h in enumerate(hits):
        if h["meta"]["title"] not in seen:
            seen.add(h["meta"]["title"])
            sources.append({"n": i + 1, "title": h["meta"]["title"], "type": h["meta"]["type"], "key": h["meta"]["doc_key"]})
    return {"text": out, "sources": sources, "grounded": True, "ai": llm.get_llm() is not None}
