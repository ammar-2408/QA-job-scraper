"""Oracle Recruiting Cloud (Fusion HCM) public candidate-experience API (no key).
Used by very large employers (JPMorgan Chase, Oracle, ...).

  list:   GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
              ?onlyData=true&expand=requisitionList.secondaryLocations
              &finder=findReqs;siteNumber={site},facetsList=NONE,keyword={term},limit=50,offset=N,
                      sortBy=POSTING_DATES_DESC
  detail: GET https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails
              ?expand=all&onlyData=true&finder=ById;Id="{id}",siteNumber={site}

Board fields: host (e.g. jpmc.fa.oraclecloud.com), site (e.g. CX_1001). Searches each
term in config.SEARCH_TERMS; results are newest first, so paging stops at old postings.
"""
from __future__ import annotations

from urllib.parse import quote

from .. import config
from ..models import Board, Job
from ..text import days_between, html_to_text, iso_date

ATS = "oraclehcm"
PAGE = 50
MAX_PAGES_PER_TERM = 3
STOP_AFTER_DAYS = 31        # newest-first: once a page reaches this age, stop paging


def _list_url(board: Board, term: str, offset: int) -> str:
    finder = (f"findReqs;siteNumber={board.site},facetsList=NONE,keyword={quote(term)},"
              f"limit={PAGE},offset={offset},sortBy=POSTING_DATES_DESC")
    return (f"https://{board.host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}")


async def list_jobs(http, board: Board) -> list[Job] | None:
    if not (board.host and board.site):
        return None
    seen: dict[str, Job] = {}
    any_ok = False
    for term in config.SEARCH_TERMS:
        for page in range(MAX_PAGES_PER_TERM):
            data = await http.get_json(_list_url(board, term, page * PAGE))
            items = (data or {}).get("items") or []
            if not items:
                break
            any_ok = True
            reqs = items[0].get("requisitionList") or []
            oldest = 0
            for r in reqs:
                rid = str(r.get("Id") or "")
                if not rid or rid in seen:
                    continue
                posted = iso_date(r.get("PostedDate"))
                oldest = max(oldest, days_between(posted) or 0)
                locs = [r.get("PrimaryLocation") or ""] + [s.get("Name") or "" for s in r.get("secondaryLocations") or []]
                wp = (r.get("WorkplaceType") or r.get("WorkplaceTypeCode") or "").lower()
                seen[rid] = Job(
                    title=" ".join((r.get("Title") or "").split()), company=board.company,
                    job_url=f"https://{board.host}/hcmUI/CandidateExperience/en/sites/{board.site}/job/{rid}",
                    source=ATS, board=board.key, external_id=rid,
                    location="; ".join(dict.fromkeys(l for l in locs if l)),
                    country=r.get("PrimaryLocationCountry") or "",
                    remote_type="Remote" if "remote" in wp else ("Hybrid" if "hybrid" in wp else ""),
                    posted_date=posted, date_source="source",
                    detail_ref={"url": (f"https://{board.host}/hcmRestApi/resources/latest/"
                                        f"recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                                        f"&finder=ById;Id=%22{rid}%22,siteNumber={board.site}")},
                )
            if len(reqs) < PAGE or oldest > STOP_AFTER_DAYS:
                break
    return list(seen.values()) if any_ok else None


async def fill_detail(http, job: Job) -> None:
    data = await http.get_json(job.detail_ref["url"])
    items = (data or {}).get("items") or []
    if not items:
        return
    d = items[0]
    parts = [html_to_text(d.get(k) or "") for k in
             ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr",
              "CorporateDescriptionStr", "OrganizationDescriptionStr")]
    for f in d.get("requisitionFlexFields") or []:
        val = html_to_text(f.get("Value") or "")
        if val:
            parts.append(f"{(f.get('Prompt') or '').strip()}: {val}".strip(": "))
    job.description = "\n\n".join(p for p in parts if p)[: config.MAX_DESC]
