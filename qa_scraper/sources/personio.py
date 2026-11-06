"""Personio public XML job feed (no key).

  GET https://{slug}.jobs.personio.de/xml?language=en      (or .com)

Each <position> has id, name, office(s), createdAt and <jobDescriptions> (HTML).
Board host stores the exact feed host when known (e.g. acme.jobs.personio.com).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import Board, Job
from ..text import html_to_text, iso_date, xml_text

ATS = "personio"


def _hosts(board: Board) -> list[str]:
    if board.host:
        return [board.host]
    return [f"{board.token}.jobs.personio.de", f"{board.token}.jobs.personio.com"]


async def list_jobs(http, board: Board) -> list[Job] | None:
    xml, host = None, ""
    for h in _hosts(board):
        xml = await http.get_text(f"https://{h}/xml?language=en")
        if xml and "<workzag-jobs" in xml:
            host = h
            break
        xml = None
    if xml is None:
        return None
    soup = BeautifulSoup(xml, "xml")
    jobs = []
    for p in soup.find_all("position"):
        name = (xml_text(p, "name") or "").strip()
        pid = (xml_text(p, "id") or "").strip()
        if not name or not pid:
            continue
        offices = [xml_text(p, "office") or ""]
        add = p.find("additionalOffices")
        if add:
            offices += [o.get_text(strip=True) for o in add.find_all("office")]
        parts = []
        for d in p.find_all("jobDescription"):
            head = (xml_text(d, "name") or "").strip()
            body = html_to_text(xml_text(d, "value") or "")
            parts.append(f"{head}\n{body}".strip())
        jobs.append(Job(
            title=name,
            company=(xml_text(p, "subcompany") or "").strip() or board.company,
            job_url=f"https://{host}/job/{pid}",
            source=ATS, board=board.key, external_id=pid,
            location="; ".join(dict.fromkeys(o.strip() for o in offices if o.strip())),
            posted_date=iso_date(xml_text(p, "createdAt")), date_source="source",
            description="\n\n".join(x for x in parts if x),
        ))
    return jobs
