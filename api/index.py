"""Website API (FastAPI). Runs on Vercel as one serverless function, or locally via serve.py.

Reads the database that the scraper writes (Postgres online, SQLite locally). The
scrape itself never runs here (Vercel stops functions after a few minutes): the Run
button asks GitHub Actions to start .github/workflows/scrape.yml, or, locally, starts
run.py in the background.

Environment:
  DATABASE_URL    Postgres connection string (unset -> data/jobs.db)
  RUN_PASSWORD    password for starting/cancelling runs (unset -> no password)
  GH_TOKEN        GitHub token allowed to start workflows on GH_REPO
  GH_REPO         default ammar-06/QA-job-scraper
  LOCAL_RUNNER=1  start run.py on this machine instead of GitHub Actions
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

import httpx  # noqa: E402
from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from qa_scraper.db import DB  # noqa: E402

GH_REPO = os.getenv("GH_REPO", "ammar-06/QA-job-scraper")
GH_WORKFLOW = os.getenv("GH_WORKFLOW", "scrape.yml")
GH_REF = os.getenv("GH_REF", "main")
STALE_RUNNING = timedelta(minutes=20)    # no heartbeat for this long -> the runner died
STALE_QUEUED = timedelta(minutes=15)     # GitHub never started the job
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


def runner() -> str:
    if os.getenv("LOCAL_RUNNER") == "1":
        return "local"
    return "github" if os.getenv("GH_TOKEN") else "none"


def check_password(given: str | None) -> None:
    want = os.getenv("RUN_PASSWORD", "")
    if want and not hmac.compare_digest((given or "").encode(), want.encode()):
        raise HTTPException(401, "Wrong password")


def sweep_stale(d: DB) -> None:
    """A run whose runner died can't report it; time it out here."""
    for r in d.all("SELECT id, status, created_at, heartbeat FROM runs WHERE status IN ('queued','running')"):
        if r["status"] == "running":
            beat = _parse(r["heartbeat"])
            if beat and now() - beat > STALE_RUNNING:
                d.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                          (now().isoformat(timespec="seconds"), "the runner stopped responding", r["id"]))
        else:
            made = _parse(r["created_at"])
            if made and now() - made > STALE_QUEUED:
                d.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?",
                          (now().isoformat(timespec="seconds"), "the run never started (GitHub Actions)", r["id"]))


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
        rows = d.all(f"SELECT {', '.join(LIST_COLS)} FROM jobs WHERE duplicate=0 AND {where} "
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
    max_age: int = Field(7, ge=1, le=60)
    password: str | None = None


class CancelRequest(BaseModel):
    password: str | None = None


@app.get("/api/config")
def get_config():
    return {"password_required": bool(os.getenv("RUN_PASSWORD")), "runner": runner()}


@app.get("/api/runs/current")
def current_run():
    d = db()
    try:
        sweep_stale(d)
        row = d.one("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    finally:
        d.close()
    return {"run": row, "active": bool(row and row["status"] in ("queued", "running"))}


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
    how = runner()
    if how == "none":
        raise HTTPException(503, "No runner configured (GH_TOKEN is not set)")
    d = db()
    try:
        sweep_stale(d)
        if d.one("SELECT id FROM runs WHERE status IN ('queued','running')"):
            raise HTTPException(409, "A run is already in progress")
        ts = now().isoformat(timespec="seconds")
        run_id = d.one("INSERT INTO runs (created_at, heartbeat, status, mode, max_age, trigger) "
                       "VALUES (?,?,?,?,?,?) RETURNING id", (ts, ts, "queued", req.mode, req.max_age, "website"))["id"]
        try:
            if how == "local":
                _start_local(run_id, req.mode, req.max_age)
            else:
                _dispatch_github(run_id, req.mode, req.max_age)
        except Exception as e:
            msg = f"could not start the run: {e}"[:300]
            d.execute("UPDATE runs SET status='failed', finished_at=?, error=? WHERE id=?", (ts, msg, run_id))
            raise HTTPException(502, msg)
        return {"run_id": run_id}
    finally:
        d.close()


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: int, req: CancelRequest):
    check_password(req.password)
    d = db()
    try:
        row = d.one("SELECT status, gh_run_id FROM runs WHERE id=?", (run_id,))
        if not row:
            raise HTTPException(404, "Run not found")
        if row["status"] not in ("queued", "running"):
            return {"status": row["status"]}
        d.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (run_id,))
        if row["status"] == "queued":       # not started yet: stop it right away
            d.execute("UPDATE runs SET status='cancelled', finished_at=? WHERE id=?",
                      (now().isoformat(timespec="seconds"), run_id))
            if row["gh_run_id"] and runner() == "github":
                _github("POST", f"/actions/runs/{row['gh_run_id']}/cancel")
            return {"status": "cancelled"}
        return {"status": "cancelling"}     # the scraper stops within ~10 s and saves what it has
    finally:
        d.close()


def _github(method: str, path: str, json=None) -> httpx.Response:
    return httpx.request(method, f"https://api.github.com/repos/{GH_REPO}{path}", json=json, timeout=20,
                         headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                                  "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                                  "User-Agent": "qa-job-scraper-web"})


def _dispatch_github(run_id: int, mode: str, max_age: int) -> None:
    r = _github("POST", f"/actions/workflows/{GH_WORKFLOW}/dispatches",
                {"ref": GH_REF, "inputs": {"run_id": str(run_id), "mode": mode, "max_age": str(max_age)}})
    if r.status_code not in (200, 204):
        raise RuntimeError(f"GitHub answered {r.status_code}: {r.text[:200]}")


def _start_local(run_id: int, mode: str, max_age: int) -> None:
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    log = open(ROOT / "output" / f"web_run_{run_id}.log", "w", encoding="utf-8")
    subprocess.Popen([sys.executable, "run.py", "--run-id", str(run_id), "--mode", mode, "--max-age", str(max_age),
                      "--trigger", "website", "--quiet"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                     creationflags=flags, env={**os.environ, "PYTHONUNBUFFERED": "1"})


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
