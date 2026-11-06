"""Full run: scrape every board in data/boards.csv, keep fresh legitimate QA jobs,
write CSVs + a run report to output/.

  python run.py                      # all boards, last 7 days
  python run.py --max-age 3          # last 3 days
  python run.py --ats greenhouse     # only one job-board system
  python run.py --limit 20           # first 20 boards (quick test)
  python run.py --no-feeds           # company boards only (skip the open job sites)
  python run.py --feeds-only         # only the open job sites
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from qa_scraper import config, export, pipeline
from qa_scraper.feeds import FEEDS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boards", help="boards CSV (default data/boards.csv)")
    ap.add_argument("--max-age", type=int, default=config.MAX_AGE_DAYS, help="max posting age in days (default 7)")
    ap.add_argument("--ats", help="only boards on this system (comma-separated)")
    ap.add_argument("--limit", type=int, help="only the first N boards")
    ap.add_argument("--quiet", action="store_true", help="no per-board progress lines")
    ap.add_argument("--no-feeds", action="store_true", help="skip the open job sites")
    ap.add_argument("--feeds-only", action="store_true", help="only the open job sites")
    args = ap.parse_args()

    boards = [] if args.feeds_only else pipeline.load_boards(args.boards)
    if args.ats:
        wanted = {a.strip().lower() for a in args.ats.split(",")}
        boards = [b for b in boards if b.ats in wanted]
    if args.limit:
        boards = boards[: args.limit]
    feeds = [] if (args.no_feeds or args.ats or args.limit) else list(FEEDS.values())
    if not boards and not feeds:
        print("Nothing to scrape (check data/boards.csv or run discover.py).")
        return 1
    print(f"Scraping {len(boards)} company boards + {len(feeds)} job sites, "
          f"keeping QA jobs posted within {args.max_age} days ...")

    res = asyncio.run(pipeline.run(boards, max_age=args.max_age, verbose=not args.quiet, feeds=feeds))
    paths = export.write_all(res, args.max_age)
    print()
    print(paths["report"].read_text(encoding="utf-8").encode("ascii", "replace").decode())
    print(f"Jobs file:    {paths['jobs']}")
    print(f"Undated:      {paths['undated']}")
    print(f"Flagged:      {paths['flagged']}")
    print(f"Board status: {paths['boards']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
