"""Step-by-step runs for the website.

Vercel stops a web request after a few minutes, but a full run takes much longer.
So the website runs it in slices: every call to step() claims the next slice of
sources (open job sites first, then boards in a fixed order), scrapes it within a time
budget, saves the results, and returns. The open page keeps calling step() until all
sources are done; the last step finishes the run (duplicates, closed jobs, counts).

Slices are claimed with a compare-and-set on runs.next_index, so two open pages (or two
computers) can drive the same run without scraping a board twice. The slice size adapts
to how fast the previous slice went.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from datetime import date, datetime, timedelta, timezone

from . import pipeline
from .db import DB
from .feeds import FEEDS
from .http import Http
from .models import Board
from .store import Store, finalize, now_iso

QUICK_DAYS = 30
FIRST_STEP = 60          # sources in the first slice; later slices adapt
MIN_STEP, MAX_STEP = 10, 400
ACTIVE = ("queued", "running", "finishing")
MAX_RETRIES = 2          # a source cut off by the slice time limit is tried again later, twice at most


def _spread(key: str) -> str:
    """Fixed pseudo-random order, so slow systems (Workday...) are spread over all slices."""
    return hashlib.md5(key.encode()).hexdigest()


def run_items(db: DB, mode: str, created_at: str | None = None, run_id: int | None = None) -> list[tuple[str, object]]:
    """The ordered list of sources a run covers (same answer on every step), followed by
    the retries queued so far for this run."""
    feeds = [FEEDS[k] for k in sorted(FEEDS)]
    boards = [] if mode == "feeds" else sorted(pipeline.load_boards(), key=lambda b: _spread(b.key))
    if mode == "quick":
        day = (datetime.fromisoformat(created_at).date() if created_at else date.today())
        since = (day - timedelta(days=QUICK_DAYS)).isoformat()
        active = {r["key"] for r in db.all("SELECT key FROM boards WHERE last_qa_date >= ?", (since,))}
        if active:
            boards = [b for b in boards if b.key in active]
    items = [("feed", f) for f in feeds] + [("board", b) for b in boards]
    if run_id is not None:
        by_key = {_key(i): i for i in items}
        for r in db.all("SELECT key FROM run_retries WHERE run_id=? ORDER BY id", (run_id,)):
            if r["key"] in by_key:
                items.append(by_key[r["key"]])
    return items


def _key(item) -> str:
    kind, src = item
    return f"feed:{src.NAME}".lower() if kind == "feed" else src.key


def create_run(db: DB, mode: str, max_age: int, trigger: str = "website") -> int:
    ts = now_iso()
    total = len(run_items(db, mode, ts))
    return db.one("INSERT INTO runs (created_at, started_at, heartbeat, status, mode, max_age, trigger, boards_total, "
                  "next_index, step_size) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING id",
                  (ts, ts, ts, "running", mode, max_age, trigger, total, 0, FIRST_STEP))["id"]


def _run(db: DB, run_id: int) -> dict | None:
    return db.one("SELECT * FROM runs WHERE id=?", (run_id,))


def _claim(db: DB, run_id: int, total: int) -> tuple[int, int] | None:
    for _ in range(8):
        run = _run(db, run_id)
        if not run or run["status"] != "running" or run["next_index"] >= total:
            return None
        start, n = run["next_index"], run["step_size"] or FIRST_STEP
        got = db.one("UPDATE runs SET next_index=?, heartbeat=? WHERE id=? AND next_index=? RETURNING id",
                     (start + n, now_iso(), run_id, start))
        if got:
            return start, n
    return None


async def _finish(db: DB, run_id: int, status: str, error: str = "") -> None:
    """Only one caller wins the right to finish a run."""
    got = db.one("UPDATE runs SET status='finishing', heartbeat=? WHERE id=? AND status='running' RETURNING id",
                 (now_iso(), run_id))
    if not got:
        return
    try:
        async with Http() as http:
            await finalize(db, run_id, http, status, error)
    except Exception as e:
        db.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                   (now_iso(), f"finishing failed: {type(e).__name__}: {e}"[:300], run_id))


async def cancel(db: DB, run_id: int) -> None:
    db.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (run_id,))
    await _finish(db, run_id, "cancelled")


async def step(db: DB, run_id: int, budget: float) -> dict | None:
    """Do one slice of the run. Returns the updated runs row."""
    run = _run(db, run_id)
    if not run or run["status"] != "running":
        return run
    if run["cancel_requested"]:
        await _finish(db, run_id, "cancelled")
        return _run(db, run_id)
    items = run_items(db, run["mode"], run["created_at"], run_id)
    claim = _claim(db, run_id, len(items))
    if claim:
        start, n = claim
        chunk = items[start:start + n]
        store = Store(db=db, run_id=run_id, mode=run["mode"], init=False)
        t0 = time.time()
        res = await pipeline.run([b for k, b in chunk if k == "board"], max_age=run["max_age"], verbose=False,
                                 feeds=[f for k, f in chunk if k == "feed"], store=store, batch=True,
                                 deadline=t0 + budget)
        # Sources cut off by the time budget are queued again; after MAX_RETRIES they count
        # as failed (so the run always ends).
        finished = {br.board.key for br in res.boards if br.saved}
        for kind, src in chunk:
            board = Board(company=src.NAME, ats="feed", token=src.NAME) if kind == "feed" else src
            if board.key in finished:
                continue
            tries = db.one("SELECT COUNT(*) AS n FROM run_retries WHERE run_id=? AND key=?", (run_id, board.key))["n"]
            if tries < MAX_RETRIES:
                db.execute("INSERT INTO run_retries (run_id, key) VALUES (?,?)", (run_id, board.key))
            else:
                br = pipeline.BoardResult(board=board, error="timed out (slice time limit)")
                await asyncio.to_thread(store._flush_board, br)
        took = max(1.0, time.time() - t0)
        # A slice lasts as long as its slowest board, so keep slices big (parallel) and let the
        # time limit + retries deal with stragglers: grow while everything finishes, otherwise
        # size the next slice to what this one actually got through.
        done_n = sum(1 for br in res.boards if br.saved)
        size = max(MIN_STEP, int(done_n * 1.2)) if res.timed_out else 2 * n
        db.execute("UPDATE runs SET step_size=? WHERE id=?", (max(MIN_STEP, min(MAX_STEP, size)), run_id))

    run = _run(db, run_id)
    items = run_items(db, run["mode"], run["created_at"], run_id) if run else items
    if run and run["status"] == "running" and run["next_index"] >= len(items):
        beat = datetime.fromisoformat(run["heartbeat"]) if run["heartbeat"] else None
        stuck = beat and datetime.now(timezone.utc) - beat > timedelta(seconds=budget + 120)
        if run["boards_done"] >= run["boards_total"] or stuck:   # stuck: a slice died with its request
            await _finish(db, run_id, "done", "" if not stuck else "some sources did not report back")
        run = _run(db, run_id)
    return run
