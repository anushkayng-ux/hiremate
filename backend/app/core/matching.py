"""Match score = Skills + Text match + Experience. Computed in code, fully explainable."""
from __future__ import annotations

import re

import numpy as np

from . import ml
from .nlp import tfidf_similarity
from .parsing import cv_sentences
from .skills import find_proof

DEFAULT_WEIGHTS = {"skills": 50, "text": 30, "exp": 20}


def _skill_line(cv_text: str) -> str:
    return next((l.strip() for l in cv_text.splitlines()
                 if re.match(r"^\s*(skills|key skills|technical skills|core skills)\s*:", l, re.I)), "")


def skill_rows(job: dict, cv_text: str, name: str = "") -> list[dict]:
    sl = _skill_line(cv_text)
    sents = cv_sentences(cv_text, name, sl)
    out = []
    for skills, must in ((job["must"], True), (job["nice"], False)):
        for s in skills:
            p = find_proof(s, sents, sl)
            status = p[0] if p else "Missing"
            out.append({"skill": s, "must": must, "status": status, "evidence": p[1] if p else "",
                        "credit": {"Proven": 1.0, "Listed": 0.5}.get(status, 0.0), "weight": 2 if must else 1})
    return out


def text_similarities(job_text: str, cv_texts: list[str], corpus: list[str], embedder=None) -> np.ndarray:
    """Semantic text match. bge if available (rescaled), else TF-IDF cosine over the whole corpus."""
    if embedder is not None and getattr(embedder, "dim", 0) != 4096:  # bge-style dense model
        q = embedder.embed([job_text], query=True)[0]
        d = embedder.embed(cv_texts)
        cos = d @ q
        return np.clip((cos - 0.55) / 0.35, 0, 1)
    return np.clip(tfidf_similarity(job_text, cv_texts, corpus), 0, 1)


def score(job: dict, cand: dict, text_sim: float, weights: dict | None = None) -> dict:
    w = weights or DEFAULT_WEIGHTS
    rows = skill_rows(job, cand["cv_text"], cand.get("name", ""))
    tot = sum(r["weight"] for r in rows)
    got = sum(r["weight"] * r["credit"] for r in rows)
    skill = round(got / tot * 100) if tot else 0
    text = round(float(text_sim) * 100)
    minimum = float(job.get("min_years") or 0)
    years = float(cand.get("years") or 0)
    exp = min(100, round(years / minimum * 100)) if minimum else 100
    meets = years >= minimum
    ws = (w["skills"] + w["text"] + w["exp"]) or 1
    total = round((w["skills"] * skill + w["text"] * text + w["exp"] * exp) / ws)

    tips = []
    for r in rows:
        if r["must"] and r["status"] == "Missing":
            tips.append(f"Proof of {r['skill']} (must-have) would add the most.")
        elif r["must"] and r["status"] == "Listed":
            tips.append(f"{r['skill']} is only listed. A work example would count it fully.")
    if not meets:
        tips.append(f"Has {years:g} years; the job asks for {minimum:g}+.")
    return {
        "score": total, "skill_score": skill, "text_score": text, "exp_score": exp, "meets_years": meets,
        "years": years, "min_years": minimum, "rows": rows,
        "matched": [r["skill"] for r in rows if r["status"] != "Missing"],
        "missing_must": [r["skill"] for r in rows if r["must"] and r["status"] == "Missing"],
        "shortlist_chance": round(ml.shortlist_chance(skill / 100, text / 100, meets), 2),
        "tips": tips[:4], "weights": w,
    }
