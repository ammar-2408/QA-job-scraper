"""Recruitee public Careers Site API (no key).

  GET https://{slug}.recruitee.com/api/offers/

Every published offer with HTML description + requirements, `published_at`,
city/country and remote/hybrid/on-site flags.
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "recruitee"


async def list_jobs(http, board: Board) -> list[Job] | None:
    host = board.host or f"{board.token}.recruitee.com"
    data = await http.get_json(f"https://{host}/api/offers/")
    if data is None or "offers" not in data:
        return None
    jobs = []
    for o in data.get("offers") or []:
        title = (o.get("title") or "").strip()
        if not title or (o.get("status") and o["status"] != "published"):
            continue
        locs = [l.get("name") or ", ".join(x for x in (l.get("city"), l.get("country")) if x)
                for l in o.get("locations") or []]
        location = "; ".join(dict.fromkeys(l for l in locs if l)) or o.get("location") or ""
        remote = "Remote" if o.get("remote") else ("Hybrid" if o.get("hybrid") else ("Onsite" if o.get("on_site") else ""))
        sal = o.get("salary") or {}
        salary = ""
        if sal.get("min") or sal.get("max"):
            salary = f"{sal.get('currency') or ''} {sal.get('min') or ''}-{sal.get('max') or ''} {sal.get('period') or ''}".strip()
        desc = html_to_text(o.get("description") or "")
        req = html_to_text(o.get("requirements") or "")
        jobs.append(Job(
            title=title,
            company=o.get("company_name") or board.company,
            job_url=o.get("careers_url") or "",
            apply_url=o.get("careers_apply_url") or "",
            source=ATS, board=board.key, external_id=str(o.get("id") or ""),
            location=location, country=o.get("country_code") or o.get("country") or "",
            remote_type=remote, salary=salary,
            posted_date=iso_date(o.get("published_at") or o.get("created_at")), date_source="source",
            description=f"{desc}\n\n{req}".strip(),
        ))
    return jobs
