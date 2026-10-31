"""Skill dictionary with synonyms (NLP: rules + normalisation) and proof finding."""
from __future__ import annotations

import re
from functools import lru_cache

SKILLS: dict[str, list[str]] = {
    "Store operations": ["store operations", "day-to-day store operations", "daily store operations",
                         "opening and closing", "opened and closed"],
    "Team management": ["team management", "led a team", "supervised", "team leads", "roster", "people management"],
    "Inventory control": ["inventory", r"stock audits?", r"cycle counts?", "shrinkage", "stock variance", "grn"],
    "Customer service": ["customer service", "customer queries", "customer escalations", "customer complaints",
                         "returns desk", "nps", "exchanges", "helped customers"],
    "POS systems": ["pos", "point of sale", "billing system", "billing counter", "pos billing"],
    "Excel reporting": ["excel", r"mis reports?", "google sheet", "spreadsheet"],
    "Visual merchandising": ["visual merchandising", r"window displays?", "planogram"],
    "P&L ownership": ["p&l", "profit and loss", "sales targets"],
    "Hindi": ["hindi"],
    "Cash handling": ["cash handling", "cash tally", "cash-up", "cash payments"],
    "UPI / card payments": ["upi", "card payments"],
    "Basic computer": ["ms office", "basic computer", "computer skills"],
    "Warehouse operations": ["warehouse", "picking", "packing", "dispatch"],
    "WMS software": ["wms"],
    "Safety compliance": ["safety"],
    "Forklift": ["forklift"],
}

_SPECIAL = set(".*+^${}()|[]\\")


def _esc(s: str) -> str:
    # keep the small regex bits used in the dictionary (s?), escape everything else
    if s.endswith("s?"):
        return re.escape(s[:-2]) + "s?"
    return re.escape(s)


@lru_cache(maxsize=512)
def skill_regex(name: str) -> re.Pattern:
    syns = SKILLS.get(name) or [name.lower()]
    return re.compile(r"(^|[^a-z0-9])(" + "|".join(_esc(s) for s in syns) + r")(?![a-z0-9])", re.I)


def skills_in(text: str) -> list[str]:
    return [k for k in SKILLS if skill_regex(k).search(text or "")]


def canon(phrase: str) -> str | None:
    """Map a free-text phrase to a canonical skill name. Unknown phrases become new skills."""
    p = (phrase or "").strip().rstrip(".").strip()
    if not p:
        return None
    for k in SKILLS:
        if skill_regex(k).search(p):
            return k
    if len(p) < 2 or len(p) > 40 or re.search(r"\d|\byears?\b|\byrs\b", p, re.I):
        return None
    return p[0].upper() + p[1:]


def find_proof(skill: str, sentences: list[str], skill_line: str) -> tuple[str, str] | None:
    """Return (status, evidence). Proven = a real CV sentence mentions it; Listed = only in the skills line."""
    rx = skill_regex(skill)
    for s in sentences:
        if rx.search(s):
            return "Proven", s
    if skill_line and rx.search(skill_line):
        return "Listed", re.sub(r"^[^:]*:\s*", "", skill_line)
    return None
