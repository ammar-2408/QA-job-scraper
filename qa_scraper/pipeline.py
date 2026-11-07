"""Run orchestration: boards -> jobs -> QA filter -> freshness -> details ->
classify -> enrich -> legitimacy -> dedupe."""
from __future__ import annotations

import asyncio
import csv
import time
from collections import Counter
from dataclasses import dataclass, field

from . import config, sources
from .filters import enrich, freshness, legitimacy, qa_match
from .http import Http
from .models import Board, Job


@dataclass
class BoardResult:
    board: Board
    ok: bool = False
    total_jobs: int = 0
    qa_jobs: int = 0
    kept: int = 0
    error: str = ""
    seconds: float = 0.0
    seen: list[Job] = field(default_factory=list, repr=False)     # every QA-titled posting on the board
    results: list[Job] = field(default_factory=list, repr=False)  # kept + undated + flagged
    saved: bool = False                                           # written to the database


@dataclass
class RunResult:
    kept: list[Job] = field(default_factory=list)        # QA + fresh + legitimate
    undated: list[Job] = field(default_factory=list)     # QA + legitimate, no posted date
    flagged: list[Job] = field(default_factory=list)     # QA + fresh, failed legitimacy
    boards: list[BoardResult] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    duplicates_merged: int = 0
    seconds: float = 0.0
    store: object = None                                  # store.Store / NullStore
    cancelled: bool = False
    timed_out: bool = False
    new_jobs: int = 0
    closed_jobs: int = 0


def load_boards(path=None) -> list[Board]:
    path = path or config.BOARDS_CSV
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not (row.get("ats") and row.get("token")):
                continue
            out.append(Board(company=row.get("company", "").strip(), ats=row["ats"].strip().lower(),
                             token=row["token"].strip(), host=(row.get("host") or "").strip(),
                             site=(row.get("site") or "").strip(),
                             careers_url=(row.get("careers_url") or "").strip()))
    return out


async def _process_job(http, src, job: Job, max_age: int, res: RunResult, br: BoardResult,
                       keep_all_titles: bool, board_known: bool = False) -> None:
    tier = qa_match.title_candidate(job.title)
    if not tier and not keep_all_titles:
        res.counts["not_qa_title"] += 1
        return
    prior_first_seen = res.store.first_seen(job.identity())
    res.store.record(job)               # every QA-titled job, whatever its age
    br.seen.append(job)
    # Level: senior / lead / manager titles are out (cheap, before any detail request).
    if config.EXCLUDE_SENIOR and enrich.too_senior_title(job.title) and not keep_all_titles:
        res.counts["too_senior"] += 1
        return
    # Remote only: the source already says hybrid / on-site -> stop here (saves detail requests).
    if config.REMOTE_ONLY and job.remote_type in ("Hybrid", "Onsite") and not keep_all_titles:
        res.counts["not_remote"] += 1
        return
    # Open job sites re-date ("refresh") old postings: if we saw the job earlier, that date wins.
    if job.source_kind == "aggregator" and prior_first_seen and job.posted_date and prior_first_seen < job.posted_date:
        job.posted_date, job.date_source = prior_first_seen, "first_seen"
    freshness.stamp(job)
    if job.days_old is not None and job.days_old > max_age:
        res.counts["too_old"] += 1
        return
    # Detail page: full description, and for some systems (BambooHR) the only posted date.
    if src is not None and hasattr(src, "fill_detail") and (not job.description or job.days_old is None):
        await src.fill_detail(http, job)
        freshness.stamp(job)
        if job.days_old is not None and job.days_old > max_age:
            res.counts["too_old"] += 1
            return
    # No date from the source at all: fall back to first-seen tracking.
    if job.days_old is None:
        if prior_first_seen:
            job.posted_date, job.date_source = prior_first_seen, "first_seen"
        elif board_known:
            job.posted_date, job.date_source = res.store.today, "first_seen"
        freshness.stamp(job)
        if job.days_old is not None and job.days_old > max_age:
            res.counts["too_old"] += 1
            return
    is_qa, why = qa_match.classify(job.title, job.description)
    if not is_qa and not keep_all_titles:
        res.counts["rejected_by_description"] += 1
        return
    job.qa_match = why or "all titles mode"
    enrich.enrich(job)
    if config.REMOTE_ONLY and job.remote_type != "Remote" and not keep_all_titles:
        res.counts["not_remote"] += 1
        return
    years = enrich.min_years(job.experience)
    if config.EXCLUDE_SENIOR and years is not None and years > config.MAX_EXPERIENCE_YEARS and not keep_all_titles:
        res.counts["too_senior"] += 1
        return
    br.qa_jobs += 1
    legitimacy.assess(job)
    if not legitimacy.is_legit(job):
        job.category = "flagged"
        res.flagged.append(job)
        res.counts["flagged"] += 1
    elif job.days_old is None:
        job.category = "undated"
        res.undated.append(job)
        res.counts["undated"] += 1
    else:
        job.category = "kept"
        res.kept.append(job)
        br.kept += 1
        res.counts["kept"] += 1
    br.results.append(job)


async def _scrape_board(http: Http, board: Board, max_age: int, res: RunResult,
                        keep_all_titles: bool, progress) -> None:
    br = BoardResult(board=board)
    res.boards.append(br)
    t0 = time.time()
    src = sources.get(board.ats)
    if src is None:
        br.error = f"no source for ats '{board.ats}'"
    else:
        try:
            jobs = await src.list_jobs(http, board)
            if jobs is None:
                br.error = "board unreachable or invalid"
            else:
                br.ok = True
                br.total_jobs = len(jobs)
                res.counts["jobs_seen"] += len(jobs)
                known = res.store.board_known_before_today(board.key)
                await asyncio.gather(*(_process_job(http, src, j, max_age, res, br, keep_all_titles, known)
                                       for j in jobs))
                res.store.mark_board(board.key)
        except Exception as e:  # one broken board must never stop the run
            br.ok, br.error = False, f"{type(e).__name__}: {e}"[:300]
    br.seconds = round(time.time() - t0, 1)
    await _save(res, br)
    progress(br)


async def _save(res: RunResult, br: BoardResult) -> None:
    try:
        await res.store.board_done(br)
    except Exception as e:      # the scrape goes on; the problem shows in the counts
        res.counts["db_errors"] += 1
        if res.counts["db_errors"] <= 5:
            print(f"database write failed for {br.board.key}: {type(e).__name__}: {e}"[:300], flush=True)


async def _scrape_feed(http: Http, feed, max_age: int, res: RunResult, progress) -> None:
    board = Board(company=feed.NAME, ats="feed", token=feed.NAME)
    br = BoardResult(board=board)
    res.boards.append(br)
    t0 = time.time()
    try:
        jobs = await feed.fetch(http, max_age)
        if jobs is None:
            br.error = "site unreachable"
        else:
            br.ok = True
            br.total_jobs = len(jobs)
            res.counts["jobs_seen"] += len(jobs)
            known = res.store.board_known_before_today(board.key)
            await asyncio.gather(*(_process_job(http, None, j, max_age, res, br, False, known) for j in jobs))
            res.store.mark_board(board.key)
    except Exception as e:
        br.ok, br.error = False, f"{type(e).__name__}: {e}"[:300]
    br.seconds = round(time.time() - t0, 1)
    await _save(res, br)
    progress(br)


def _norm(s: str) -> str:
    import re
    s = re.sub(r"\b(inc|llc|ltd|gmbh|corp|co|plc|sa|bv|ag)\b\.?", "", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _drop_aggregator_copies(jobs: list[Job]) -> tuple[list[Job], int]:
    """An open-site posting whose company + title also exists on that company's own
    board is the same job: keep the company-board copy (more trusted, exact data)."""
    ats_keys = {(_norm(j.company), _norm(j.title)) for j in jobs if j.source_kind == "company_ats"}
    kept = [j for j in jobs if j.source_kind == "company_ats" or (_norm(j.company), _norm(j.title)) not in ats_keys]
    return kept, len(jobs) - len(kept)


def _dedupe(jobs: list[Job]) -> tuple[list[Job], int]:
    """Same company + title + location from two sources -> keep the most trusted,
    then the one with the longer description."""
    rank = {"company_ats": 0, "aggregator_verified": 1, "flagged": 2}
    best: dict[str, Job] = {}
    seen_ids: set[str] = set()
    merged = 0
    for j in jobs:
        if j.identity() in seen_ids:
            merged += 1
            continue
        seen_ids.add(j.identity())
        k = j.dedupe_key()
        cur = best.get(k)
        if cur is None:
            best[k] = j
            continue
        merged += 1
        if (rank.get(j.trust, 3), -len(j.description)) < (rank.get(cur.trust, 3), -len(cur.description)):
            best[k] = j
    return list(best.values()), merged


async def run(boards: list[Board], max_age: int | None = None, keep_all_titles: bool = False,
              verbose: bool = True, feeds: list | None = None, store=None, batch: bool = False,
              deadline: float | None = None) -> RunResult:
    """Scrape `boards` (company job boards) and `feeds` (open job-site modules).

    batch=True: one slice of a larger run (the website's step-by-step runs): the run
    row is neither started nor finished here. `deadline` (time.time() value): boards
    still unfinished then are stopped and reported as timed out (res.timed_out)."""
    max_age = config.MAX_AGE_DAYS if max_age is None else max_age
    feeds = feeds or []
    res = RunResult()
    from .store import NullStore
    res.store = store if store is not None else NullStore()
    t0 = time.time()
    done = [0]
    total = len(boards) + len(feeds)

    def progress(br: BoardResult):
        done[0] += 1
        if verbose:
            status = f"{br.total_jobs} jobs, {br.qa_jobs} QA, {br.kept} kept" if br.ok else f"FAILED ({br.error})"
            line = f"[{done[0]}/{total}] {br.board.ats}:{br.board.token} - {status}"
            print(line.encode("ascii", "replace").decode(), flush=True)

    if not batch:
        await res.store.start(max_age, total)
    async with Http() as http:
        gate = asyncio.Semaphore(config.BOARD_CONCURRENCY)    # boards in progress at once (memory)

        async def gated(b):
            async with gate:
                await _scrape_board(http, b, max_age, res, keep_all_titles, progress)
        pending = {asyncio.create_task(gated(b)) for b in boards}
        pending |= {asyncio.create_task(_scrape_feed(http, f, max_age, res, progress)) for f in feeds}
        while pending:
            wait = 5 if deadline is None else max(0.1, min(5, deadline - time.time()))
            _, pending = await asyncio.wait(pending, timeout=wait)
            if pending and deadline is not None and time.time() >= deadline:
                res.timed_out = True
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                break
            if pending and await res.store.cancel_requested():
                res.cancelled = True
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if verbose:
                    print("Run cancelled.", flush=True)
                break
        res.counts["http_errors"] = len(http.errors)

        res.kept, m0 = _drop_aggregator_copies(res.kept)
        res.kept, m1 = _dedupe(res.kept)
        res.undated, m2 = _dedupe(res.undated)
        res.duplicates_merged = m0 + m1 + m2
        res.kept.sort(key=lambda j: (j.days_old if j.days_old is not None else 99, j.company.lower(), j.title.lower()))
        res.seconds = round(time.time() - t0, 1)
        if not batch:
            await res.store.finish(res, http, status="cancelled" if res.cancelled else "done")
    res.store.close()
    return res
