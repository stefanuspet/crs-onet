"""SQLite storage for questionnaire sessions.

No names or other personal details are stored: a session is a random code plus its answers.
The answers are what later calibration and evaluation need.
"""
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "crs.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    max_job_zone   INTEGER,
    finished_early INTEGER NOT NULL DEFAULT 0,
    finished_at    TEXT,
    outcome        TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    value       INTEGER NOT NULL,
    is_repeat   INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path():
    return Path(os.environ.get("CRS_DB", DEFAULT_DB))


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_session(max_job_zone=None):
    session_id = secrets.token_urlsafe(12)
    with connect() as conn:
        conn.execute("INSERT INTO sessions (id, created_at, max_job_zone) VALUES (?, ?, ?)",
                     (session_id, _now(), max_job_zone))
    return session_id


def get_session(session_id):
    """Return (session row, [answer rows in order]) or None."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        answers = conn.execute("SELECT * FROM answers WHERE session_id = ? ORDER BY seq", (session_id,)).fetchall()
    return row, answers


def add_answer(session_id, kind, idx, value, is_repeat):
    with connect() as conn:
        seq = conn.execute("SELECT COUNT(*) FROM answers WHERE session_id = ?", (session_id,)).fetchone()[0]
        conn.execute("INSERT INTO answers VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (session_id, seq, kind, idx, value, int(is_repeat), _now()))


def mark_finished(session_id, outcome, early=False):
    with connect() as conn:
        conn.execute("UPDATE sessions SET finished_at = COALESCE(finished_at, ?), outcome = ?, "
                     "finished_early = MAX(finished_early, ?) WHERE id = ?",
                     (_now(), outcome, int(early), session_id))
