"""Arbeitnow public API: https://www.arbeitnow.com/api/job-board-api?page=N

Newest first, so paging stops as soon as a page reaches postings older than the window.
"""
from __future__ import annotations

from ..models import Job
from ..text import days_between, html_to_text, iso_date

NAME = "arbeitnow"
MAX_PAGES = 10


async def fetch(http, max_age: int) -> list[Job] | None:
    jobs: list[Job] = []
    any_ok = False
    for page in range(1, MAX_PAGES + 1):
        data = await http.get_json("https://www.arbeitnow.com/api/job-board-api", params={"page": page})
        if not data or not data.get("data"):
            break
        any_ok = True
        oldest = 0
        for j in data["data"]:
            posted = iso_date(j.get("created_at"))
            oldest = max(oldest, days_between(posted) or 0)
            jobs.append(Job(
                title=(j.get("title") or "").strip(), company=(j.get("company_name") or "").strip(),
                job_url=j.get("url") or "", source=NAME, source_kind="aggregator", board=NAME,
                external_id=j.get("slug") or "", location=j.get("location") or "",
                remote_type="Remote" if j.get("remote") else "",
                posted_date=posted, date_source="source",
                description=html_to_text(j.get("description") or ""),
            ))
        if oldest > max_age or not (data.get("links") or {}).get("next"):
            break
    return jobs if any_ok else None
