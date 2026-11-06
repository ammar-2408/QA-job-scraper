"""We Work Remotely public RSS: https://weworkremotely.com/remote-jobs.rss

Titles are "Company: Job Title"; descriptions start with a Headquarters / URL block
that gives the company's website.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import Job
from ..text import html_to_text, iso_date, xml_text

NAME = "weworkremotely"
_URL = re.compile(r"URL:\s*</strong>\s*<a href=\"([^\"]+)\"", re.I)


async def fetch(http, max_age: int) -> list[Job] | None:
    xml = await http.get_text("https://weworkremotely.com/remote-jobs.rss")
    if not xml or "<rss" not in xml:
        return None
    jobs = []
    for it in BeautifulSoup(xml, "xml").find_all("item"):
        raw_title = (xml_text(it, "title") or "").strip()
        company, _, title = raw_title.partition(":")
        if not title:
            company, title = "", raw_title
        desc_html = xml_text(it, "description") or ""
        m = _URL.search(desc_html)
        region = (xml_text(it, "region") or "").strip()
        country = (xml_text(it, "country") or "").strip()
        jobs.append(Job(
            title=title.strip(), company=company.strip(),
            job_url=(xml_text(it, "link") or "").strip(), source=NAME, source_kind="aggregator",
            board=NAME, external_id=(xml_text(it, "guid") or "").strip(),
            location="; ".join(x for x in (region, country) if x), remote_type="Remote",
            company_url=m.group(1) if m else "",
            posted_date=iso_date((xml_text(it, "pubDate") or "").strip()), date_source="source",
            description=html_to_text(desc_html),
        ))
    return jobs
