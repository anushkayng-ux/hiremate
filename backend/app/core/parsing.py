"""Read files (PDF / DOCX / TXT) and parse JDs and CVs into structured data."""
from __future__ import annotations

import io
import re
from datetime import date

from .skills import SKILLS, canon, find_proof, skills_in

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
CITIES = ["Noida", "New Delhi", "Delhi", "Gurugram", "Gurgaon", "Ghaziabad", "Faridabad", "Mumbai", "Pune",
          "Bengaluru", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Jaipur", "Lucknow", "Chandigarh",
          "Ahmedabad", "Indore", "Rohtak", "Meerut", "Kanpur"]
BULLET = re.compile(r"^[-•*–▪●]\s*")
DATE_RANGE = re.compile(
    r"([A-Za-z]{3,9})\.?\s+(\d{4})\s*(?:–|—|-|to)\s*(present|current|now|till date|([A-Za-z]{3,9})\.?\s+(\d{4}))", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(\+?\d[\d\s-]{8,}\d)")


class ParseError(ValueError):
    pass


# ---------------------------------------------------------------- files
def read_file(data: bytes, filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext in ("txt", "md", "text", "csv"):
        return data.decode("utf-8", errors="ignore")
    if ext == "pdf":
        import pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Could not open the PDF ({e}).") from e
        if len(text.strip()) < 30:
            raise ParseError("This PDF has no readable text (it may be a scanned image). Paste the text instead.")
        return text
    if ext == "docx":
        import docx
        try:
            d = docx.Document(io.BytesIO(data))
        except Exception as e:  # noqa: BLE001
            raise ParseError(f"Could not open the Word file ({e}).") from e
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                parts.append(" | ".join(c.text for c in r.cells))
        return "\n".join(parts)
    raise ParseError(f"Unsupported file type '.{ext}'. Use PDF, DOCX or TXT.")


def find_city(text: str) -> str:
    for c in CITIES:
        if re.search(rf"\b{c}\b", text, re.I):
            return c
    return ""


def _lines(text: str) -> list[str]:
    return [l.strip() for l in (text or "").splitlines() if l.strip()]


def _after(line: str) -> str:
    return re.sub(r"^[^:]*:\s*", "", line)


# ---------------------------------------------------------------- classify
def classify(text: str) -> str:
    """Guess if text is a JD, a CV, or a policy/other doc."""
    t = text.lower()
    jd = sum(bool(re.search(p, t)) for p in [r"must[- ]have", r"responsibilit", r"qualification", r"nice[- ]to[- ]have",
                                              r"about the role", r"we are (hiring|looking)", r"job (title|description)"])
    cv = sum(bool(re.search(p, t)) for p in [r"\bskills\s*:", r"\beducation\s*:", r"\bsummary\s*:",
                                              r"\b(19|20)\d{2}\s*(–|—|-|to)\s*(present|current|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
                                              r"@", r"curriculum vitae|resume"])
    if jd >= 2 and jd >= cv:
        return "JD"
    if cv >= 2:
        return "CV"
    return "Policy"


# ---------------------------------------------------------------- JD
def parse_jd(text: str, title: str | None = None) -> dict:
    lines = _lines(text)
    if not lines:
        raise ParseError("The job description is empty.")

    def get(rx: str) -> str:
        return next((l for l in lines if re.search(rx, l, re.I)), "")

    ml = get(r"^(must[- ]haves?|requirements?|required skills|key skills|skills required|mandatory skills)\s*:")
    nl = get(r"^(nice[- ]to[- ]haves?|preferred( skills)?|good[- ]to[- ]have|desirable)\s*:")
    if ml:
        must = list(dict.fromkeys(filter(None, (canon(x) for x in re.split(r"[,;]", _after(ml))))))
        nice = list(dict.fromkeys(filter(None, (canon(x) for x in re.split(r"[,;]", _after(nl)))))) if nl else []
    else:
        must, nice = skills_in(text), []
    nice = [s for s in nice if s not in must]
    ym = re.search(r"(\d+)\s*\+?\s*(?:years|yrs)", text, re.I)
    t = (title or lines[0]).strip()
    t = re.sub(r"^(job title|role|position|title)\s*:\s*", "", t, flags=re.I)
    return {
        "title": t[:120],
        "location": _after(get(r"^location\s*:")) or find_city(text) or "Not stated",
        "must": must,
        "nice": nice,
        "min_years": float(ym.group(1)) if ym else 0.0,
        "qualification": _after(get(r"^(qualifications?|education)\s*:")),
        "description": text.strip(),
    }


# ---------------------------------------------------------------- CV
def _month(w: str | None) -> int | None:
    return MONTHS.get((w or "")[:3].lower())


def cv_sentences(text: str, name: str = "", skill_line: str = "") -> list[str]:
    out = []
    for l in _lines(text):
        if l == skill_line or l == name or EMAIL.search(l) or re.match(r"^(location|education)\s*:", l, re.I):
            continue
        l = BULLET.sub("", l)
        l = re.sub(r"^(summary|profile|objective|about( me)?)\s*:\s*", "", l, flags=re.I)
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", l):
            if len(s) > 12:
                out.append(s)
    return out


def parse_cv(text: str, today: date | None = None) -> dict:
    today = today or date.today()
    lines = _lines(text)
    if len(lines) < 2:
        raise ParseError("The CV looks empty or too short.")

    def is_contact(l: str) -> bool:
        return bool(EMAIL.search(l) or PHONE.search(l) or re.search(r"linkedin|https?:", l, re.I))

    name = next((l for l in lines if not is_contact(l) and len(l) < 50), "Unnamed")
    name = re.sub(r"^name\s*:\s*", "", name, flags=re.I).strip()
    if name == name.upper():
        name = name.title()

    def pick(rx: str) -> str:
        return _after(next((l for l in lines if re.search(rx, l, re.I)), ""))

    loc = pick(r"^(location|address|city)\s*:") or find_city(" ".join(lines[:8])) or "Not stated"
    summary = pick(r"^(summary|profile|objective|about( me)?)\s*:")
    edu = pick(r"^education\s*:") or next(
        (l for l in lines if re.search(r"\b(b\.?\s?com|bba|b\.?\s?tech|b\.?\s?sc|bca|mca|mba|diploma|class 12|12th|graduat)", l, re.I)),
        "Not stated")
    skill_line = next((l for l in lines if re.match(r"^(skills|key skills|technical skills|core skills)\s*:", l, re.I)), "")

    roles, cur, months = [], None, 0
    now_m = today.year * 12 + today.month - 1
    for l in lines:
        m = DATE_RANGE.search(l)
        if m and _month(m.group(1)) is not None:
            start = int(m.group(2)) * 12 + _month(m.group(1))
            if re.search(r"present|current|now|till", m.group(3), re.I):
                end = now_m
            elif m.group(5) and _month(m.group(4)) is not None:
                end = int(m.group(5)) * 12 + _month(m.group(4))
            else:
                end = start
            months += max(0, end - start + 1)
            rest = l.replace(m.group(0), "")
            parts = [re.sub(r"[,(–—-]+\s*$", "", x.strip()).strip() for x in re.split(r"\s*\|\s*|\s+at\s+", rest)]
            parts = [p for p in parts if p]
            cur = {"role": parts[0] if parts else "Role", "org": parts[1] if len(parts) > 1 else "",
                   "dates": m.group(0), "points": []}
            roles.append(cur)
            continue
        if BULLET.match(l) and cur is not None:
            cur["points"].append(BULLET.sub("", l))

    years = round(months / 12, 1)
    if not years:
        ym = re.search(r"(\d+(?:\.\d)?)\s*\+?\s*(?:years|yrs)", text, re.I)
        years = float(ym.group(1)) if ym else 0.0

    sentences = cv_sentences(text, name, skill_line)
    skills = {}
    for k in SKILLS:
        p = find_proof(k, sentences, skill_line)
        if p:
            skills[k] = {"status": p[0], "evidence": p[1]}
    # skills listed that aren't in the dictionary are kept as Listed
    if skill_line:
        for raw in re.split(r"[,;]", _after(skill_line)):
            c = canon(raw)
            if c and c not in skills:
                p = find_proof(c, sentences, skill_line)
                if p:
                    skills[c] = {"status": p[0], "evidence": p[1]}

    if re.search(r"\b(mba|m\.?\s?com|m\.?\s?sc|masters?)\b", edu, re.I):
        level = "Postgraduate"
    elif re.search(r"\b(b\.?\s?com|bba|b\.?\s?tech|b\.?\s?sc|b\.?\s?a\b|bca|graduat|bachelor)", edu, re.I):
        level = "Graduate"
    elif re.search(r"diploma", edu, re.I):
        level = "Diploma"
    elif re.search(r"class 12|12th", edu, re.I):
        level = "Class 12"
    else:
        level = "Other"

    em = EMAIL.search(text)
    ph = PHONE.search(text)
    headline = (roles[0]["role"] + (", " + roles[0]["org"].split(",")[0] if roles[0]["org"] else "")) if roles \
        else (summary or (lines[1] if len(lines) > 1 else ""))[:70]
    return {
        "name": name, "email": em.group(0) if em else "", "phone": ph.group(0).strip() if ph else "",
        "location": loc, "summary": summary or (sentences[0] if sentences else ""), "education": edu,
        "edu_level": level, "years": years, "roles": roles, "skills": skills, "headline": headline,
        "cv_text": text.strip(),
    }
