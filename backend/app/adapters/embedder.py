"""Embedder port with two adapters.

- BgeEmbedder: BAAI/bge-base-en-v1.5 via sentence-transformers (best quality, needs the model download).
- HashingEmbedder: scikit-learn hashing TF vectors (no download, works offline, always available).
"""
from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

from ..config import BGE_MODEL, EMBEDDER
from ..core.nlp import tok

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray: ...


class HashingEmbedder:
    name = "hashing-tf (offline fallback)"
    dim = 4096

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer
        self.v = HashingVectorizer(n_features=self.dim, tokenizer=tok, lowercase=False, token_pattern=None,
                                   ngram_range=(1, 2), alternate_sign=False, norm="l2")

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        return self.v.transform(texts).toarray().astype("float32")


class BgeEmbedder:
    dim = 768
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model: str = BGE_MODEL) -> None:
        from sentence_transformers import SentenceTransformer
        self.m = SentenceTransformer(model)
        self.name = model
        self.dim = self.m.get_sentence_embedding_dimension()

    def embed(self, texts: list[str], query: bool = False) -> np.ndarray:
        if query:
            texts = [self.QUERY_PREFIX + t for t in texts]
        return np.asarray(self.m.encode(texts, normalize_embeddings=True), dtype="float32")


_inst: Embedder | None = None


def get_embedder() -> Embedder:
    global _inst
    if _inst is None:
        if EMBEDDER in ("auto", "bge"):
            try:
                _inst = BgeEmbedder()
                log.info("Embedder: %s", _inst.name)
            except Exception as e:  # noqa: BLE001
                if EMBEDDER == "bge":
                    raise
                log.warning("bge not available (%s); using hashing embedder", e)
        if _inst is None:
            _inst = HashingEmbedder()
    return _inst
