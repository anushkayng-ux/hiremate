"""Tokeniser, TF-IDF similarity and BM25 search."""
from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

STOP = set("a an and the of to in on for with at by from as is are be was were or this that it its we our you your "
           "their i my me per across into over including sq ft present day".split())


def tok(t: str) -> list[str]:
    t = (t or "").lower().replace("p&l", "pnl")
    t = re.sub(r"[^a-z ]+", " ", t)
    out = []
    for w in t.split():
        if len(w) < 2 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def tfidf_matrix(texts: list[str]):
    vec = TfidfVectorizer(tokenizer=tok, lowercase=False, sublinear_tf=True, token_pattern=None)
    return vec, vec.fit_transform(texts)


def tfidf_similarity(query: str, docs: list[str], corpus: list[str] | None = None) -> np.ndarray:
    """Cosine similarity of query vs each doc, IDF learned from the whole corpus."""
    corpus = corpus or [query, *docs]
    vec = TfidfVectorizer(tokenizer=tok, lowercase=False, sublinear_tf=True, token_pattern=None).fit(corpus)
    q = vec.transform([query])
    d = vec.transform(docs)
    return (d @ q.T).toarray().ravel()


def bm25_search(chunks: list[dict], query: str, k: int = 5) -> list[dict]:
    if not chunks:
        return []
    # light "prefix stemming" so reschedule / rescheduling / rescheduled match
    def stem(ws):
        return [w[:6] for w in ws]
    corpus = [stem(tok(c["text"])) or ["_"] for c in chunks]
    bm = BM25Okapi(corpus, k1=1.4, b=0.75)
    q = list(dict.fromkeys(stem(tok(query))))
    if not q:
        return []
    scores = bm.get_scores(q)
    order = np.argsort(-scores)
    return [{**chunks[i], "score": float(scores[i])} for i in order[:k] if scores[i] > 0]
