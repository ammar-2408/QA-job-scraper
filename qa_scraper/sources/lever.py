"""Lever public Postings API (no key).

  GET https://api.lever.co/v0/postings/{company}?mode=json

One call returns every posting with its full description, `createdAt` (epoch ms),
workplaceType and an ISO country code. EU-hosted accounts live on api.eu.lever.co.
"""
from __future__ import annotations

import re

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "lever"
HOSTS = ("https://api.lever.co", "https://api.eu.lever.co")
_WORKPLACE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "on-site": "Onsite"}


def _description(j: dict) -> str:
    parts = [j.get("descriptionPlain") or html_to_text(j.get("description") or "")]
    for item in j.get("lists") or []:
        heading = (item.get("text") or "").strip()
        body = html_to_text(item.get("content") or "")
        parts.append(f"{heading}\n{body}".strip())
    parts.append(j.get("additionalPlain") or html_to_text(j.get("additional") or ""))
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _location(cats: dict) -> str:
    locs = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
    seen, out = set(), []
    for loc in locs:
        loc = re.sub(r"\s+", " ", str(loc or "")).strip(" /")
        if loc and loc.lower() not in seen:
            seen.add(loc.lower())
            out.append(loc)
    return "; ".join(out)


async def list_jobs(http, board: Board) -> list[Job] | None:
    hosts = [board.host] if board.host else HOSTS
    data = None
    for host in hosts:
        data = await http.get_json(f"{host}/v0/postings/{board.token}?mode=json")
        if isinstance(data, list):
            break
    if not isinstance(data, list):
        return None
    jobs = []
    for j in data:
        title = (j.get("text") or "").strip()
        if not title:
            continue
        cats = j.get("categories") or {}
        sr = j.get("salaryRange") or {}
        salary = ""
        if sr.get("min") or sr.get("max"):
            salary = f"{sr.get('currency', '')} {sr.get('min', '')}-{sr.get('max', '')} {sr.get('interval', '')}".strip()
        jobs.append(Job(
            title=title,
            company=board.company,
            job_url=j.get("hostedUrl") or "",
            apply_url=j.get("applyUrl") or "",
            source=ATS, board=board.key,
            external_id=str(j.get("id") or ""),
            location=_location(cats),
            country=(j.get("country") or "").upper(),
            remote_type=_WORKPLACE.get((j.get("workplaceType") or "").lower(), ""),
            salary=salary,
            posted_date=iso_date(j.get("createdAt")),
            date_source="source",
            description=_description(j),
        ))
    return jobs
