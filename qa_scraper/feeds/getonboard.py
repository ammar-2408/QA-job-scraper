"""Get on Board (Latin America tech jobs) public API, no key:

  https://www.getonbrd.com/api/v0/categories/sysadmin-devops-qa/jobs?per_page=100&page=N&expand=["company"]
  https://www.getonbrd.com/api/v0/search/jobs?query=<term>&per_page=100&page=N&expand=["company"]

robots.txt allows search use (Content-Signal: search=yes). Each job states its remote
modality: fully_remote / remote_local (remote within its countries) / hybrid / no_remote.
"""
from __future__ import annotations

import asyncio

from ..models import Job
from ..text import html_to_text, iso_date

NAME = "getonboard"
API = "https://www.getonbrd.com/api/v0"
QUERIES = ["qa", "tester", "testing", "quality assurance", "automatización", "analista qa", "sdet"]
MAX_PAGES = 5
_MODALITY = {"fully_remote": "Remote", "remote_local": "Remote", "hybrid": "Hybrid", "no_remote": "Onsite"}


def _job(item: dict) -> Job | None:
    a = item.get("attributes") or {}
    title = (a.get("title") or "").strip()
    url = (item.get("links") or {}).get("public_url") or ""
    if not title or not url:
        return None
    company = (((a.get("company") or {}).get("data") or {}).get("attributes") or {}).get("name") or ""
    countries = [c for c in (a.get("countries") or []) if c]
    lo, hi = a.get("min_salary"), a.get("max_salary")
    desc = " ".join(html_to_text(a.get(k) or "") for k in ("description", "functions", "desirable", "projects"))
    return Job(title=title, company=company.strip(), job_url=url, source=NAME, source_kind="aggregator",
               board=NAME, external_id=str(item.get("id") or url), location="; ".join(countries),
               country="; ".join(countries), remote_type=_MODALITY.get(a.get("remote_modality") or "", ""),
               salary=f"USD {lo}-{hi} per month" if lo and hi else "",
               posted_date=iso_date(a.get("published_at")), date_source="source", description=desc.strip())


async def fetch(http, max_age: int) -> list[Job] | None:
    seen: dict[str, Job] = {}
    ok = []

    async def pages(path: str, params: dict) -> None:
        for page in range(1, MAX_PAGES + 1):
            data = await http.get_json(f"{API}/{path}", params={**params, "per_page": 100, "page": page,
                                                                "expand": '["company"]'})
            if not data or "data" not in data:
                return
            ok.append(True)
            for item in data["data"]:
                j = _job(item)
                if j and j.job_url not in seen:
                    seen[j.job_url] = j
            if page >= ((data.get("meta") or {}).get("total_pages") or 0):
                return

    await asyncio.gather(pages("categories/sysadmin-devops-qa/jobs", {}),
                         *(pages("search/jobs", {"query": q}) for q in QUERIES))
    return list(seen.values()) if ok else None
