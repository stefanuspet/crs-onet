"""Storage for questionnaire sessions, answers and feedback.

Two backends behind the same functions:
  - SQLite file (default, data/crs.sqlite3; override with CRS_DB) for local use
  - Postgres, when a DATABASE_URL is given, for hosting where local files do not survive restarts

No names or other personal details are stored: a session is a random code plus its answers
and, if the student gives it, feedback.
"""
import json
import os
import secrets
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "crs.sqlite3"

TABLES = [
    """CREATE TABLE IF NOT EXISTS sessions (
        id             TEXT PRIMARY KEY,
        created_at     TEXT NOT NULL,
        max_job_zone   INTEGER,
        finished_early INTEGER NOT NULL DEFAULT 0,
        finished_at    TEXT,
        outcome        TEXT,
        consent        INTEGER NOT NULL DEFAULT 0,
        cohort         TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS answers (
        session_id  TEXT NOT NULL REFERENCES sessions(id),
        seq         INTEGER NOT NULL,
        kind        TEXT NOT NULL,
        idx         INTEGER NOT NULL,
        value       INTEGER NOT NULL,
        is_repeat   INTEGER NOT NULL,
        answered_at TEXT NOT NULL,
        PRIMARY KEY (session_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS feedback (
        session_id  TEXT PRIMARY KEY REFERENCES sessions(id),
        relevance   INTEGER NOT NULL,
        ease        INTEGER NOT NULL,
        interested  TEXT NOT NULL,
        sus         TEXT,
        comment     TEXT,
        created_at  TEXT NOT NULL
    )""",
]
# Columns added after the first version; applied to SQLite files created before them.
ADDED_COLUMNS = {"sessions": {"consent": "INTEGER NOT NULL DEFAULT 0", "cohort": "TEXT"}}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Queries are written with '?' placeholders and work on both backends."""

    def __init__(self, database_url=None):
        self.database_url = database_url
        self._lock = threading.Lock()
        self._pg = None
        self._ready_for = None   # SQLite path whose schema has been prepared
        self._fallback = None    # temporary SQLite path, used when the default one is not writable

    @property
    def backend(self):
        return "postgres" if self.database_url else "sqlite"

    # ---- connections
    def sqlite_path(self):
        return Path(os.environ.get("CRS_DB") or self._fallback or DEFAULT_DB)

    def _sqlite(self):
        path = self.sqlite_path()
        try:
            conn = sqlite3.connect(path)
            conn.execute("BEGIN IMMEDIATE")   # takes the write lock: fails here if the file cannot be written
            conn.rollback()
        except sqlite3.OperationalError:
            # Read-only or missing folder on the host: keep the app usable with a temporary file.
            if os.environ.get("CRS_DB") or self._fallback:
                raise
            self._fallback = Path(tempfile.gettempdir()) / "crs.sqlite3"
            return self._sqlite()
        conn.row_factory = sqlite3.Row
        if self._ready_for != path:
            for ddl in TABLES:
                conn.execute(ddl)
            for table, columns in ADDED_COLUMNS.items():
                existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            conn.commit()
            self._ready_for = path
        return conn

    def _postgres(self):
        import psycopg
        from psycopg.rows import dict_row
        if self._pg is None or self._pg.closed:
            # prepare_threshold=None: hosted Postgres is often reached through a transaction pooler,
            # which does not support server-side prepared statements.
            self._pg = psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row,
                                       prepare_threshold=None, connect_timeout=15)
            for ddl in TABLES:
                self._pg.execute(ddl)
        return self._pg

    def _run(self, sql, params=(), fetch=None):
        """fetch: None (write), 'one' or 'all'."""
        if self.backend == "sqlite":
            conn = self._sqlite()
            try:
                cur = conn.execute(sql, params)
                rows = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
                conn.commit()
                return rows
            finally:
                conn.close()
        import psycopg
        with self._lock:
            for attempt in (1, 2):   # a hosted connection can drop while the app is idle: reconnect once
                try:
                    cur = self._postgres().execute(sql.replace("?", "%s"), params)
                    return cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
                except psycopg.OperationalError:
                    if self._pg is not None:
                        self._pg.close()
                    self._pg = None
                    if attempt == 2:
                        raise

    # ---- sessions and answers
    def create_session(self, max_job_zone=None, consent=False, cohort=None):
        session_id = secrets.token_urlsafe(12)
        self._run("INSERT INTO sessions (id, created_at, max_job_zone, consent, cohort) VALUES (?, ?, ?, ?, ?)",
                  (session_id, _now(), max_job_zone, int(consent), cohort))
        return session_id

    def get_session(self, session_id):
        """Return (session row, [answer rows in order]) or None."""
        row = self._run("SELECT * FROM sessions WHERE id = ?", (session_id,), "one")
        if row is None:
            return None
        return row, self._run("SELECT * FROM answers WHERE session_id = ? ORDER BY seq", (session_id,), "all")

    def add_answer(self, session_id, seq, kind, idx, value, is_repeat):
        self._run("INSERT INTO answers (session_id, seq, kind, idx, value, is_repeat, answered_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?)", (session_id, seq, kind, idx, value, int(is_repeat), _now()))

    def count_answers(self, session_id):
        return self._run("SELECT COUNT(*) AS n FROM answers WHERE session_id = ?", (session_id,), "one")["n"]

    def mark_finished(self, session_id, outcome, early=False):
        self._run("UPDATE sessions SET finished_at = COALESCE(finished_at, ?), outcome = ?, "
                  "finished_early = CASE WHEN finished_early > ? THEN finished_early ELSE ? END WHERE id = ?",
                  (_now(), outcome, int(early), int(early), session_id))

    # ---- feedback
    def save_feedback(self, session_id, relevance, ease, interested, sus, comment):
        self._run("INSERT INTO feedback (session_id, relevance, ease, interested, sus, comment, created_at) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (session_id) DO UPDATE SET "
                  "relevance = excluded.relevance, ease = excluded.ease, interested = excluded.interested, "
                  "sus = excluded.sus, comment = excluded.comment, created_at = excluded.created_at",
                  (session_id, relevance, ease, json.dumps(interested),
                   json.dumps(sus) if sus else None, comment or None, _now()))

    def get_feedback(self, session_id):
        return self._run("SELECT * FROM feedback WHERE session_id = ?", (session_id,), "one")

    # ---- export
    def all_session_ids(self):
        return [r["id"] for r in self._run("SELECT id FROM sessions ORDER BY created_at, id", fetch="all")]

    def all_answers(self):
        return self._run("SELECT * FROM answers ORDER BY session_id, seq", fetch="all")
