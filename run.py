"""Full run: scrape every board in data/boards.csv, keep fresh legitimate QA jobs,
write CSVs + a run report to output/.

  python run.py                      # all boards, last 7 days
  python run.py --max-age 3          # last 3 days
  python run.py --ats greenhouse     # only one job-board system
  python run.py --limit 20           # first 20 boards (quick test)
  python run.py --no-feeds           # company boards only (skip the open job sites)
  python run.py --feeds-only         # only the open job sites
  python run.py --mode quick         # job sites + boards that had a QA job in the last 30 days

Results also go to the database (data/jobs.db, or Postgres when DATABASE_URL is set),
which is what the website reads. --run-id is used by the website/GitHub workflow.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta

from qa_scraper import config, export, pipeline
from qa_scraper.feeds import FEEDS

QUICK_DAYS = 30


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boards", help="boards CSV (default data/boards.csv)")
    ap.add_argument("--max-age", type=int, default=config.MAX_AGE_DAYS, help="max posting age in days (default 7)")
    ap.add_argument("--ats", help="only boards on this system (comma-separated)")
    ap.add_argument("--limit", type=int, help="only the first N boards")
    ap.add_argument("--quiet", action="store_true", help="no per-board progress lines")
    ap.add_argument("--no-feeds", action="store_true", help="skip the open job sites")
    ap.add_argument("--feeds-only", action="store_true", help="only the open job sites")
    ap.add_argument("--mode", choices=["full", "quick", "feeds"], default="full")
    ap.add_argument("--run-id", type=int, help="existing runs row to fill (created by the website)")
    ap.add_argument("--trigger", default="cli", help="who started the run (cli | website | schedule)")
    args = ap.parse_args()
    if args.mode == "feeds":
        args.feeds_only = True

    from qa_scraper.store import Store, set_run_status
    try:
        store = Store(run_id=args.run_id, mode=args.mode, trigger=args.trigger)
    except Exception as e:
        print(f"Could not open the database: {type(e).__name__}: {e}")
        return 1
    if args.run_id is not None:
        row = store.db.one("SELECT status FROM runs WHERE id=?", (args.run_id,))
        if not row or row["status"] != "queued":
            print(f"Run #{args.run_id} is {row['status'] if row else 'missing'}; nothing to do.")
            return 0

    boards = [] if args.feeds_only else pipeline.load_boards(args.boards)
    if args.mode == "quick":
        rows = store.db.all("SELECT key FROM boards WHERE last_qa_date >= ?",
                            ((date.today() - timedelta(days=QUICK_DAYS)).isoformat(),))
        active = {r["key"] for r in rows}
        if active:
            boards = [b for b in boards if b.key in active]
        else:
            print("Quick mode: no board history yet, scanning every board this time.")
    if args.ats:
        wanted = {a.strip().lower() for a in args.ats.split(",")}
        boards = [b for b in boards if b.ats in wanted]
    if args.limit:
        boards = boards[: args.limit]
    feeds = [] if (args.no_feeds or args.ats or args.limit) else list(FEEDS.values())
    if not boards and not feeds:
        print("Nothing to scrape (check data/boards.csv or run discover.py).")
        if store.run_id is not None:
            set_run_status(store.run_id, "failed", "nothing to scrape")
        return 1
    print(f"Scraping {len(boards)} company boards + {len(feeds)} job sites, "
          f"keeping QA jobs posted within {args.max_age} days ...")

    try:
        res = asyncio.run(pipeline.run(boards, max_age=args.max_age, verbose=not args.quiet, feeds=feeds,
                                       store=store))
    except BaseException as e:
        if store.run_id is not None:
            set_run_status(store.run_id, "failed", f"{type(e).__name__}: {e}"[:300])
        raise
    paths = export.write_all(res, args.max_age)
    print()
    print(paths["report"].read_text(encoding="utf-8").encode("ascii", "replace").decode())
    print(f"Jobs file:    {paths['jobs']}")
    print(f"Undated:      {paths['undated']}")
    print(f"Flagged:      {paths['flagged']}")
    print(f"Board status: {paths['boards']}")
    print(f"Run #{store.run_id}: {res.new_jobs} new, {res.closed_jobs} closed"
          + (" (cancelled)" if res.cancelled else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
