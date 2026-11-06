"""Rippling ATS public job board API (no key).

  list:   GET https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs
  detail: GET https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs/{uuid}

The list has no date; the detail has createdOn, the description and companyName.
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "rippling"
API = "https://api.rippling.com/platform/api/ats/v1/board/{token}/jobs"


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(API.format(token=board.token))
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        title = " ".join((j.get("name") or "").split())
        uid = j.get("uuid") or ""
        if not title or not uid:
            continue
        loc = j.get("workLocation") or {}
        jobs.append(Job(
            title=title, company=board.company, job_url=j.get("url") or "",
            source=ATS, board=board.key, external_id=uid,
            location=loc.get("label") or "" if isinstance(loc, dict) else str(loc),
            detail_ref={"url": f"{API.format(token=board.token)}/{uid}"},
        ))
    return jobs


async def fill_detail(http, job: Job) -> None:
    d = await http.get_json(job.detail_ref["url"])
    if not d:
        return
    desc = d.get("description")
    if isinstance(desc, dict):
        job.description = "\n\n".join(html_to_text(v) for v in desc.values() if isinstance(v, str) and v)
    elif isinstance(desc, str):
        job.description = html_to_text(desc)
    job.posted_date = iso_date(d.get("createdOn"))
    job.date_source = "source" if job.posted_date else ""
    if d.get("companyName"):
        job.company = d["companyName"]
    locs = d.get("workLocations") or []
    if locs:
        job.location = "; ".join(str(l) for l in locs)
    pay = d.get("payRangeDetails") or []
    if pay and isinstance(pay[0], dict):
        p = pay[0]
        lo, hi = p.get("rangeStart"), p.get("rangeEnd")
        if lo or hi:
            job.salary = f"{p.get('currency') or ''} {lo or ''}-{hi or ''} {p.get('frequency') or ''}".strip()
