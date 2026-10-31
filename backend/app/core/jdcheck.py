"""JD quality and fairness check: vague, biased or missing items."""
from __future__ import annotations

import re

FLAGS = [
    (r"\b(rock ?star|ninja|guru|superstar)\b", "Vague hype word", "Describe the actual work instead"),
    (r"\b(young|energetic|youthful|recent graduate)\b", "May exclude older applicants", "Remove age-related words"),
    (r"\b(male|female|girls?|boys?|gentlemen|ladies)\b(?! and)", "Gendered wording", "Use neutral words like 'candidate'"),
    (r"\b(native (hindi|english) speaker)\b", "Language requirement may exclude people", "Ask for the fluency level needed"),
    (r"\b(good looking|presentable|fair complexion|fair)\b", "Appearance-based wording", "Remove it"),
    (r"\b(age|aged)\s*(below|under|between|\d)", "Age limit", "Remove age limits unless legally required"),
]


def jd_check(description: str, must: list[str], location: str) -> list[dict]:
    out = []
    for rx, title, fix in FLAGS:
        m = re.search(rx, description, re.I)
        if m:
            out.append({"level": "bad", "title": f'{title}: "{m.group(0)}"', "fix": fix})
    if len(must) > 8:
        out.append({"level": "warn", "title": f"{len(must)} must-have skills", "fix": "Keep 4–8 so ranking stays meaningful"})
    if not must:
        out.append({"level": "warn", "title": "No must-have skills found", "fix": "Add a 'Must have:' line or add skills by hand"})
    if not re.search(r"\d+\s*\+?\s*(years|yrs)", description, re.I):
        out.append({"level": "warn", "title": "No experience level stated", "fix": "Add minimum years, e.g. '2+ years'"})
    if not location or location == "Not stated":
        out.append({"level": "warn", "title": "No location", "fix": "Add the store or city"})
    if not out:
        out.append({"level": "good", "title": "Clear and fair", "fix": "No vague, biased or missing items found"})
    return out
