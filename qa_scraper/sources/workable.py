"""Workable public widget API (no key).

  GET https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true

Returns every open job with full HTML description and `published_on`. A role open in
several cities comes back once per city with the same shortcode; those are merged.
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "workable"
API = "https://apply.workable.com/api/v1/widget/accounts/{token}?details=true"


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(API.format(token=board.token))
    if data is None or "jobs" not in data:
        return None
    merged: dict[str, Job] = {}
    for j in data.get("jobs") or []:
        title = " ".join((j.get("title") or "").split())
        if not title:
            continue
        key = j.get("shortcode") or j.get("shortlink") or j.get("url") or title
        loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        if key in merged:
            job = merged[key]
            if loc and loc not in job.location:
                job.location = f"{job.location}; {loc}" if job.location else loc
            if j.get("country") and j["country"] not in job.country:
                job.country = f"{job.country}; {j['country']}" if job.country else j["country"]
            continue
        merged[key] = Job(
            title=title,
            company=data.get("name") or board.company,
            job_url=j.get("shortlink") or j.get("url") or "",
            source=ATS, board=board.key, external_id=j.get("shortcode") or "",
            location=loc, country=j.get("country") or "",
            remote_type="Remote" if j.get("telecommuting") else "",
            posted_date=iso_date(j.get("published_on") or j.get("created_at")), date_source="source",
            description=html_to_text(j.get("description") or ""),
        )
    return list(merged.values())
