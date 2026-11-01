"""SQLite: schema + small helpers. SQLite is the source of truth."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any, Iterable

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('Admin','Recruiter','Interviewer')),
  password_hash TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, location TEXT, description TEXT NOT NULL,
  min_years REAL DEFAULT 0, qualification TEXT, status TEXT DEFAULT 'Open',
  source TEXT DEFAULT 'Seed', file_name TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS job_skills(
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, skill TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('must','nice')), PRIMARY KEY(job_id, skill));
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT, location TEXT,
  headline TEXT, summary TEXT, education TEXT, edu_level TEXT, years REAL DEFAULT 0,
  roles_json TEXT DEFAULT '[]', cv_text TEXT NOT NULL, file_name TEXT,
  source TEXT DEFAULT 'Seed', created_at TEXT);
CREATE TABLE IF NOT EXISTS candidate_skills(
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE, skill TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('Proven','Listed')), evidence TEXT,
  PRIMARY KEY(candidate_id, skill));
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  stage TEXT NOT NULL DEFAULT 'Applied', created_at TEXT, updated_at TEXT,
  UNIQUE(job_id, candidate_id));
CREATE TABLE IF NOT EXISTS match_results(
  application_id INTEGER PRIMARY KEY REFERENCES applications(id) ON DELETE CASCADE,
  score INTEGER, skill_score INTEGER, text_score INTEGER, exp_score INTEGER,
  details_json TEXT, computed_at TEXT);
CREATE TABLE IF NOT EXISTS interviews(
  id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  date TEXT NOT NULL, time TEXT NOT NULL, mode TEXT, interviewer TEXT,
  status TEXT DEFAULT 'Scheduled', questions_json TEXT, assessment TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS interview_feedback(
  id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  scores_json TEXT, text TEXT, by_name TEXT, ai_summary TEXT, readiness INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS emails(
  id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  type TEXT NOT NULL, lang TEXT DEFAULT 'English', subject TEXT, body TEXT,
  status TEXT DEFAULT 'Draft', approved_by TEXT, approved_at TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  job_id INTEGER, text TEXT NOT NULL, by_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS knowledge_docs(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, type TEXT NOT NULL DEFAULT 'Policy',
  text TEXT NOT NULL, source TEXT DEFAULT 'Seed', file_name TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS activity_logs(
  id INTEGER PRIMARY KEY, entity TEXT, entity_id INTEGER, candidate_id INTEGER, job_id INTEGER,
  action TEXT, detail TEXT, by_name TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS assistant_sessions(id TEXT PRIMARY KEY, user_id INTEGER, state_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS criteria(
  id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
  text TEXT NOT NULL, kind TEXT NOT NULL, check_type TEXT NOT NULL, value TEXT, points INTEGER DEFAULT 10,
  active INTEGER DEFAULT 1, created_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS criteria_checks(
  criterion_id INTEGER NOT NULL, cv_hash TEXT NOT NULL, status TEXT, evidence TEXT, by_ai INTEGER,
  PRIMARY KEY(criterion_id, cv_hash));
CREATE TABLE IF NOT EXISTS candidate_accounts(
  candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE, email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL, created_at TEXT, last_login TEXT);
CREATE TABLE IF NOT EXISTS generated_files(
  id INTEGER PRIMARY KEY, name TEXT, path TEXT, mime TEXT, created_at TEXT);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA journal_mode=WAL")      # faster writes, readers don't block
        _conn.execute("PRAGMA synchronous=NORMAL")    # safe with WAL, far fewer disk syncs
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    return _conn


# columns added after the first release; added in place so existing databases keep their data
_NEW_COLS = {
    "emails": [("direction", "TEXT DEFAULT 'out'"), ("sent_at", "TEXT"), ("sent_by", "TEXT"), ("read_at", "TEXT"),
               ("parent_id", "INTEGER"), ("cand_read_at", "TEXT")],
    "users": [("active", "INTEGER DEFAULT 1"), ("last_login", "TEXT")],
    "interviews": [("candidate_response", "TEXT"), ("candidate_note", "TEXT"), ("responded_at", "TEXT")],
}


def _migrate(c: sqlite3.Connection) -> None:
    for table, cols in _NEW_COLS.items():
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        for name, decl in cols:
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    # old demo accounts get neutral demo names
    c.execute("UPDATE users SET email='admin@hiremate.demo', name='Demo Admin' WHERE lower(email)='muskan@hiremate.demo' "
              "AND NOT EXISTS(SELECT 1 FROM users WHERE email='admin@hiremate.demo')")
    c.execute("UPDATE users SET name='Demo Recruiter' WHERE email='recruiter@hiremate.demo' AND name='Ravi Kumar'")
    c.execute("UPDATE users SET name='Demo Interviewer' WHERE email='interviewer@hiremate.demo' AND name='Neha Gupta'")
    # 'Approved' used to mean 'ready to send'; it is now 'Sent'
    c.execute("UPDATE emails SET status='Sent', sent_at=COALESCE(sent_at, approved_at), sent_by=COALESCE(sent_by, approved_by) "
              "WHERE status='Approved'")
    c.commit()


def reset_connection() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None


def rows(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    with _lock:
        r = conn().execute(sql, tuple(params)).fetchone()
        return dict(r) if r else None


def run(sql: str, params: Iterable[Any] = ()) -> int:
    """Execute a write and return lastrowid."""
    with _lock:
        c = conn()
        cur = c.execute(sql, tuple(params))
        c.commit()
        return cur.lastrowid


def run_many(sql: str, seq: list[tuple]) -> None:
    """Many writes in ONE transaction (one disk sync instead of one per row)."""
    if not seq:
        return
    with _lock:
        c = conn()
        c.executemany(sql, seq)
        c.commit()


def get_setting(key: str, default: Any = None) -> Any:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value: Any) -> None:
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)))


def log(action: str, detail: str = "", by: str = "System", candidate_id: int | None = None,
        job_id: int | None = None, entity: str = "", entity_id: int | None = None) -> None:
    run("INSERT INTO activity_logs(entity,entity_id,candidate_id,job_id,action,detail,by_name,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)", (entity, entity_id, candidate_id, job_id, action, detail, by, now()))
