"""Remote OK public API: https://remoteok.com/api (latest postings; first element is a legal notice)."""
from __future__ import annotations

from ..models import Job
from ..text import html_to_text, iso_date

NAME = "remoteok"


async def fetch(http, max_age: int) -> list[Job] | None:
    data = await http.get_json("https://remoteok.com/api")
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        lo, hi = j.get("salary_min"), j.get("salary_max")
        jobs.append(Job(
            title=j["position"].strip(), company=(j.get("company") or "").strip(),
            job_url=j.get("url") or "", apply_url=j.get("apply_url") or "",
            source=NAME, source_kind="aggregator", board=NAME, external_id=str(j.get("id") or ""),
            location=j.get("location") or "", remote_type="Remote",
            salary=f"USD {lo}-{hi} per year" if lo and hi else "",
            posted_date=iso_date(j.get("date") or j.get("epoch")), date_source="source",
            description=html_to_text(j.get("description") or ""),
        ))
    return jobs
