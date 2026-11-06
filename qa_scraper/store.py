"""Run history, live results and open/closed tracking (see db.py for the backends).

What is stored:

  * runs    one row per run: status, progress counters (updated as boards finish),
            final counts. The website reads this for the progress bar.
  * boards  last scan of every board: status, error, counts, first successful scan.
  * seen    every QA-titled posting ever seen, whatever its age: first_seen/last_seen.
            Used for sources that publish no posted date (Manatal, Pinpoint, ...):
              - an undated job gets its first_seen date if we saw it before, or
              - today's date if its board was already scanned on an earlier day and
                the job was not there then (so it really is new);
              - on a board's very first scan its undated jobs stay "date unknown":
                we never guess an age we can't know.
  * jobs    every job that passed the filters (kept / undated / flagged), saved as
            soon as its board finishes so the website shows results live.

Open / closed: after a run, a job whose company board was scanned successfully but no
longer lists it is marked closed. Jobs of boards that failed are never closed, and
open-job-site jobs never close by absence (those feeds only show recent postings).
Boards that use keyword search (Workday, SmartRecruiters, Oracle) can miss a posting
on a bad search page, so a missing job there is only closed if its own page is gone.

"NEW" = the job's first_run_id is the latest run.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone

from .db import DB, JOB_FIELDS
from .text import today

SEARCH_BASED = {"workday", "smartrecruiters", "oraclehcm"}
ACTIVE = ("queued", "running")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_JOB_COLS = ["identity", *JOB_FIELDS, "detail_url", "category", "duplicate", "first_seen", "last_seen",
             "first_run_id", "last_run_id", "status", "closed_on", "updated_at", "result_run_id"]
_KEEP_ON_UPDATE = {"identity", "first_seen", "first_run_id"}
_JOB_UPSERT = (f"INSERT INTO jobs ({', '.join(_JOB_COLS)}) VALUES ({', '.join('?' * len(_JOB_COLS))}) "
               f"ON CONFLICT(identity) DO UPDATE SET "
               + ", ".join(f"{c}=excluded.{c}" for c in _JOB_COLS if c not in _KEEP_ON_UPDATE))


class Store:
    def __init__(self, path=None, db: DB | None = None, run_id: int | None = None,
                 mode: str = "full", trigger: str = "cli", init: bool = True):
        self._owns_db = db is None
        self.db = db or (DB(f"sqlite:///{path}") if path else DB())
        if init:
            self.db.init_schema()
        self.today = today().isoformat()
        self.run_id = run_id
        self.mode, self.trigger = mode, trigger
        self._seen = {r["identity"]: r["first_seen"] for r in self.db.all("SELECT identity, first_seen FROM seen")}
        self._boards = {r["key"]: r["first_scanned"] for r in self.db.all("SELECT key, first_scanned FROM boards")}
        self._written: set[str] = set()
        self._t0 = time.time()
        self._last_check = 0.0
        self._cancel = False

    # -- used while processing jobs (in memory, no I/O) ----------------------------
    def board_known_before_today(self, key: str) -> bool:
        first = self._boards.get(key)
        return bool(first and first < self.today)

    def first_seen(self, identity: str) -> str | None:
        return self._seen.get(identity)

    def record(self, job) -> None:
        self._seen.setdefault(job.identity(), self.today)

    def mark_board(self, key: str) -> None:
        pass                              # written by board_done

    # -- run lifecycle ---------------------------------------------------------------
    async def start(self, max_age: int, boards_total: int) -> None:
        await asyncio.to_thread(self._start, max_age, boards_total)

    def _start(self, max_age: int, boards_total: int) -> None:
        now, gh = now_iso(), os.getenv("GITHUB_RUN_ID") or None
        if self.run_id is None:
            row = self.db.one("INSERT INTO runs (created_at, started_at, heartbeat, status, mode, max_age, trigger, "
                              "boards_total, gh_run_id) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
                              (now, now, now, "running", self.mode, max_age, self.trigger, boards_total, gh))
            self.run_id = row["id"]
        else:
            self.db.execute("UPDATE runs SET started_at=?, heartbeat=?, status='running', mode=?, max_age=?, "
                            "boards_total=?, gh_run_id=COALESCE(?, gh_run_id) WHERE id=?",
                            (now, now, self.mode, max_age, boards_total, gh, self.run_id))

    async def cancel_requested(self) -> bool:
        """Checked every few seconds by the pipeline; also keeps the heartbeat fresh."""
        if self._cancel or time.time() - self._last_check < 10 or self.run_id is None:
            return self._cancel
        self._last_check = time.time()

        def check():
            self.db.execute("UPDATE runs SET heartbeat=? WHERE id=?", (now_iso(), self.run_id))
            row = self.db.one("SELECT cancel_requested FROM runs WHERE id=?", (self.run_id,))
            return bool(row and row["cancel_requested"])
        try:
            self._cancel = await asyncio.to_thread(check)
        except Exception:
            pass                          # a hiccup on the database must not stop the run
        return self._cancel

    async def board_done(self, br) -> None:
        await asyncio.to_thread(self._flush_board, br)

    def _flush_board(self, br) -> None:
        b, run, day = br.board, self.run_id, self.today
        now = now_iso()
        with self.db.transaction() as tx:
            if br.ok:
                tx.many("INSERT INTO seen VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(identity) DO UPDATE SET "
                        "last_seen=excluded.last_seen, last_run_id=excluded.last_run_id, title=excluded.title",
                        [(j.identity(), j.board, j.title, j.company, j.job_url,
                          self._seen.get(j.identity(), day), day, run) for j in br.seen])
                tx.many("UPDATE jobs SET last_seen=?, last_run_id=?, status='open', closed_on=NULL WHERE identity=?",
                        [(day, run, j.identity()) for j in br.seen])
                rows = []
                for j in br.results:
                    ident = j.identity()
                    self._written.add(ident)
                    rows.append((ident, *[getattr(j, f) for f in JOB_FIELDS],
                                 j.detail_ref.get("url") or "", j.category, 0, self._seen.get(ident, day), day,
                                 run, run, "open", None, now, run))
                tx.many(_JOB_UPSERT, rows)
            tx.execute(
                "INSERT INTO boards (key, company, ats, token, careers_url, first_scanned, last_scanned, last_status, "
                "last_error, jobs_total, qa_jobs, kept, last_qa_date, last_run_id, seconds) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET company=excluded.company, "
                "ats=excluded.ats, token=excluded.token, careers_url=excluded.careers_url, first_scanned=COALESCE(boards.first_scanned, excluded.first_scanned), "
                "last_scanned=excluded.last_scanned, last_status=excluded.last_status, last_error=excluded.last_error, "
                "jobs_total=excluded.jobs_total, qa_jobs=excluded.qa_jobs, kept=excluded.kept, "
                "last_qa_date=COALESCE(excluded.last_qa_date, boards.last_qa_date), last_run_id=excluded.last_run_id, "
                "seconds=excluded.seconds",
                (b.key, b.company, b.ats, b.token, b.careers_url, day if br.ok else None, day,
                 "ok" if br.ok else "failed", br.error, br.total_jobs, br.qa_jobs, br.kept,
                 day if br.qa_jobs else None, run, br.seconds))
            if run is not None:
                tx.execute("UPDATE runs SET boards_done=boards_done+1, boards_failed=boards_failed+?, "
                           "jobs_seen=jobs_seen+?, qa_found=qa_found+?, kept=kept+?, heartbeat=? WHERE id=?",
                           (0 if br.ok else 1, br.total_jobs, br.qa_jobs, br.kept, now, run))
        if br.ok:
            self._boards.setdefault(b.key, day)
        br.saved = True

    async def finish(self, res, http=None, status: str = "done", error: str = "") -> None:
        if self.run_id is None:
            return
        out = await finalize(self.db, self.run_id, http, status, error, seconds=round(time.time() - self._t0, 1))
        res.new_jobs, res.closed_jobs = out["new_jobs"], out["closed_jobs"]

    def close(self) -> None:
        if self._owns_db:
            self.db.close()


async def finalize(db: DB, run_id: int, http=None, status: str = "done", error: str = "",
                   seconds: float | None = None) -> dict:
    """End of a run, worked out from the database (so it also works when the run was
    spread over many short web requests): hide duplicates, close jobs that disappeared,
    write the final counts."""
    from . import pipeline
    from .models import Job
    rows = await asyncio.to_thread(db.all, "SELECT * FROM jobs WHERE result_run_id=?", (run_id,))
    jobs = {"kept": [], "undated": [], "flagged": []}
    for r in rows:
        j = Job(**{f: r[f] for f in JOB_FIELDS if f in ("title", "company", "job_url", "source")})
        for f in JOB_FIELDS:
            setattr(j, f, r[f] if r[f] is not None else ("" if f != "days_old" else None))
        j.category = r["category"]
        j._ident = r["identity"]
        jobs.setdefault(r["category"], []).append(j)
    kept, _ = pipeline._drop_aggregator_copies(jobs["kept"])
    kept, _ = pipeline._dedupe(kept)
    undated, _ = pipeline._dedupe(jobs["undated"])
    final = {j._ident for j in kept + undated + jobs["flagged"]}
    written = {r["identity"] for r in rows}

    ok_boards = {r["key"] for r in await asyncio.to_thread(
        db.all, "SELECT key FROM boards WHERE last_run_id=? AND last_status='ok' AND ats != 'feed'", (run_id,))}
    gone: list[str] = []
    if ok_boards:
        cands = await asyncio.to_thread(
            db.all, "SELECT identity, board, source, detail_url FROM jobs "
                    "WHERE status='open' AND (last_run_id IS NULL OR last_run_id<?)", (run_id,))
        cands = [c for c in cands if c["board"] in ok_boards]
        verify = [c for c in cands if c["source"] in SEARCH_BASED]
        gone = [c["identity"] for c in cands if c["source"] not in SEARCH_BASED]
        if verify and http is not None:
            async def page_gone(c):
                if not c["detail_url"]:
                    return False
                r = await http.request("GET", c["detail_url"])
                return r is not None and r.status_code in (404, 410)
            flags = await asyncio.gather(*(page_gone(c) for c in verify))
            gone += [c["identity"] for c, g in zip(verify, flags) if g]

    day = today().isoformat()

    def write():
        with db.transaction() as tx:
            tx.many("UPDATE jobs SET duplicate=1 WHERE identity=?", [(i,) for i in written - final])
            tx.many("UPDATE jobs SET duplicate=0 WHERE identity=?", [(i,) for i in final])
            tx.many("UPDATE jobs SET status='closed', closed_on=? WHERE identity=?", [(day, i) for i in gone])
        new = db.one("SELECT COUNT(*) AS n FROM jobs WHERE first_run_id=? AND duplicate=0 AND category='kept'",
                     (run_id,))["n"]
        run = db.one("SELECT started_at FROM runs WHERE id=?", (run_id,)) or {}
        secs = seconds
        if secs is None and run.get("started_at"):
            secs = round((datetime.now(timezone.utc) - datetime.fromisoformat(run["started_at"])).total_seconds(), 1)
        db.execute("UPDATE runs SET status=?, finished_at=?, heartbeat=?, seconds=?, kept=?, new_jobs=?, "
                   "closed_jobs=?, error=COALESCE(?, error) WHERE id=?",
                   (status, now_iso(), now_iso(), secs, len(kept), new, len(gone), error or None, run_id))
        return {"new_jobs": new, "closed_jobs": len(gone), "kept": len(kept)}
    return await asyncio.to_thread(write)


class NullStore:
    """Used by one-off checks (check_board.py) so they don't alter run history."""
    today = today().isoformat()
    run_id = None

    def board_known_before_today(self, key): return False
    def mark_board(self, key): pass
    def first_seen(self, identity): return None
    def record(self, job): pass
    async def start(self, max_age, boards_total): pass
    async def cancel_requested(self): return False
    async def board_done(self, br): pass
    async def finish(self, res, http=None, status="done", error=""): pass
    def close(self): pass


def set_run_status(run_id: int, status: str, error: str = "") -> None:
    """Used by the GitHub workflow when the scraper process itself crashed or was cancelled."""
    db = DB()
    db.init_schema()
    db.execute("UPDATE runs SET status=?, finished_at=?, error=COALESCE(?, error) WHERE id=? AND status IN (?,?)",
               (status, now_iso(), error or None, run_id, *ACTIVE))
    db.close()


def import_history(path) -> None:
    """Copy first-seen history from the old data/history.db into the current database."""
    import sqlite3
    src = sqlite3.connect(path)
    db = DB()
    db.init_schema()
    boards = src.execute("SELECT key, first_scanned, last_scanned FROM boards").fetchall()
    jobs = src.execute("SELECT identity, board, title, company, job_url, first_seen, last_seen FROM jobs").fetchall()
    with db.transaction() as tx:
        tx.many("INSERT INTO boards (key, first_scanned, last_scanned) VALUES (?,?,?) ON CONFLICT(key) DO NOTHING",
                boards)
        tx.many("INSERT INTO seen (identity, board, title, company, job_url, first_seen, last_seen) "
                "VALUES (?,?,?,?,?,?,?) ON CONFLICT(identity) DO NOTHING", jobs)
    print(f"Imported {len(boards)} boards and {len(jobs)} seen jobs into the {db.kind} database.")
    db.close()


if __name__ == "__main__":
    # python -m qa_scraper.store status <run_id> <failed|cancelled> [message]
    # python -m qa_scraper.store import-history [data/history.db]
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "status":
        set_run_status(int(sys.argv[2]), sys.argv[3], " ".join(sys.argv[4:]))
    elif cmd == "import-history":
        from . import config
        import_history(sys.argv[2] if len(sys.argv) > 2 else config.DATA_DIR / "history.db")
    elif cmd == "init":
        d = DB()
        d.init_schema()
        print(f"{d.kind} schema ready")
    else:
        print(__doc__)
