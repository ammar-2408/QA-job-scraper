"""Teamtailor public RSS feed (no key).

  GET https://{slug}.teamtailor.com/jobs.rss      (custom career domains go in board.host)

Items carry pubDate, link, remoteStatus, company_name, full HTML description and
structured tt:location entries (city / country).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import Board, Job
from ..text import html_to_text, iso_date, xml_text

ATS = "teamtailor"
_REMOTE = {"fully": "Remote", "remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite", "none": "Onsite"}


async def list_jobs(http, board: Board) -> list[Job] | None:
    host = board.host or f"{board.token}.teamtailor.com"
    xml = await http.get_text(f"https://{host}/jobs.rss")
    if not xml or "<rss" not in xml:
        return None
    soup = BeautifulSoup(xml, "xml")
    jobs = []
    for it in soup.find_all("item"):
        title = (xml_text(it, "title") or "").strip()
        if not title:
            continue
        locs, countries = [], []
        for loc in it.find_all("location"):
            nm = (xml_text(loc, "name") or "").strip()
            if nm:
                locs.append(nm)
            c = (xml_text(loc, "country") or "").strip()
            if c:
                countries.append(c)
        jobs.append(Job(
            title=title,
            company=(xml_text(it, "company_name") or "").strip() or board.company,
            job_url=(xml_text(it, "link") or "").strip(),
            source=ATS, board=board.key, external_id=(xml_text(it, "guid") or "").strip(),
            location="; ".join(dict.fromkeys(locs)),
            country="; ".join(dict.fromkeys(countries)),
            remote_type=_REMOTE.get((xml_text(it, "remoteStatus") or "").strip().lower(), ""),
            posted_date=iso_date((xml_text(it, "pubDate") or "").strip()), date_source="source",
            description=html_to_text(xml_text(it, "description") or ""),
        ))
    return jobs
