"""Classic ML (scikit-learn): Naive Bayes, Logistic Regression, KNN, K-Means + PCA.

These support the recruiter; they never decide. Data here is small and synthetic, so treat
the outputs as a method demo.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import NearestNeighbors

from .nlp import tok

NB_TRAIN = [
    ("Store management", "store manager assistant store manager store operations opening closing roster team sales targets shrinkage area manager"),
    ("Store management", "department manager floor supervisor visual merchandising footfall nps store team festive operations"),
    ("Store management", "led store team inventory audits sales reports excel mis store budget"),
    ("Store management", "department manager hypermarket supervised associates team leads stock audits sales targets"),
    ("Cashier & customer service", "cashier billing counter pos billing cash tally upi card payments"),
    ("Cashier & customer service", "customer queries exchanges returns checkout counter cash handling"),
    ("Cashier & customer service", "billed customers payments day-end cash accuracy counter"),
    ("Warehouse & logistics", "warehouse picking packing dispatch inbound grn wms"),
    ("Warehouse & logistics", "logistics delivery dark store forklift safety pickers packers"),
    ("Warehouse & logistics", "dispatch numbers warehouse operations shipments stock movement"),
]
# Example past shortlist decisions: [skill 0-1, text 0-1, meets years 0/1] -> shortlisted
LR_HISTORY = [[.9, .35, 1, 1], [.85, .3, 1, 1], [.8, .25, 1, 1], [.75, .3, 1, 1], [.7, .2, 1, 1], [.6, .3, 1, 1],
              [.8, .18, 0, 1], [.65, .28, 0, 0], [.55, .18, 1, 0], [.5, .25, 0, 0], [.45, .2, 1, 0], [.4, .15, 0, 0],
              [.35, .22, 1, 0], [.3, .1, 0, 0], [.7, .15, 0, 0], [.25, .12, 1, 0]]


@lru_cache(maxsize=1)
def _nb():
    vec = CountVectorizer(tokenizer=tok, lowercase=False, token_pattern=None)
    X = vec.fit_transform([t for _, t in NB_TRAIN])
    m = MultinomialNB(alpha=1.0).fit(X, [c for c, _ in NB_TRAIN])
    return vec, m


def job_family(text: str) -> list[tuple[str, float]]:
    vec, m = _nb()
    p = m.predict_proba(vec.transform([text]))[0]
    return sorted(zip(map(str, m.classes_), map(float, p)), key=lambda x: -x[1])


@lru_cache(maxsize=1)
def _lr():
    X = np.array([r[:3] for r in LR_HISTORY])
    y = np.array([r[3] for r in LR_HISTORY])
    m = LogisticRegression(C=10.0).fit(X, y)  # mild L2 regularisation
    return m, float(m.score(X, y))


def shortlist_chance(skill: float, text: float, meets: bool) -> float:
    m, _ = _lr()
    return float(m.predict_proba([[skill, text, 1.0 if meets else 0.0]])[0][1])


def lr_accuracy() -> float:
    return _lr()[1]


def _tfidf(texts: list[str]):
    vec = TfidfVectorizer(tokenizer=tok, lowercase=False, sublinear_tf=True, token_pattern=None)
    return vec, vec.fit_transform(texts)


def similar(cands: list[dict], cid: int, k: int = 3) -> list[tuple[int, float]]:
    """KNN on TF-IDF of CV text."""
    if len(cands) < 2:
        return []
    _, X = _tfidf([c["cv_text"] for c in cands])
    nn = NearestNeighbors(n_neighbors=min(k + 1, len(cands)), metric="cosine").fit(X)
    idx = next(i for i, c in enumerate(cands) if c["id"] == cid)
    d, ix = nn.kneighbors(X[idx])
    return [(cands[j]["id"], round(1 - float(dd), 3)) for dd, j in zip(d[0], ix[0]) if j != idx][:k]


def clusters(cands: list[dict], k: int = 3) -> dict:
    """K-Means talent groups + PCA 2D map."""
    if len(cands) < 3:
        return {"groups": [], "points": []}
    k = min(k, len(cands) - 1)
    vec, X = _tfidf([c["cv_text"] for c in cands])
    km = KMeans(n_clusters=k, n_init=10, random_state=7).fit(X)
    terms = np.array(vec.get_feature_names_out())
    groups = []
    for g in range(k):
        top = terms[np.argsort(-km.cluster_centers_[g])[:4]].tolist()
        groups.append({"group": g + 1, "top_terms": top,
                       "members": [c["id"] for c, lab in zip(cands, km.labels_) if lab == g]})
    xy = PCA(n_components=2, random_state=7).fit_transform(X.toarray())
    points = [{"id": c["id"], "name": c["name"], "x": round(float(a), 3), "y": round(float(b), 3),
               "group": int(lab) + 1} for c, (a, b), lab in zip(cands, xy, km.labels_)]
    return {"groups": groups, "points": points}
