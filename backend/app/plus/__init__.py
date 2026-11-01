"""HireMate Plus: 40 extra features on top of the 5 core requirements.

Kept in its own folder so the core app (R1–R5) stays exactly as it was:
  insights.py      best fit elsewhere, dropout risk, commute, salary fit, hire & train, ask the CV, CV coach, briefing
  talent.py        success profile, integrity check, why-not, hidden gems, JD reality, career path, runners-up,
                   silver list, offer at risk, second opinion, pool health, skill demand, duplicates & merge
  hr_tools.py      job posts, notes → scorecard, question bank, Hindi CVs, recruiter performance, live helper,
                   panel check, role-plays, tone switch, policy answers, bulk update, decision journal, blind first look
  portal_tools.py  CV builder, AI chat screening, self-booking, status timing, joining checklist, billing test
  router.py        all /plus endpoints
"""
from .. import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS plus_qbank(id INTEGER PRIMARY KEY, role TEXT NOT NULL, question TEXT NOT NULL, qtype TEXT,
  up INTEGER DEFAULT 0, down INTEGER DEFAULT 0, added_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plus_panel(id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id)
  ON DELETE CASCADE, rater TEXT, scores_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plus_decisions(id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id)
  ON DELETE CASCADE, decision TEXT, reason TEXT, by_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plus_revealed(candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
  by_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS plus_screen(application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
  items_json TEXT, total INTEGER, ai INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS plus_joining(application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  doc TEXT NOT NULL, file_name TEXT, path TEXT, uploaded_at TEXT, verified_by TEXT, verified_at TEXT,
  PRIMARY KEY(application_id, doc));
CREATE TABLE IF NOT EXISTS plus_tests(id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id)
  ON DELETE CASCADE, seed INTEGER, started_at TEXT, finished_at TEXT, score INTEGER, total INTEGER, seconds INTEGER,
  detail_json TEXT);
"""


def ensure_schema() -> None:
    db.conn().executescript(SCHEMA)


def lc(s: str) -> str:
    """Lower-case a skill name for a sentence but keep acronyms: 'POS systems' stays, 'Cash handling' -> 'cash handling'."""
    return " ".join(w if (w.isupper() or (len(w) > 1 and any(ch.isupper() for ch in w[1:]))) else w.lower()
                    for w in (s or "").split())
