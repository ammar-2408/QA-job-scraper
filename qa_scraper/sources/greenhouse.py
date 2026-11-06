"""Greenhouse public Job Board API (no key).

  list:   GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs
  detail: GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}

The light listing already carries title, location and `first_published`, so the
full description is only fetched for jobs that survive the QA + freshness checks.
`first_published` is used for freshness, not `updated_at` (Greenhouse bumps
updated_at on any edit, which would make old postings look new).
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(API.format(token=board.token))
    if data is None:
        return None
    jobs = []
    for j in data.get("jobs") or []:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        jobs.append(Job(
            title=title,
            company=j.get("company_name") or board.company,
            job_url=j.get("absolute_url") or "",
            source=ATS, board=board.key,
            external_id=str(j.get("id") or ""),
            location=((j.get("location") or {}).get("name") or "").strip(),
            posted_date=iso_date(j.get("first_published") or j.get("updated_at")),
            date_source="source",
            detail_ref={"url": f"{API.format(token=board.token)}/{j.get('id')}"},
        ))
    return jobs


async def fill_detail(http, job: Job) -> None:
    data = await http.get_json(job.detail_ref["url"])
    if not data:
        return
    job.description = html_to_text(data.get("content") or "")
    offices = [o.get("location") or o.get("name") for o in data.get("offices") or []]
    job.detail_ref["offices"] = [o for o in offices if o]
    for meta in data.get("metadata") or []:
        name = (meta.get("name") or "").lower()
        val = meta.get("value")
        if val and any(k in name for k in ("salary", "compensation", "pay range")):
            job.salary = val if isinstance(val, str) else str(val)
