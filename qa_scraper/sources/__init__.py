"""Source registry.

Each source module exposes:
  ATS = "<name>"
  async def list_jobs(http, board) -> list[Job] | None   (None = board unreachable/invalid)
  async def fill_detail(http, job) -> None              (optional; fetches full description)
"""
from __future__ import annotations

from . import ashby, greenhouse, lever

SOURCES = {m.ATS: m for m in (greenhouse, lever, ashby)}


def get(ats: str):
    return SOURCES.get((ats or "").lower())
