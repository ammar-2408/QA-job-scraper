"""Test one board quickly and print what the scraper would keep.

  python check_board.py greenhouse gitlab
  python check_board.py lever spotify --max-age 30
  python check_board.py ashby ramp --all        # list every QA job regardless of age
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from qa_scraper import pipeline
from qa_scraper.models import Board


def _a(s) -> str:
    return str(s if s is not None else "").encode("ascii", "replace").decode()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ats")
    ap.add_argument("token")
    ap.add_argument("--company", default="")
    ap.add_argument("--host", default="", help="workday host, e.g. nvidia.wd5.myworkdayjobs.com")
    ap.add_argument("--site", default="", help="workday site, e.g. NVIDIAExternalCareerSite")
    ap.add_argument("--max-age", type=int, default=7)
    ap.add_argument("--all", action="store_true", help="ignore the age limit (show every QA job)")
    args = ap.parse_args()

    board = Board(company=args.company or args.token, ats=args.ats.lower(), token=args.token,
                  host=args.host, site=args.site)
    res = asyncio.run(pipeline.run([board], max_age=10_000 if args.all else args.max_age, verbose=False))
    br = res.boards[0]
    if not br.ok:
        print(f"FAILED: {br.error}")
        return 1
    print(f"{board.key}: {br.total_jobs} jobs on board, {br.qa_jobs} QA in window, {len(res.kept)} kept")
    for j in res.kept:
        print(f"  [{j.days_old}d] {_a(j.title)} | {_a(j.location)} | {_a(j.country)} | {_a(j.remote_type)} "
              f"| {_a(j.role_type)} | {_a(j.tools)[:60]}")
        print(f"        {_a(j.job_url)}")
    if res.undated:
        print(f"Undated QA jobs: {len(res.undated)}")
    if res.flagged:
        print(f"Flagged: {len(res.flagged)}")
        for j in res.flagged:
            print(f"  {_a(j.title)} -> {_a(j.trust_reasons)}")
    c = res.counts
    print(f"(not QA title: {c['not_qa_title']}, too old: {c['too_old']}, "
          f"rejected by description: {c['rejected_by_description']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
