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
    br.qa_jobs += 1
    job.qa_match = why or "all titles mode"
    enrich.enrich(job)
    legitimacy.assess(job)
    if not legitimacy.is_legit(job):
        res.flagged.append(job)
        res.counts["flagged"] += 1
    elif job.days_old is None:
        res.undated.append(job)
        res.counts["undated"] += 1
    else:
        res.kept.append(job)
        br.kept += 1
        res.counts["kept"] += 1


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
            br.error = f"{type(e).__name__}: {e}"[:300]
    br.seconds = round(time.time() - t0, 1)
    progress(br)


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
        br.error = f"{type(e).__name__}: {e}"[:300]
    br.seconds = round(time.time() - t0, 1)
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
              verbose: bool = True, feeds: list | None = None, store=None) -> RunResult:
    """Scrape `boards` (company job boards) and `feeds` (open job-site modules)."""
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

    async with Http() as http:
        await asyncio.gather(*(_scrape_board(http, b, max_age, res, keep_all_titles, progress) for b in boards),
                             *(_scrape_feed(http, f, max_age, res, progress) for f in feeds))
        res.counts["http_errors"] = len(http.errors)
    res.store.close()

    res.kept, m0 = _drop_aggregator_copies(res.kept)
    res.kept, m1 = _dedupe(res.kept)
    res.undated, m2 = _dedupe(res.undated)
    res.duplicates_merged = m0 + m1 + m2
    res.kept.sort(key=lambda j: (j.days_old if j.days_old is not None else 99, j.company.lower(), j.title.lower()))
    res.seconds = round(time.time() - t0, 1)
    return res
