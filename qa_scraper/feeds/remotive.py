"""Remotive public API: https://remotive.com/api/remote-jobs (full feed, filtered locally)."""
from __future__ import annotations

from ..models import Job
from ..text import html_to_text, iso_date

NAME = "remotive"


async def fetch(http, max_age: int) -> list[Job] | None:
    data = await http.get_json("https://remotive.com/api/remote-jobs")
    if not data or "jobs" not in data:
        return None
    return [Job(
        title=(j.get("title") or "").strip(),
        company=(j.get("company_name") or "").strip(),
        job_url=j.get("url") or "", source=NAME, source_kind="aggregator", board=NAME,
        external_id=str(j.get("id") or ""),
        location=j.get("candidate_required_location") or "", remote_type="Remote",
        salary=(j.get("salary") or "").strip(),
        posted_date=iso_date(j.get("publication_date")), date_source="source",
        description=html_to_text(j.get("description") or ""),
    ) for j in data["jobs"] if j.get("title")]
