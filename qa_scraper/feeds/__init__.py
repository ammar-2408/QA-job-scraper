"""Open job sites (aggregators). Unlike company boards, anyone can post on these,
so their jobs go through the stricter aggregator legitimacy checks.

Each module exposes:
  NAME = "<site>"
  async def fetch(http, max_age: int) -> list[Job] | None   (None = site unreachable)

All of these sites ask for attribution: the output keeps the source name and the
original posting URL for every job.
"""
from __future__ import annotations

from . import arbeitnow, getonboard, himalayas, jobicy, remoteok, remotive, weworkremotely

FEEDS = {m.NAME: m for m in (remotive, remoteok, weworkremotely, himalayas, jobicy, arbeitnow, getonboard)}
