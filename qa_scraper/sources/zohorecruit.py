"""Zoho Recruit public careers API (no key). Widely used by software houses in
Pakistan and India (e.g. Tkxel, Systems Limited).

  list:   GET https://{slug}.zohorecruit.com/recruit/v2/public/Job_Openings?pagename=Careers
  detail: GET https://{slug}.zohorecruit.com/recruit/v2/public/Job_Openings/{id}?pagename=Careers

These are the same public endpoints the company's own careers page reads. The list
has title / city / country / remote; the detail adds Date_Opened, the description,
salary and experience. Accounts can live on zohorecruit.com, .in or .eu (board.host).
An unknown slug answers 403 ORG_NOT_FOUND.
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text, iso_date

ATS = "zohorecruit"
DOMAINS = ("zohorecruit.com", "zohorecruit.in", "zohorecruit.eu")


def _hosts(board: Board) -> list[str]:
    return [board.host] if board.host else [f"{board.token}.{d}" for d in DOMAINS]


async def list_jobs(http, board: Board) -> list[Job] | None:
    data, host = None, ""
    for h in _hosts(board):
        data = await http.get_json(f"https://{h}/recruit/v2/public/Job_Openings", params={"pagename": "Careers"})
        if isinstance(data, dict) and data.get("code") == "success":
            host = h
            break
        data = None
    if data is None:
        return None
    jobs = []
    for o in data.get("data") or []:
        title = (o.get("Posting_Title") or o.get("Job_Opening_Name") or "").strip()
        jid = str(o.get("id") or "")
        # Shown on the careers page when published OR explicitly kept there.
        if not title or not jid or (o.get("Publish") is False and not o.get("Keep_on_Career_Site")):
            continue
        jobs.append(Job(
            title=title, company=board.company,
            job_url=o.get("$url") or f"https://{host}/jobs/Careers/{jid}",
            source=ATS, board=board.key, external_id=jid,
            location=", ".join(x for x in (o.get("City"), o.get("State"), o.get("Country")) if x),
            country=o.get("Country") or "",
            remote_type="Remote" if o.get("Remote_Job") else "",
            detail_ref={"url": f"https://{host}/recruit/v2/public/Job_Openings/{jid}?pagename=Careers"},
        ))
    return jobs


async def fill_detail(http, job: Job) -> None:
    data = await http.get_json(job.detail_ref["url"])
    rows = (data or {}).get("data") or []
    if not rows:
        return
    d = rows[0]
    job.description = html_to_text(d.get("Job_Description") or "")
    job.posted_date = iso_date(d.get("Date_Opened"))
    job.date_source = "source" if job.posted_date else ""
    sal = (d.get("Salary") or "").strip()
    if sal and sal.lower() not in ("market competitive", "competitive", "negotiable"):
        job.salary = sal
    if d.get("Work_Experience"):
        job.experience = d["Work_Experience"]
    if d.get("$appy_url"):
        job.apply_url = d["$appy_url"]
