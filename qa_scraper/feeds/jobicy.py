"""Jobicy public API: https://jobicy.com/api/v2/remote-jobs (latest 100 + testing/tester tags)."""
from __future__ import annotations

from ..models import Job
from ..text import html_to_text, iso_date

NAME = "jobicy"
CALLS = [{"count": 100}, {"count": 100, "tag": "testing"}, {"count": 100, "tag": "tester"},
         {"count": 100, "tag": "quality assurance"}]


async def fetch(http, max_age: int) -> list[Job] | None:
    seen: dict[str, Job] = {}
    any_ok = False
    for params in CALLS:
        data = await http.get_json("https://jobicy.com/api/v2/remote-jobs", params=params)
        if not data or "jobs" not in data:
            continue
        any_ok = True
        for j in data["jobs"]:
            jid = str(j.get("id") or "")
            if not jid or jid in seen:
                continue
            lo, hi = j.get("salaryMin"), j.get("salaryMax")
            seen[jid] = Job(
                title=(j.get("jobTitle") or "").strip(), company=(j.get("companyName") or "").strip(),
                job_url=j.get("url") or "", source=NAME, source_kind="aggregator", board=NAME, external_id=jid,
                location=j.get("jobGeo") or "", remote_type="Remote",
                salary=f"{j.get('salaryCurrency') or ''} {lo}-{hi} {j.get('salaryPeriod') or ''}".strip() if lo and hi else "",
                posted_date=iso_date(j.get("pubDate")), date_source="source",
                description=html_to_text(j.get("jobDescription") or j.get("jobExcerpt") or ""),
            )
    return list(seen.values()) if any_ok else None
