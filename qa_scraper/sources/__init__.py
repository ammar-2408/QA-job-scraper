"""Company job-board systems.

Each source module exposes:
  ATS = "<name>"
  async def list_jobs(http, board) -> list[Job] | None   (None = board unreachable/invalid)
  async def fill_detail(http, job) -> None              (optional; full description / exact date)
"""
from __future__ import annotations

from . import (ashby, bamboohr, breezy, greenhouse, lever, manatal, oraclehcm, personio, pinpoint, recruitee,
               rippling, smartrecruiters, teamtailor, workable, workday, zohorecruit)

SOURCES = {m.ATS: m for m in (greenhouse, lever, ashby, workday, smartrecruiters, workable, recruitee,
                              personio, teamtailor, bamboohr, breezy, zohorecruit, oraclehcm, rippling,
                              manatal, pinpoint)}


def get(ats: str):
    return SOURCES.get((ats or "").lower())
