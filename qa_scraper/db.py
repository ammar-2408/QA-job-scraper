"""Database access for runs, boards and jobs.

One small wrapper over two backends so the same SQL runs everywhere:

  * Postgres  when DATABASE_URL (or POSTGRES_URL) starts with postgres:// - the hosted
    database the website and the GitHub Actions runs share;
  * SQLite    otherwise (data/jobs.db) - local runs and tests.

SQL is written with `?` placeholders and portable syntax (ON CONFLICT ... DO UPDATE,
RETURNING); the wrapper converts placeholders for Postgres. Dates and timestamps are
stored as ISO text so they sort and compare the same in both backends.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

from . import config

SQLITE_PATH = config.DATA_DIR / "jobs.db"

# Every Job field stored in the jobs table (description included, detail_ref not).
JOB_FIELDS = ["title", "company", "job_url", "source", "source_kind", "board", "external_id", "location",
              "country", "remote_type", "salary", "posted_date", "date_source", "days_old", "description",
              "company_url", "apply_url", "role_type", "seniority", "experience", "tools", "trust",
              "trust_reasons", "qa_match"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id {ID},
    created_at TEXT, started_at TEXT, finished_at TEXT, heartbeat TEXT,
    status TEXT,                      -- queued | running | done | failed | cancelled
    mode TEXT, max_age INTEGER, trigger TEXT,
    boards_total INTEGER DEFAULT 0, boards_done INTEGER DEFAULT 0, boards_failed INTEGER DEFAULT 0,
    jobs_seen INTEGER DEFAULT 0, qa_found INTEGER DEFAULT 0, kept INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0, closed_jobs INTEGER DEFAULT 0,
    cancel_requested INTEGER DEFAULT 0, gh_run_id TEXT, error TEXT, seconds REAL,
    next_index INTEGER DEFAULT 0, step_size INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS boards (
    key TEXT PRIMARY KEY, company TEXT, ats TEXT, token TEXT, careers_url TEXT,
    first_scanned TEXT, last_scanned TEXT, last_status TEXT, last_error TEXT,
    jobs_total INTEGER DEFAULT 0, qa_jobs INTEGER DEFAULT 0, kept INTEGER DEFAULT 0,
    last_qa_date TEXT, last_run_id INTEGER, seconds REAL
);
CREATE TABLE IF NOT EXISTS seen (
    identity TEXT PRIMARY KEY, board TEXT, title TEXT, company TEXT, job_url TEXT,
    first_seen TEXT, last_seen TEXT, last_run_id INTEGER
);
CREATE TABLE IF NOT EXISTS jobs (
    identity TEXT PRIMARY KEY,
    {JOB_COLUMNS},
    detail_url TEXT, category TEXT, duplicate INTEGER DEFAULT 0,
    first_seen TEXT, last_seen TEXT, first_run_id INTEGER, last_run_id INTEGER,
    status TEXT DEFAULT 'open', closed_on TEXT, updated_at TEXT, result_run_id INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS jobs_board ON jobs (board);
CREATE TABLE IF NOT EXISTS run_retries (id {ID}, run_id INTEGER, key TEXT);
CREATE INDEX IF NOT EXISTS seen_board ON seen (board);
CREATE INDEX IF NOT EXISTS jobs_result_run ON jobs (result_run_id);
"""


# Columns added after the first release: (table, column, type). Added to older databases.
_MIGRATIONS = [("runs", "next_index", "INTEGER DEFAULT 0"), ("runs", "step_size", "INTEGER DEFAULT 0"),
               ("jobs", "result_run_id", "INTEGER"), ("jobs", "apply_ok", "INTEGER DEFAULT 1")]


def database_url() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""


class DB:
    def __init__(self, url: str | None = None):
        url = database_url() if url is None else url
        self.lock = threading.Lock()
        if url.startswith(("postgres://", "postgresql://")):
            import psycopg
            from psycopg.rows import dict_row
            self.kind = "pg"
            self.conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=15)
        else:
            path = Path(url[len("sqlite:///"):]) if url.startswith("sqlite:///") else SQLITE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            self.kind = "sqlite"
            self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")

    # -- low level ---------------------------------------------------------------
    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.kind == "pg" else sql

    def execute(self, sql: str, params=()) -> None:
        with self.lock:
            self.conn.execute(self._q(sql), params)

    def many(self, sql: str, rows) -> None:
        rows = list(rows)
        if not rows:
            return
        with self.lock:
            if self.kind == "pg":
                with self.conn.cursor() as cur:
                    cur.executemany(self._q(sql), rows)
            else:
                self.conn.executemany(sql, rows)

    def all(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            cur = self.conn.execute(self._q(sql), params)
            return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def transaction(self):
        """Group many writes into one commit (much faster over the network)."""
        return _Tx(self)

    def init_schema(self) -> None:
        ident = "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY" if self.kind == "pg" \
            else "INTEGER PRIMARY KEY AUTOINCREMENT"
        cols = ",\n    ".join(f"{f} INTEGER" if f == "days_old" else f"{f} TEXT" for f in JOB_FIELDS)
        script = _SCHEMA.replace("{ID}", ident).replace("{JOB_COLUMNS}", cols)
        index_lines = [l for l in script.splitlines() if l.startswith("CREATE INDEX")]
        script = "\n".join(l for l in script.splitlines() if not l.startswith("CREATE INDEX"))
        with self.lock:
            if self.kind == "pg":
                for stmt in (s.strip() for s in script.split(";")):
                    body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--"))
                    if body.strip():
                        self.conn.execute(body)
            else:
                self.conn.executescript(script)
            for table, col, typ in _MIGRATIONS:
                have = self._columns(table)
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            for line in index_lines:
                self.conn.execute(line.rstrip(";"))

    def _columns(self, table: str) -> set[str]:
        if self.kind == "pg":
            rows = self.conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s",
                                     (table,)).fetchall()
            return {r["column_name"] for r in rows}
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


class _Tx:
    def __init__(self, db: DB):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        if self.db.kind == "pg":
            self._tx = self.db.conn.transaction()
            self._tx.__enter__()
        else:
            self.db.conn.execute("BEGIN")
        return _TxCursor(self.db)

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.db.kind == "pg":
                self._tx.__exit__(exc_type, exc, tb)
            else:
                self.db.conn.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.db.lock.release()
        return False


class _TxCursor:
    """execute/many inside a transaction (the DB lock is already held)."""
    def __init__(self, db: DB):
        self.db = db

    def execute(self, sql: str, params=()) -> None:
        self.db.conn.execute(self.db._q(sql), params)

    def many(self, sql: str, rows) -> None:
        rows = list(rows)
        if not rows:
            return
        if self.db.kind == "pg":
            with self.db.conn.cursor() as cur:
                cur.executemany(self.db._q(sql), rows)
        else:
            self.db.conn.executemany(sql, rows)

    def all(self, sql: str, params=()) -> list[dict]:
        cur = self.db.conn.execute(self.db._q(sql), params)
        return [dict(r) for r in cur.fetchall()]
