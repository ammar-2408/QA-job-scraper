"""SmartRecruiters public Posting API (no key).

  list:   GET https://api.smartrecruiters.com/v1/companies/{id}/postings?q=<term>&limit=100&offset=N
  detail: GET https://api.smartrecruiters.com/v1/companies/{id}/postings/{postingId}

Some companies have 5,000+ postings, so the listing is fetched with server-side
keyword search (config.SEARCH_TERMS). `releasedDate` is used for freshness.
"""
from __future__ import annotations

from .. import config
from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "smartrecruiters"
API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
MAX_PAGES_PER_TERM = 3


def _location(loc: dict) -> tuple[str, str]:
    full = loc.get("fullLocation") or ", ".join(x for x in (loc.get("city"), loc.get("country", "").upper()) if x)
    remote = "Remote" if loc.get("remote") else ("Hybrid" if loc.get("hybrid") else "")
    return full, remote


async def list_jobs(http, board: Board) -> list[Job] | None:
    base = API.format(token=board.token)
    seen: dict[str, Job] = {}
    any_ok = False
    for term in config.SEARCH_TERMS:
        for page in range(MAX_PAGES_PER_TERM):
            data = await http.get_json(base, params={"q": term, "limit": 100, "offset": page * 100})
            if data is None:
                break
            any_ok = True
            content = data.get("content") or []
            for p in content:
                pid = str(p.get("id") or "")
                if not pid or pid in seen:
                    continue
                loc, remote = _location(p.get("location") or {})
                seen[pid] = Job(
                    title=(p.get("name") or "").strip(),
                    company=((p.get("company") or {}).get("name") or board.company),
                    job_url=f"https://jobs.smartrecruiters.com/{board.token}/{pid}",
                    source=ATS, board=board.key, external_id=pid,
                    location=loc, remote_type=remote,
                    country=((p.get("location") or {}).get("country") or "").upper(),
                    posted_date=iso_date(p.get("releasedDate")), date_source="source",
                    detail_ref={"url": f"{base}/{pid}"},
                )
            if len(content) < 100:
                break
    return list(seen.values()) if any_ok else None


async def fill_detail(http, job: Job) -> None:
    d = await http.get_json(job.detail_ref["url"])
    if not d:
        return
    sections = (d.get("jobAd") or {}).get("sections") or {}
    parts = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        sec = sections.get(key) or {}
        text = html_to_text(sec.get("text") or "")
        if text:
            parts.append(f"{sec.get('title') or ''}\n{text}".strip())
    job.description = "\n\n".join(parts)[: config.MAX_DESC]
    if d.get("postingUrl"):
        job.job_url = d["postingUrl"]
    if d.get("applyUrl"):
        job.apply_url = d["applyUrl"]
    comp = d.get("compensation") or {}
    if comp.get("min") or comp.get("max"):
        job.salary = f"{comp.get('currency', '')} {comp.get('min', '')}-{comp.get('max', '')} {comp.get('period', '')}".strip()
