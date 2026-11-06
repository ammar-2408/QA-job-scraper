"""Find and verify company job boards -> data/boards.csv

Reads company names from data/seed_companies.txt (one per line; optionally
"Company Name | slug1, slug2" to give exact board slugs), tries each name's likely
board slug on every supported job-board system, and records only the boards that
really respond WITH at least one job. Existing rows in boards.csv are kept.

  python discover.py                       # probe every seed company on every system
  python discover.py --ats greenhouse      # only one system
  python discover.py --seeds my_list.txt
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import re
import sys
import time

from qa_scraper import config, sources
from qa_scraper.http import Http
from qa_scraper.models import Board

FIELDS = ["company", "ats", "token", "host", "site", "careers_url", "jobs_at_check", "verified_on"]
SEEDS = config.DATA_DIR / "seed_companies.txt"

PUBLIC_URL = {
    "greenhouse": "https://job-boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
}


def slugs_for(name: str, explicit: list[str]) -> list[str]:
    base = name.lower().replace("&", "and")
    base = re.sub(r"[^a-z0-9 .-]", "", base).strip()
    cands = explicit + [
        re.sub(r"[ .-]", "", base),        # "Sauce Labs" -> saucelabs
        re.sub(r"[ .]+", "-", base),       # -> sauce-labs
        re.sub(r"\b(inc|llc|ltd|gmbh|corp|co|technologies|technology|labs|hq|ai|io)\b", "", base).replace(" ", ""),
    ]
    out = []
    for c in cands:
        c = c.strip("-. ")
        if c and c not in out:
            out.append(c)
    return out


def read_seeds(path) -> list[tuple[str, list[str]]]:
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, slugs = line.partition("|")
        out.append((name.strip(), [s.strip().lower() for s in slugs.split(",") if s.strip()]))
    return out


def read_boards() -> dict[str, dict]:
    if not config.BOARDS_CSV.exists():
        return {}
    with open(config.BOARDS_CSV, encoding="utf-8-sig", newline="") as f:
        return {f"{r['ats']}:{r['token']}".lower(): r for r in csv.DictReader(f)}


def write_boards(rows: dict[str, dict]) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    with open(config.BOARDS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for _, r in sorted(rows.items(), key=lambda kv: (kv[1]["ats"], kv[1]["company"].lower())):
            w.writerow(r)


async def probe(http: Http, ats: str, name: str, slug: str):
    src = sources.get(ats)
    board = Board(company=name, ats=ats, token=slug)
    jobs = await src.list_jobs(http, board)
    if not jobs:
        return None
    company = jobs[0].company if ats == "greenhouse" and jobs[0].company else name
    return {"company": company, "ats": ats, "token": slug, "host": "", "site": "",
            "careers_url": PUBLIC_URL.get(ats, "").format(token=slug),
            "jobs_at_check": len(jobs), "verified_on": time.strftime("%Y-%m-%d")}


async def discover(seeds, systems) -> list[dict]:
    found: list[dict] = []
    async with Http() as http:
        async def one_company(name, explicit):
            for ats in systems:
                for slug in slugs_for(name, explicit):
                    row = await probe(http, ats, name, slug)
                    if row:
                        found.append(row)
                        print(f"  + {ats}:{slug} ({row['jobs_at_check']} jobs) - {name}".encode("ascii", "replace").decode(),
                              flush=True)
                        break          # first working slug on this system is enough
        await asyncio.gather(*(one_company(n, s) for n, s in seeds))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=str(SEEDS))
    ap.add_argument("--ats", help="comma-separated systems to probe (default: all that support discovery)")
    args = ap.parse_args()

    systems = [a.strip() for a in args.ats.split(",")] if args.ats else list(PUBLIC_URL)
    seeds = read_seeds(args.seeds)
    print(f"Probing {len(seeds)} companies on {', '.join(systems)} ...")
    t0 = time.time()
    found = asyncio.run(discover(seeds, systems))
    rows = read_boards()
    before = len(rows)
    for r in found:
        rows[f"{r['ats']}:{r['token']}".lower()] = r
    write_boards(rows)
    by_ats: dict[str, int] = {}
    for r in rows.values():
        by_ats[r["ats"]] = by_ats.get(r["ats"], 0) + 1
    print(f"\nFound {len(found)} working boards in {time.time() - t0:.0f}s. "
          f"boards.csv: {before} -> {len(rows)} boards")
    for k, v in sorted(by_ats.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
