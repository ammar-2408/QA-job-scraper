"""Pinpoint public postings feed (no key).

  GET https://{slug}.pinpointhq.com/postings.json

No posted date is published, so freshness comes from first-seen tracking (store.py).
"""
from __future__ import annotations

from ..models import Board, Job
from ..text import html_to_text

ATS = "pinpoint"
_WORKPLACE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Onsite"}

# Unused / trial Pinpoint accounts serve these template postings. A board made only
# of them is not a real job board (seen on bosch., razorpay., zendesk., sage. ...).
DEMO_TITLES = {"customer service rep", "marketing manager", "marketing executive"}


def _is_demo(titles: list[str]) -> bool:
    return bool(titles) and all(t.lower() in DEMO_TITLES or t.lower().startswith("head of dei") for t in titles)


async def list_jobs(http, board: Board) -> list[Job] | None:
    data = await http.get_json(f"https://{board.token}.pinpointhq.com/postings.json")
    if not isinstance(data, dict) or "data" not in data:
        return None
    if _is_demo([(j.get("title") or "").strip() for j in data["data"]]):
        return None
    jobs = []
    for j in data["data"]:
        title = (j.get("title") or "").strip()
        if not title:
            continue
        loc = j.get("location") or {}
        parts = [j.get("description"), j.get("key_responsibilities"), j.get("skills_knowledge_expertise"),
                 j.get("benefits")]
        salary = ""
        if j.get("compensation_visible") and (j.get("compensation_minimum") or j.get("compensation_maximum")):
            salary = (f"{j.get('compensation_currency') or ''} {j.get('compensation_minimum') or ''}-"
                      f"{j.get('compensation_maximum') or ''} {j.get('compensation_frequency') or ''}").strip()
        jobs.append(Job(
            title=title, company=board.company, job_url=j.get("url") or "",
            source=ATS, board=board.key, external_id=str(j.get("id") or ""),
            location=loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("province")) if x),
            remote_type=_WORKPLACE.get((j.get("workplace_type") or "").lower(), ""),
            salary=salary,
            description="\n\n".join(html_to_text(p) for p in parts if p),
        ))
    return jobs
