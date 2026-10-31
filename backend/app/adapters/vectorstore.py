"""VectorStore port: ChromaDB adapter + in-memory fallback.

Every JD, CV and knowledge doc is chunked and indexed here. SQLite stays the source of truth;
this index can always be rebuilt with `rebuild_index()`.
"""
from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

from ..config import CHROMA_DIR, VECTOR_STORE
from .embedder import get_embedder

log = logging.getLogger(__name__)


def chunk_text(text: str, size: int = 450, overlap: int = 80) -> list[str]:
    """Split on lines, pack into ~size-character chunks with a little overlap."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    chunks, cur = [], ""
    for l in lines:
        if len(cur) + len(l) + 1 > size and cur:
            chunks.append(cur)
            cur = cur[-overlap:] + " " + l if overlap else l
        else:
            cur = (cur + "\n" + l) if cur else l
    if cur:
        chunks.append(cur)
    return chunks or ([text] if text else [])


class VectorStore(Protocol):
    name: str

    def upsert(self, doc_key: str, text: str, meta: dict) -> None: ...
    def delete(self, doc_key: str) -> None: ...
    def search(self, query: str, k: int = 5, where: dict | None = None) -> list[dict]: ...
    def clear(self) -> None: ...


class MemoryStore:
    name = "in-memory"

    def __init__(self) -> None:
        self.items: dict[str, tuple[np.ndarray, str, dict]] = {}

    def upsert(self, doc_key, text, meta):
        self.delete(doc_key)
        chunks = chunk_text(text)
        vecs = get_embedder().embed(chunks)
        for i, (c, v) in enumerate(zip(chunks, vecs)):
            self.items[f"{doc_key}#{i}"] = (v, c, {**meta, "doc_key": doc_key})

    def delete(self, doc_key):
        for k in [k for k in self.items if k.split("#")[0] == doc_key]:
            del self.items[k]

    def search(self, query, k=5, where=None):
        if not self.items:
            return []
        q = get_embedder().embed([query], query=True)[0]
        out = []
        for key, (v, text, meta) in self.items.items():
            if where and any(meta.get(a) != b for a, b in where.items()):
                continue
            out.append({"id": key, "text": text, "meta": meta, "score": float(np.dot(q, v))})
        return sorted(out, key=lambda x: -x["score"])[:k]

    def clear(self):
        self.items.clear()


class ChromaStore:
    name = "chromadb"

    def __init__(self) -> None:
        import chromadb
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self.col = self.client.get_or_create_collection("hiremate", metadata={"hnsw:space": "cosine"},
                                                        embedding_function=None)

    def upsert(self, doc_key, text, meta):
        self.delete(doc_key)
        chunks = chunk_text(text)
        if not chunks:
            return
        vecs = get_embedder().embed(chunks)
        self.col.add(ids=[f"{doc_key}#{i}" for i in range(len(chunks))], documents=chunks,
                     embeddings=[v.tolist() for v in vecs],
                     metadatas=[{**{k: v for k, v in meta.items() if v is not None}, "doc_key": doc_key}] * len(chunks))

    def delete(self, doc_key):
        self.col.delete(where={"doc_key": doc_key})

    def search(self, query, k=5, where=None):
        if self.col.count() == 0:
            return []
        q = get_embedder().embed([query], query=True)[0]
        res = self.col.query(query_embeddings=[q.tolist()], n_results=min(k, self.col.count()),
                             where=where or None)
        out = []
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            out.append({"id": i, "text": d, "meta": m, "score": 1 - float(dist)})
        return out

    def clear(self):
        self.client.delete_collection("hiremate")
        self.col = self.client.get_or_create_collection("hiremate", metadata={"hnsw:space": "cosine"},
                                                        embedding_function=None)


_inst: VectorStore | None = None


def get_store() -> VectorStore:
    global _inst
    if _inst is None:
        if VECTOR_STORE in ("auto", "chroma"):
            try:
                _inst = ChromaStore()
            except Exception as e:  # noqa: BLE001
                if VECTOR_STORE == "chroma":
                    raise
                log.warning("ChromaDB not available (%s); using in-memory store", e)
        if _inst is None:
            _inst = MemoryStore()
    return _inst
