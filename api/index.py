"""Website API (FastAPI). Runs on Vercel as one serverless function, or locally via serve.py.

Reads and writes the database (Postgres online, SQLite locally). Two ways to run a scrape:

  RUNNER=process  (Hugging Face Spaces, local serve.py) run.py is started as a background
                  process on this server; the page can be closed while it runs.
  RUNNER=batch    (Vercel, where requests stop after a few minutes) the open page keeps
                  calling POST /api/runs/{id}/step, which scrapes the next slice of sources
                  within STEP_SECONDS - see qa_scraper/batch.py.

Environment:
  DATABASE_URL    Postgres connection string (unset -> data/jobs.db)
  RUN_PASSWORD    password for starting/cancelling runs (unset -> no password)
  RUNNER          process | batch (default batch)
  STEP_SECONDS    time budget of one slice in batch mode (default 200)
"""
from __future__ import annotations

import hmac
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from qa_scraper import batch  # noqa: E402
from qa_scraper.config import REMOTE_ONLY  # noqa: E402
from qa_scraper.db import DB  # noqa: E402

STEP_SECONDS = float(os.getenv("STEP_SECONDS", "200"))
RUNNER = os.getenv("RUNNER", "batch")
STALE_RUNNING = timedelta(hours=6) if RUNNER == "batch" else timedelta(minutes=20)
STALE_QUEUED = timedelta(minutes=5)
STALE_FINISHING = timedelta(minutes=15)
CLOSED_DAYS = 30                         # closed jobs stay visible this long

LIST_COLS = ["identity", "title", "company", "location", "country", "remote_type", "salary", "posted_date",
             "date_source", "source", "source_kind", "board", "trust", "trust_reasons", "role_type", "seniority",
             "experience", "tools", "job_url", "apply_url", "company_url", "category", "first_seen", "last_seen",
             "first_run_id", "status", "closed_on"]

app = FastAPI(title="QA Job Scraper", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
_schema_ready = False


def db() -> DB:
    global _schema_ready
    d = DB()
    if not _schema_ready:
        d.init_schema()
        _schema_ready = True
    return d


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> date:
    return now().date()


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def check_password(given: str | None) -> None:
    want = os.getenv("RUN_PASSWORD", "")
    if want and not hmac.compare_digest((given or "").encode(), want.encode()):
        raise HTTPException(401, "Wrong password")


def sweep_stale(d: DB) -> None:
    """A run nobody drives any more (all pages closed for hours) is ended here."""
    for r in d.all("SELECT id, status, heartbeat FROM runs WHERE status IN ('queued','running','finishing')"):
        beat = _parse(r["heartbeat"])
        limit = {"finishing": STALE_FINISHING, "queued": STALE_QUEUED}.get(r["status"], STALE_RUNNING)
        if beat and now() - beat > limit:
            why = {"finishing": "finishing did not complete", "queued": "the run never started"}.get(
                r["status"], "stopped: no open page continued the run" if RUNNER == "batch"
                else "the run stopped responding (server restarted?)")
            d.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                      (now().isoformat(timespec="seconds"), why, r["id"]))


# -- pages ---------------------------------------------------------------------------
@app.get("/")
def index():                       # Vercel serves public/ itself; this is for serve.py
    return FileResponse(ROOT / "public" / "index.html")


# -- jobs ----------------------------------------------------------------------------
@app.get("/api/jobs")
def jobs(scope: str = Query("open", pattern="^(open|closed|all)$")):
    d = db()
    try:
        cutoff = (utc_today() - timedelta(days=CLOSED_DAYS)).isoformat()
        where = {"open": "status='open'", "closed": "status='closed' AND closed_on >= ?",
                 "all": "(status='open' OR closed_on >= ?)"}[scope]
        params = () if scope == "open" else (cutoff,)
        if REMOTE_ONLY:
            where += " AND remote_type='Remote'"
        rows = d.all(f"SELECT {', '.join(LIST_COLS)} FROM jobs WHERE duplicate=0 AND category != 'filtered' AND {where} "
                     f"ORDER BY posted_date DESC LIMIT 8000", params)
        for r in rows:
            if r["country"] and len(r["country"]) > 200:
                r["country"] = r["country"][:200] + "..."
        latest = d.one("SELECT id FROM runs WHERE started_at IS NOT NULL ORDER BY id DESC LIMIT 1")
        return {"jobs": rows, "latest_run_id": latest["id"] if latest else None, "today": utc_today().isoformat()}
    finally:
        d.close()


@app.get("/api/job")
def job(id: str):
    d = db()
    try:
        row = d.one("SELECT * FROM jobs WHERE identity=?", (id,))
    finally:
        d.close()
    if not row:
        raise HTTPException(404, "Job not found")
    return row


@app.get("/api/search")
def search(q: str = Query(..., min_length=2, max_length=100)):
    """Identities of jobs whose title, company or description contain q (the table filters on these)."""
    like = "%" + q.lower().replace("\\", "").replace("%", "").replace("_", " ") + "%"
    d = db()
    try:
        rows = d.all("SELECT identity FROM jobs WHERE duplicate=0 AND (LOWER(title) LIKE ? OR LOWER(company) LIKE ? "
                     "OR LOWER(COALESCE(description, '')) LIKE ? OR LOWER(COALESCE(tools, '')) LIKE ?) LIMIT 10000",
                     (like, like, like, like))
    finally:
        d.close()
    return {"ids": [r["identity"] for r in rows]}


# -- runs ----------------------------------------------------------------------------
class RunRequest(BaseModel):
    mode: str = Field("full", pattern="^(full|quick|feeds)$")
    max_age: int = Field(30, ge=1, le=60)
    password: str | None = None


class CancelRequest(BaseModel):
    password: str | None = None


ACTIVE = ("queued", "running", "finishing")


@app.get("/api/config")
def get_config():
    return {"password_required": bool(os.getenv("RUN_PASSWORD")), "runner": RUNNER}


@app.get("/api/runs/current")
def current_run():
    d = db()
    try:
        sweep_stale(d)
        row = d.one("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    finally:
        d.close()
    return {"run": row, "active": bool(row and row["status"] in ACTIVE)}


@app.get("/api/runs")
def runs():
    d = db()
    try:
        sweep_stale(d)
        return {"runs": d.all("SELECT * FROM runs ORDER BY id DESC LIMIT 50")}
    finally:
        d.close()


@app.post("/api/runs")
def start_run(req: RunRequest):
    check_password(req.password)
    d = db()
    try:
        sweep_stale(d)
        if d.one("SELECT id FROM runs WHERE status IN ('queued','running','finishing')"):
            raise HTTPException(409, "A run is already in progress")
        if RUNNER == "batch":
            return {"run_id": batch.create_run(d, req.mode, req.max_age)}
        ts = now().isoformat(timespec="seconds")
        run_id = d.one("INSERT INTO runs (created_at, heartbeat, status, mode, max_age, trigger) "
                       "VALUES (?,?,?,?,?,?) RETURNING id", (ts, ts, "queued", req.mode, req.max_age, "website"))["id"]
        try:
            _start_process(run_id, req.mode, req.max_age)
        except Exception as e:
            msg = f"could not start the run: {e}"[:300]
            d.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?", (ts, msg, run_id))
            raise HTTPException(502, msg)
        return {"run_id": run_id}
    finally:
        d.close()


def _start_process(run_id: int, mode: str, max_age: int) -> None:
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    log = open(out / f"web_run_{run_id}.log", "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([sys.executable, "run.py", "--run-id", str(run_id), "--mode", mode, "--max-age", str(max_age),
                      "--trigger", "website", "--quiet"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                     creationflags=flags, env={**os.environ, "PYTHONUNBUFFERED": "1"})


@app.post("/api/runs/{run_id}/step")
async def run_step(run_id: int):
    """Scrape the next slice of a running run (called repeatedly by the open page)."""
    d = db()
    try:
        run = await batch.step(d, run_id, STEP_SECONDS)
    finally:
        d.close()
    if not run:
        raise HTTPException(404, "Run not found")
    return {"run": run, "active": run["status"] in ACTIVE}


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: int, req: CancelRequest):
    check_password(req.password)
    d = db()
    try:
        row = d.one("SELECT status FROM runs WHERE id=?", (run_id,))
        if not row:
            raise HTTPException(404, "Run not found")
        if RUNNER == "batch":
            await batch.cancel(d, run_id)
        elif row["status"] == "queued":
            d.execute("UPDATE runs SET status='cancelled', cancel_requested=1, finished_at=? WHERE id=?",
                      (now().isoformat(timespec="seconds"), run_id))
        elif row["status"] == "running":
            d.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (run_id,))   # run.py stops within ~10 s
        return {"status": d.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"]}
    finally:
        d.close()


# -- boards --------------------------------------------------------------------------
@app.get("/api/boards")
def boards():
    d = db()
    try:
        return {"boards": d.all("SELECT key, company, ats, token, careers_url, last_status, last_error, jobs_total, "
                                "qa_jobs, kept, last_scanned, last_qa_date, seconds FROM boards "
                                "WHERE ats IS NOT NULL ORDER BY company")}
    finally:
        d.close()
