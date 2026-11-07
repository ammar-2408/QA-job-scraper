"""Workday public CXS JSON API (no key).

  list:   POST https://{host}/wday/cxs/{tenant}/{site}/jobs
          body {"appliedFacets": {}, "limit": 20, "offset": N, "searchText": "<term>"}
  detail: GET  https://{host}/wday/cxs/{tenant}/{site}{externalPath}

Large employers have thousands of postings, so instead of paging the whole board
we run Workday's own keyword search for each term in config.SEARCH_TERMS and merge
the results. The listing gives "Posted 3 Days Ago"-style dates, so old postings are
dropped before any detail request; the detail gives the exact date (startDate).

Board fields: token = tenant, host = e.g. nvidia.wd5.myworkdayjobs.com, site = e.g.
NVIDIAExternalCareerSite.
"""
from __future__ import annotations

import asyncio
import re

from .. import config
from ..filters import qa_match
from ..models import Board, Job
from ..text import html_to_text, iso_date, relative_date

ATS = "workday"
PAGE = 20
MAX_PAGES_PER_TERM = 5      # 100 results per search term is plenty for QA roles

_RAW_LOC = re.compile(r"^[A-Z]{2}\s*-\s*[A-Z]{2,3}\s*-\s*(.+)$")   # "US - CA - San Diego" -> "San Diego"


def _base(board: Board) -> str:
    return f"https://{board.host}/wday/cxs/{board.token}/{board.site}"


async def list_jobs(http, board: Board) -> list[Job] | None:
    if not (board.host and board.site):
        return None
    base = _base(board)
    seen: dict[str, Job] = {}
    ok = []

    async def one_term(term: str) -> None:
        for page in range(MAX_PAGES_PER_TERM):
            data = await http.post_json(f"{base}/jobs", {"appliedFacets": {}, "limit": PAGE,
                                                         "offset": page * PAGE, "searchText": term})
            if data is None:
                break
            ok.append(True)
            postings = data.get("jobPostings") or []
            # Results are ranked by relevance: a page without a single QA-looking title means
            # the rest of this search is unrelated too.
            if not any(qa_match.title_candidate(p.get("title") or "") for p in postings):
                break
            for p in postings:
                path = p.get("externalPath") or ""
                if not path or path in seen:
                    continue
                seen[path] = Job(
                    title=(p.get("title") or "").strip(),
                    company=board.company,
                    job_url=f"https://{board.host}/{board.site}{path}",
                    source=ATS, board=board.key,
                    external_id=f"{board.token}{path}",
                    location=(p.get("locationsText") or "").strip(),
                    posted_date=relative_date(p.get("postedOn") or ""),
                    date_source="source",
                    detail_ref={"url": f"{base}{path}"},
                )
            if len(postings) < PAGE:
                break

    await asyncio.gather(*(one_term(t) for t in config.SEARCH_TERMS))   # per-host limit still applies
    return list(seen.values()) if ok else None


def _clean_loc(loc: str) -> str:
    m = _RAW_LOC.match((loc or "").strip())
    return m.group(1).strip() if m else (loc or "").strip()


async def fill_detail(http, job: Job) -> None:
    data = await http.get_json(job.detail_ref["url"])
    info = (data or {}).get("jobPostingInfo") or {}
    if not info:
        return
    job.description = html_to_text(info.get("jobDescription") or "")
    locs = [info.get("location")] + list(info.get("additionalLocations") or [])
    locs = [_clean_loc(l) for l in locs if l]
    if locs:
        job.location = "; ".join(dict.fromkeys(locs))
    country = (info.get("country") or {}).get("descriptor") or ""
    if country:
        job.country = country
    if info.get("startDate"):
        job.posted_date = iso_date(info["startDate"])
    remote = (info.get("remoteType") or "").lower()
    if "remote" in remote:
        job.remote_type = "Remote"
    elif "hybrid" in remote:
        job.remote_type = "Hybrid"
    if info.get("externalUrl"):
        job.job_url = info["externalUrl"]
