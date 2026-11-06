"""BambooHR public careers JSON (no key).

  list:   GET https://{slug}.bamboohr.com/careers/list
  detail: GET https://{slug}.bamboohr.com/careers/{id}/detail

The listing has no posted date; the detail has `datePosted`, the description and
compensation. A slug that is not a BambooHR customer returns an HTML marketing page,
which list_jobs treats as "no board".
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "bamboohr"


def _loc(o: dict) -> tuple[str, str]:
    ats = o.get("atsLocation") or {}
    loc = o.get("location") or {}
    city = loc.get("city") or ats.get("city")
    state = loc.get("state") or ats.get("state") or ats.get("province")
    country = ats.get("country") or loc.get("addressCountry") or ""
    return ", ".join(x for x in (city, state, country) if x), country


async def list_jobs(http, board: Board) -> list[Job] | None:
    base = f"https://{board.token}.bamboohr.com/careers"
    data = await http.get_json(f"{base}/list")
    if not isinstance(data, dict) or "result" not in data:
        return None
    jobs = []
    for o in data.get("result") or []:
        title = (o.get("jobOpeningName") or "").strip()
        jid = str(o.get("id") or "")
        if not title or not jid:
            continue
        location, country = _loc(o)
        jobs.append(Job(
            title=title, company=board.company,
            job_url=f"{base}/{jid}", source=ATS, board=board.key, external_id=jid,
            location=location, country=country,
            remote_type="Remote" if o.get("isRemote") or str(o.get("locationType")) == "2" else "",
            detail_ref={"url": f"{base}/{jid}/detail"},
        ))
    return jobs


async def fill_detail(http, job: Job) -> None:
    data = await http.get_json(job.detail_ref["url"])
    jo = ((data or {}).get("result") or {}).get("jobOpening") or {}
    if not jo:
        return
    job.description = html_to_text(jo.get("description") or "")
    job.posted_date = iso_date(jo.get("datePosted"))
    job.date_source = "source" if job.posted_date else ""
    if jo.get("compensation"):
        job.salary = jo["compensation"]
    if jo.get("jobOpeningShareUrl"):
        job.job_url = jo["jobOpeningShareUrl"]
