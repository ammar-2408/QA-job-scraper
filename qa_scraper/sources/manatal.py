"""Manatal public careers-page API (no key).

  GET https://www.careers-page.com/api/v1.0/c/{slug}/jobs/?page=N

No posted date is published, so freshness comes from first-seen tracking (store.py).
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text

ATS = "manatal"
MAX_PAGES = 10


async def list_jobs(http, board: Board) -> list[Job] | None:
    url = f"https://www.careers-page.com/api/v1.0/c/{board.token}/jobs/"
    jobs: list[Job] = []
    any_ok = False
    for page in range(1, MAX_PAGES + 1):
        data = await http.get_json(url, params={"page": page})
        if not isinstance(data, dict) or "results" not in data:
            break
        any_ok = True
        for j in data["results"]:
            title = (j.get("position_name") or "").strip()
            if not title:
                continue
            jobs.append(Job(
                title=title, company=board.company,
                job_url=f"https://www.careers-page.com/{board.token}/job/{j.get('hash')}",
                source=ATS, board=board.key, external_id=str(j.get("id") or ""),
                location=j.get("location_display") or "", country=j.get("country") or "",
                description=html_to_text(j.get("description") or ""),
            ))
        if not data.get("next"):
            break
    return jobs if any_ok else None
