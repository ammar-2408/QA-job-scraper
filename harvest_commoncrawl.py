"""Harvest job-board slugs from the Common Crawl URL index -> data/cc_candidates.csv

Common Crawl (free, public, no key) publishes, for every monthly crawl, a sorted URL
index split into gzip blocks plus a small lookup file (cluster.idx) saying which block
covers which URL prefix. We download cluster.idx once per crawl, then fetch only the
blocks for the job-board hosts we support (HTTP range requests, a few at a time), and
pull each board's slug out of the crawled URLs. This avoids the index *server*
(index.commoncrawl.org), which is often overloaded.

The candidates are not verified here: discover.py --from-candidates checks each one
(it must answer with real open jobs) before it goes into data/boards.csv.

  python harvest_commoncrawl.py                       # latest crawl
  python harvest_commoncrawl.py --crawls 3            # the 3 latest crawls (more boards)
  python harvest_commoncrawl.py --crawl CC-MAIN-2026-43
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from qa_scraper import config

DATA = "https://data.commoncrawl.org"
CACHE = config.DATA_DIR / "cc_cache"                  # cluster.idx files (gitignored)
OUT = config.DATA_DIR / "cc_candidates.csv"
FIELDS = ["ats", "token", "host", "site", "example_url", "crawl"]
HEADERS = {"User-Agent": config.USER_AGENT}

# SURT prefixes (reversed host, as the index sorts them) for each supported system.
PREFIXES = {
    "greenhouse": ["io,greenhouse,boards)/", "io,greenhouse,job-boards)/"],
    "lever": ["co,lever,jobs)/"],
    "ashby": ["com,ashbyhq,jobs)/"],
    "workable": ["com,workable,apply)/"],
    "recruitee": ["com,recruitee,"],
    "bamboohr": ["com,bamboohr,"],
    "breezy": ["hr,breezy,"],
    "teamtailor": ["com,teamtailor,"],
    "personio": ["de,personio,jobs,", "com,personio,jobs,"],
    "zohorecruit": ["com,zohorecruit,", "in,zohorecruit,", "eu,zohorecruit,"],
    "workday": ["com,myworkdayjobs,"],
    "rippling": ["com,rippling,ats)/"],
    "smartrecruiters": ["com,smartrecruiters,jobs)/", "com,smartrecruiters,careers)/"],
    "pinpoint": ["com,pinpointhq,"],
    "manatal": ["com,careers-page)/"],
}

SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")
# Subdomains / first path parts that belong to the system itself, not to a company.
RESERVED = {"www", "api", "app", "apps", "help", "support", "status", "blog", "docs", "careers", "jobs", "job",
            "embed", "static", "assets", "cdn", "login", "signup", "admin", "marketplace", "partners", "developers",
            "dev", "staging", "test", "demo", "mail", "email", "info", "about", "pricing", "j", "s", "v1", "v0",
            "en", "de", "fr", "es", "search", "robots.txt", "sitemap.xml", "favicon.ico", "oauth", "auth", "go",
            "career", "hire", "company", "companies", "account", "accounts", "portal", "media", "images", "img",
            "wday", "public", "share", "track", "feeds", "rss", "community", "integrations", "resources"}


def latest_crawls(n: int) -> list[str]:
    r = httpx.get("https://index.commoncrawl.org/collinfo.json", headers=HEADERS, timeout=60)
    r.raise_for_status()
    return [c["id"] for c in r.json()[:n]]


def cluster_index(crawl: str) -> tuple[list[str], list[tuple[str, int, int]]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{crawl}-cluster.idx"
    if not path.exists():
        print(f"  downloading cluster.idx for {crawl} (~100 MB, once) ...", flush=True)
        tmp = path.with_suffix(".part")
        with httpx.stream("GET", f"{DATA}/cc-index/collections/{crawl}/indexes/cluster.idx", headers=HEADERS,
                          timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        tmp.replace(path)
    keys, blocks = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            keys.append(parts[0].split(" ")[0])
            blocks.append((parts[1], int(parts[2]), int(parts[3])))
    return keys, blocks


def blocks_for(prefix: str, keys: list[str], blocks) -> list[int]:
    """Indexes of the blocks that can contain URLs starting with `prefix`."""
    i = max(0, bisect.bisect_left(keys, prefix) - 1)       # the block before may hold the first lines
    out = []
    while i < len(keys):
        if keys[i] > prefix and not keys[i].startswith(prefix):
            break
        out.append(i)
        i += 1
    return out


def fetch_block(crawl: str, block) -> list[str]:
    name, offset, length = block
    url = f"{DATA}/cc-index/collections/{crawl}/indexes/{name}"
    for attempt in range(5):
        try:
            r = httpx.get(url, headers={**HEADERS, "Range": f"bytes={offset}-{offset + length - 1}"}, timeout=120)
            if r.status_code in (200, 206):
                return gzip.decompress(r.content).decode("utf-8", errors="replace").splitlines()
            if r.status_code in (429, 503):
                time.sleep(5 * (attempt + 1))
                continue
            return []
        except (httpx.HTTPError, OSError, EOFError):
            time.sleep(3 * (attempt + 1))
    return []


def _sub(host: str, base: str) -> str:
    """'acme.recruitee.com' with base 'recruitee.com' -> 'acme'."""
    if not host.endswith("." + base):
        return ""
    sub = host[: -len(base) - 1]
    return sub if "." not in sub else ""


def extract(ats: str, url: str) -> dict | None:
    """Board identity from one crawled URL, or None."""
    try:
        u = urlparse(url)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    parts = [p for p in u.path.split("/") if p]
    first = parts[0] if parts else ""
    token, b_host, site = "", "", ""
    if ats == "greenhouse":
        if first in ("embed", "embed_job_board") or "for" in parse_qs(u.query):
            token = (parse_qs(u.query).get("for") or [""])[0]
        else:
            token = first
    elif ats in ("lever", "ashby", "workable", "rippling", "manatal"):
        token = first
    elif ats == "smartrecruiters":
        token = first                                    # company identifier keeps its case in the API
        return {"ats": ats, "token": token, "host": "", "site": ""} if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$", token) \
            and token.lower() not in RESERVED else None
    elif ats in ("recruitee", "bamboohr", "teamtailor", "pinpoint"):
        token = _sub(host, f"{ats.replace('pinpoint', 'pinpointhq')}.com")
    elif ats == "breezy":
        token = _sub(host, "breezy.hr")
    elif ats == "personio":
        for d in ("jobs.personio.de", "jobs.personio.com"):
            if _sub(host, d):
                token, b_host = _sub(host, d), host
    elif ats == "zohorecruit":
        for d in ("zohorecruit.com", "zohorecruit.in", "zohorecruit.eu"):
            if _sub(host, d):
                token, b_host = _sub(host, d), host
    elif ats == "workday":
        m = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
        if not m or not parts:
            return None
        rest = parts[1:] if re.match(r"^[a-z]{2}-[A-Za-z]{2}$", parts[0]) else parts   # optional locale
        if not rest or rest[0].lower() in RESERVED:
            return None
        token, b_host, site = m.group(1), host, rest[0]
        if not re.match(r"^[A-Za-z0-9_-]{2,80}$", site):
            return None
        return {"ats": ats, "token": token, "host": b_host, "site": site}
    token = token.lower()
    if not token or token in RESERVED or not SLUG.match(token):
        return None
    return {"ats": ats, "token": token, "host": b_host, "site": site}


def harvest(crawl: str, systems: list[str], workers: int) -> dict[tuple, dict]:
    keys, blocks = cluster_index(crawl)
    found: dict[tuple, dict] = {}
    for ats in systems:
        idx = sorted({i for p in PREFIXES[ats] for i in blocks_for(p, keys, blocks)})
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for lines in ex.map(lambda i: fetch_block(crawl, blocks[i]), idx):
                for line in lines:
                    surt, _, rest = line.partition(" ")
                    if not any(surt.startswith(p) for p in PREFIXES[ats]):
                        continue
                    try:
                        rec = json.loads(rest.split(" ", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    c = extract(ats, rec.get("url") or "")
                    if not c:
                        continue
                    k = (c["ats"], c["token"].lower(), c["site"].lower())
                    if k not in found:
                        found[k] = {**c, "example_url": rec.get("url", "")[:300], "crawl": crawl}
        n = sum(1 for k in found if k[0] == ats)
        print(f"  {crawl} {ats}: {len(idx)} index blocks -> {n} boards so far ({time.time() - t0:.0f}s)", flush=True)
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crawl", help="one crawl id, e.g. CC-MAIN-2026-43")
    ap.add_argument("--crawls", type=int, default=1, help="use the N latest crawls (default 1)")
    ap.add_argument("--ats", help="only these systems (comma-separated)")
    ap.add_argument("--workers", type=int, default=4, help="parallel block downloads (default 4, be gentle)")
    args = ap.parse_args()
    systems = [a.strip() for a in args.ats.split(",")] if args.ats else list(PREFIXES)
    crawls = [args.crawl] if args.crawl else latest_crawls(args.crawls)

    rows: dict[tuple, dict] = {}
    if OUT.exists():                                   # keep earlier harvests
        with open(OUT, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["ats"], r["token"].lower(), (r.get("site") or "").lower())] = r
    before = len(rows)
    for crawl in crawls:
        print(f"Crawl {crawl}:", flush=True)
        for k, v in harvest(crawl, systems, args.workers).items():
            rows.setdefault(k, v)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for _, r in sorted(rows.items()):
            w.writerow(r)
    by: dict[str, int] = {}
    for k in rows:
        by[k[0]] = by.get(k[0], 0) + 1
    print(f"\n{OUT.name}: {before} -> {len(rows)} candidate boards")
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
