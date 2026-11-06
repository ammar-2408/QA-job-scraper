"""Run-to-run memory (SQLite, data/history.db - not committed).

Used for sources that publish no posted date (Manatal, Pinpoint, and any posting
whose date is missing):

  * every QA-titled job seen is recorded with first_seen / last_seen;
  * a board's first successful scan date is recorded;
  * on later runs, an undated job gets:
      - its first_seen date, if we saw it before, or
      - today's date, if its board was already scanned on an earlier day and the
        job was not there then (so it really is new);
    on a board's very first scan its undated jobs stay "date unknown" - we never
    guess an age we can't know.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config
from .text import today

DB_PATH = config.DATA_DIR / "history.db"


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS boards (key TEXT PRIMARY KEY, first_scanned TEXT, last_scanned TEXT);
            CREATE TABLE IF NOT EXISTS jobs (
                identity TEXT PRIMARY KEY, board TEXT, title TEXT, company TEXT, job_url TEXT,
                first_seen TEXT, last_seen TEXT);
        """)
        self.today = today().isoformat()

    def board_known_before_today(self, key: str) -> bool:
        row = self.db.execute("SELECT first_scanned FROM boards WHERE key=?", (key,)).fetchone()
        return bool(row and row[0] < self.today)

    def mark_board(self, key: str) -> None:
        self.db.execute("INSERT INTO boards VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET last_scanned=excluded.last_scanned",
                        (key, self.today, self.today))

    def first_seen(self, identity: str) -> str | None:
        row = self.db.execute("SELECT first_seen FROM jobs WHERE identity=?", (identity,)).fetchone()
        return row[0] if row else None

    def record(self, job) -> None:
        self.db.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET last_seen=excluded.last_seen",
            (job.identity(), job.board, job.title, job.company, job.job_url, self.today, self.today))

    def close(self) -> None:
        self.db.commit()
        self.db.close()


class NullStore:
    """Used by one-off checks (check_board.py) so they don't alter run history."""
    today = today().isoformat()

    def board_known_before_today(self, key): return False
    def mark_board(self, key): pass
    def first_seen(self, identity): return None
    def record(self, job): pass
    def close(self): pass
