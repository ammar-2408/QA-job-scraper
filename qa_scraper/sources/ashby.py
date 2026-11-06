"""Ashby public Posting API (no key).

  GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true

Returns every listed posting with full description, `publishedAt`,
workplaceType and a structured address (incl. country).
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import iso_date

ATS = "ashby"
API = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
_WORKPLACE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "on-site": "Onsite"}


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(API.format(token=board.token))
    if data is None or "jobs" not in data:
        return None
    jobs = []
    for j in data.get("jobs") or []:
        title = (j.get("title") or "").strip()
        if not title or j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""]
        locs += [(s.get("location") or "") for s in j.get("secondaryLocations") or []]
        addr = ((j.get("address") or {}).get("postalAddress") or {})
        comp = j.get("compensation") or {}
        remote = _WORKPLACE.get((j.get("workplaceType") or "").lower(), "")
        if not remote and j.get("isRemote"):
            remote = "Remote"
        jobs.append(Job(
            title=title,
            company=board.company,
            job_url=j.get("jobUrl") or "",
            apply_url=j.get("applyUrl") or "",
            source=ATS, board=board.key,
            external_id=str(j.get("id") or ""),
            location="; ".join(dict.fromkeys(l.strip() for l in locs if l and l.strip())),
            country=addr.get("addressCountry") or "",
            remote_type=remote,
            salary=(comp.get("scrapeableCompensationSalarySummary")
                    or comp.get("compensationTierSummary") or "").strip(),
            posted_date=iso_date(j.get("publishedAt")),
            date_source="source",
            description=(j.get("descriptionPlain") or "").strip(),
        ))
    return jobs
