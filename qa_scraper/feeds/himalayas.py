"""Himalayas public search API: https://himalayas.app/jobs/api/search?q=<term>&page=N (20 per page)."""
from __future__ import annotations

import asyncio

from ..models import Job
from ..text import html_to_text, iso_date

NAME = "himalayas"
QUERIES = ["qa", "quality assurance", "qa engineer", "qa analyst", "qa tester", "tester", "software tester",
           "manual tester", "manual qa", "test automation", "automation tester", "qa automation", "sdet",
           "test engineer", "software test", "quality engineer", "mobile qa", "api testing", "game tester",
           "selenium", "playwright", "cypress", "appium", "performance testing"]
MAX_PAGES = 20


def _short(places: list[str], n: int = 4) -> str:
    if len(places) <= n:
        return "; ".join(places)
    return "; ".join(places[:n]) + f" (+{len(places) - n} more)"


async def fetch(http, max_age: int) -> list[Job] | None:
    seen: dict[str, Job] = {}
    ok = []

    async def one_query(q: str) -> None:
        for page in range(1, MAX_PAGES + 1):
            data = await http.get_json("https://himalayas.app/jobs/api/search", params={"q": q, "page": page})
            if not data or "jobs" not in data:
                break
            ok.append(True)
            for j in data["jobs"]:
                guid = j.get("guid") or j.get("applicationLink") or ""
                if not guid or guid in seen:
                    continue
                lo, hi, cur = j.get("minSalary"), j.get("maxSalary"), j.get("currency") or ""
                where = list(dict.fromkeys(j.get("locationRestrictions") or []))
                seen[guid] = Job(
                    title=(j.get("title") or "").strip(), company=(j.get("companyName") or "").strip(),
                    job_url=guid, apply_url=j.get("applicationLink") or "",
                    source=NAME, source_kind="aggregator", board=NAME, external_id=guid,
                    location=_short(where) or "Worldwide",
                    country="; ".join(where), remote_type="Remote",
                    salary=f"{cur} {lo}-{hi} {j.get('salaryPeriod') or ''}".strip() if lo and hi else "",
                    posted_date=iso_date(j.get("pubDate")), date_source="source",
                    description=html_to_text(j.get("description") or j.get("excerpt") or ""),
                )
            if len(data["jobs"]) < 20:
                break

    await asyncio.gather(*(one_query(q) for q in QUERIES))     # the HTTP client caps requests per host
    return list(seen.values()) if ok else None
