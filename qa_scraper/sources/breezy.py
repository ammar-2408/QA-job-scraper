"""Breezy HR public job list (no key).

  list:   GET https://{slug}.breezy.hr/json
  detail: the public posting page (server-rendered HTML, description in .description)
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "breezy"


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(f"https://{board.token}.breezy.hr/json")
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        title = (j.get("name") or "").strip()
        if not title:
            continue
        locs = j.get("locations") or ([j["location"]] if j.get("location") else [])
        names = [l.get("name") for l in locs if l.get("name")]
        countries = [((l.get("country") or {}).get("name") or "") for l in locs]
        remote = any(l.get("is_remote") for l in locs)
        jobs.append(Job(
            title=title,
            company=((j.get("company") or {}).get("name") or board.company),
            job_url=j.get("url") or "",
            source=ATS, board=board.key, external_id=str(j.get("id") or ""),
            location="; ".join(dict.fromkeys(names)),
            country="; ".join(dict.fromkeys(c for c in countries if c)),
            remote_type="Remote" if remote else "",
            salary=(j.get("salary") or "").strip(),
            posted_date=iso_date(j.get("published_date")), date_source="source",
            detail_ref={"url": j.get("url") or ""},
        ))
    return jobs


async def fill_detail(http, job: Job) -> None:
    if not job.detail_ref.get("url"):
        return
    page = await http.get_text(job.detail_ref["url"])
    if not page:
        return
    node = BeautifulSoup(page, "lxml").select_one(".description")
    if node:
        job.description = html_to_text(str(node))
