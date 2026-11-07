"""Find and verify company job boards -> data/boards.csv

Reads company names from data/seed_companies.txt (one per line; optionally
"Company Name | slug1, slug2" to give exact board slugs), tries each name on every
supported job-board system, and records only boards that really respond WITH at
least one open job. Workday boards come from data/workday_seeds.txt: each line is
"Company | careers URL" (verified directly) or just "Company" (host and site are
guessed). Existing rows in boards.csv are kept.

  python discover.py                          # every seed on every system
  python discover.py --ats workable,personio  # only some systems
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
WORKDAY_SEEDS = config.DATA_DIR / "workday_seeds.txt"

PUBLIC_URL = {
    "greenhouse": "https://job-boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
    "smartrecruiters": "https://jobs.smartrecruiters.com/{token}",
    "workable": "https://apply.workable.com/{token}/",
    "recruitee": "https://{token}.recruitee.com/",
    "personio": "https://{token}.jobs.personio.de/",
    "teamtailor": "https://{token}.teamtailor.com/jobs",
    "bamboohr": "https://{token}.bamboohr.com/careers",
    "breezy": "https://{token}.breezy.hr/",
    "zohorecruit": "https://{token}.zohorecruit.com/jobs/Careers",
    "rippling": "https://ats.rippling.com/{token}/jobs",
    "manatal": "https://www.careers-page.com/{token}",
    "pinpoint": "https://{token}.pinpointhq.com/",
}
SYSTEMS = list(PUBLIC_URL) + ["workday", "oraclehcm"]
ORACLE_SEEDS = config.DATA_DIR / "oracle_seeds.txt"
ORACLE_URL = re.compile(r"https?://([a-z0-9.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z-]+/sites/([A-Za-z0-9_]+)")

# Workday data centres seen in the wild. A wrong host/tenant answers 422; a right
# tenant with a wrong site answers 404, so the host is found cheaply first.
WD_HOSTS = ["wd1", "wd5", "wd3", "wd12", "wd10", "wd103", "wd105", "wd108", "wd501", "wd502", "wd503"]
WD_SITE_PATTERNS = ["External", "Careers", "careers", "{T}Careers", "{T}_Careers", "{t}careers", "{T}External",
                    "External_Career_Site", "ExternalCareerSite", "{T}ExternalCareerSite", "{T}_External",
                    "Search", "jobs", "Jobs", "{t}", "{T}", "Global", "External_Careers", "en-US/{T}"]
WD_URL = re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)")
_PROBE_BODY = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}


def slugs_for(name: str, explicit: list[str]) -> list[str]:
    base = name.lower().replace("&", "and")
    base = re.sub(r"[^a-z0-9 .-]", "", base).strip()
    cands = explicit + [
        re.sub(r"[ .-]", "", base),        # "Sauce Labs" -> saucelabs
        re.sub(r"[ .]+", "-", base),       # -> sauce-labs
        re.sub(r"\b(inc|llc|ltd|gmbh|corp|co|technologies|technology|labs|hq|ai|io|software|group)\b", "", base).replace(" ", ""),
    ]
    out = []
    for c in cands:
        c = c.strip("-. ")
        if c and c not in out and not c.startswith("http"):
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


def _row(company, ats, token, n, host="", site="", url=""):
    return {"company": company, "ats": ats, "token": token, "host": host, "site": site,
            "careers_url": url or PUBLIC_URL.get(ats, "").format(token=token),
            "jobs_at_check": n, "verified_on": time.strftime("%Y-%m-%d")}


async def probe(http: Http, ats: str, name: str, slug: str):
    if ats == "smartrecruiters":
        # one cheap call instead of the per-keyword listing
        data = await http.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1})
        if not data or not data.get("totalFound"):
            return None
        company = ((data.get("content") or [{}])[0].get("company") or {}).get("name") or name
        return _row(company, ats, slug, data["totalFound"])
    src = sources.get(ats)
    jobs = await src.list_jobs(http, Board(company=name, ats=ats, token=slug))
    if not jobs:
        return None
    if ats in NAMED_BY_SYSTEM and jobs[0].company:
        company = jobs[0].company
    else:
        company = await verified_name(http, src, name, slug, jobs)
    return _row(company, ats, slug, len(jobs))


# Systems whose feed states the employer's name. For the others the name is only our
# seed guess, and a generic slug ("neon", "test", "arc") may belong to another company.
NAMED_BY_SYSTEM = ("greenhouse", "workable", "recruitee", "teamtailor", "breezy", "smartrecruiters")
# (zohorecruit, rippling, manatal, pinpoint, lever, ashby, personio, bamboohr: name is our guess -> verified)
_NAME_STOP = {"the", "inc", "ltd", "llc", "labs", "ai", "io", "hq", "group", "software", "technologies", "co"}


async def verified_name(http, src, name: str, slug: str, jobs) -> str:
    """Keep the seed name only if the board's own job descriptions mention it;
    otherwise label the board by its slug so no job is shown under a wrong employer."""
    words = [w for w in re.findall(r"[a-z0-9]+", name.lower()) if w not in _NAME_STOP] or [name.lower()]
    key = words[0] if len(words[0]) >= 3 else " ".join(words)
    sample = jobs[:8]
    if hasattr(src, "fill_detail") and not any(j.description for j in sample):
        for j in sample[:3]:
            await src.fill_detail(http, j)
    text = " ".join(f"{j.title} {j.description}" for j in sample).lower()
    if re.search(r"\b" + re.escape(key) + r"\b", text):
        return name
    return f"{slug} (name unverified)"


async def _wd_count(http: Http, host: str, tenant: str, site: str) -> int | None:
    data = await http.post_json(f"https://{host}/wday/cxs/{tenant}/{site}/jobs", _PROBE_BODY)
    if data is None:
        return None
    return int(data.get("total") or len(data.get("jobPostings") or []))


async def find_workday(http: Http, name: str, slugs: list[str], sem: asyncio.Semaphore):
    async with sem:
        for tenant in slugs[:2]:
            for wd in WD_HOSTS:
                host = f"{tenant}.{wd}.myworkdayjobs.com"
                r = await http.request("POST", f"https://{host}/wday/cxs/{tenant}/zz-probe/jobs", json=_PROBE_BODY)
                if r is None or r.status_code != 404:
                    continue                      # 422 = no such tenant on this host
                T = tenant.upper() if len(tenant) <= 4 else tenant.capitalize()
                for pat in WD_SITE_PATTERNS:
                    site = pat.format(T=T, t=tenant)
                    n = await _wd_count(http, host, tenant, site)
                    if n:
                        return _row(name, "workday", tenant, n, host=host, site=site,
                                    url=f"https://{host}/{site}")
                return None                       # tenant exists but site name not guessable
    return None


async def discover(seeds, systems, wd_urls, oracle_urls=()) -> list[dict]:
    found: list[dict] = []

    def report(row, name):
        found.append(row)
        print(f"  + {row['ats']}:{row['token']} ({row['jobs_at_check']} jobs) - {name}".encode("ascii", "replace").decode(),
              flush=True)

    async with Http() as http:
        wd_sem = asyncio.Semaphore(6)       # be gentle with Workday's shared infrastructure

        async def one_company(name, explicit):
            slugs = slugs_for(name, explicit)
            for ats in systems:
                if ats in ("workday", "oraclehcm"):
                    continue                # these come from their own seed files (see below)
                for slug in slugs:
                    row = await probe(http, ats, name, slug)
                    if row:
                        report(row, name)
                        break               # first working slug on this system is enough

        async def one_wd_url(name, url):
            m = WD_URL.match(url)
            if not m:                       # just a company name: guess host + site
                row = await find_workday(http, name, slugs_for(name, []), wd_sem)
                if row:
                    report(row, name)
                return
            tenant, wd, site = m.groups()
            host = f"{tenant}.{wd}.myworkdayjobs.com"
            async with wd_sem:
                n = await _wd_count(http, host, tenant, site)
            if n:
                report(_row(name, "workday", tenant, n, host=host, site=site, url=f"https://{host}/{site}"), name)

        async def one_oracle(name, url):
            m = ORACLE_URL.match(url)
            if not m:
                return
            host, site = m.groups()
            board = Board(company=name, ats="oraclehcm", token=host.split(".")[0], host=host, site=site)
            data = await http.get_json(sources.oraclehcm._list_url(board, "", 0))
            items = (data or {}).get("items") or []
            n = items[0].get("TotalJobsCount") if items else 0
            if n:
                report(_row(name, "oraclehcm", board.token, n, host=host, site=site, url=url), name)

        await asyncio.gather(*(one_company(n, s) for n, s in seeds),
                             *(one_wd_url(n, u) for n, u in wd_urls),
                             *(one_oracle(n, u) for n, u in oracle_urls))
    return found


def read_workday_seeds(path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, url = line.partition("|")
        url = url.strip()
        if not url and line.startswith("http"):
            name, url = line, line
        out.append((name.strip(), url))
    return out


async def companies_from_feeds() -> list[str]:
    """Names of employers advertising QA roles on the open job sites (last 60 days)."""
    from qa_scraper.feeds import FEEDS
    from qa_scraper.filters import qa_match
    async with Http() as http:
        results = await asyncio.gather(*(f.fetch(http, 60) for f in FEEDS.values()))
    names = []
    for jobs in results:
        for j in jobs or []:
            c = (j.company or "").strip()
            if c and qa_match.title_candidate(j.title) and c not in names and len(c) <= 60:
                names.append(c)
    return names


def _name_from_slug(slug: str) -> str:
    return re.sub(r"[-_.]+", " ", slug).strip().title() or slug


async def _verify_workday(http: Http, c: dict) -> dict | None:
    n = await _wd_count(http, c["host"], c["token"], c["site"])
    if not n:
        return None
    name = _name_from_slug(c["token"])
    # Workday doesn't state the employer: keep the tenant name only if a posting mentions it.
    base = f"https://{c['host']}/wday/cxs/{c['token']}/{c['site']}"
    data = await http.post_json(f"{base}/jobs", {"appliedFacets": {}, "limit": 3, "offset": 0, "searchText": ""})
    text = ""
    for p in (data or {}).get("jobPostings") or []:
        d = await http.get_json(base + (p.get("externalPath") or ""))
        text += " " + (((d or {}).get("jobPostingInfo") or {}).get("jobDescription") or "")
    key = re.sub(r"[^a-z0-9]", "", c["token"].lower())
    if not (len(key) >= 3 and key in re.sub(r"[^a-z0-9]", "", text.lower())):
        name = f"{c['token']} (name unverified)"
    return _row(name, "workday", c["token"], n, host=c["host"], site=c["site"],
                url=f"https://{c['host']}/{c['site']}")


async def from_candidates(path, systems=None, limit=None) -> int:
    """Verify Common Crawl candidates (harvest_commoncrawl.py) and add the working boards."""
    rows = read_boards()
    with open(path, encoding="utf-8", newline="") as f:
        cands = [c for c in csv.DictReader(f) if not systems or c["ats"] in systems]
    have = {(r["ats"], r["token"].lower()) for r in rows.values()}
    todo = [c for c in cands if (c["ats"], c["token"].lower()) not in have]
    # Workday: one site per tenant is enough (the harvest can list several URLs of one tenant).
    seen_wd, uniq = set(), []
    for c in todo:
        if c["ats"] == "workday":
            if c["token"].lower() in seen_wd:
                continue
            seen_wd.add(c["token"].lower())
        uniq.append(c)
    todo = uniq[:limit] if limit else uniq
    print(f"{len(cands)} candidates, {len(todo)} not in boards.csv yet: verifying ...", flush=True)
    found, done = [], [0]
    t0 = time.time()
    async with Http() as http:
        sem = asyncio.Semaphore(config.MAX_CONCURRENCY)

        async def one(c):
            async with sem:
                try:
                    if c["ats"] == "workday":
                        row = await _verify_workday(http, c)
                    else:
                        row = await probe(http, c["ats"], _name_from_slug(c["token"]), c["token"])
                        if row and c.get("host") and c["ats"] in ("zohorecruit", "personio"):
                            row["host"] = c["host"]
                except Exception:
                    row = None
            done[0] += 1
            if row:
                found.append(row)
            if done[0] % 250 == 0:
                print(f"  {done[0]}/{len(todo)} checked, {len(found)} working ({time.time() - t0:.0f}s)", flush=True)
        await asyncio.gather(*(one(c) for c in todo))
    before = len(rows)
    for r in found:
        rows.setdefault(f"{r['ats']}:{r['token']}".lower(), r)
    write_boards(rows)
    by: dict[str, int] = {}
    for r in found:
        by[r["ats"]] = by.get(r["ats"], 0) + 1
    unverified = sum(1 for r in rows.values() if "(name unverified)" in r["company"])
    print(f"\n{len(found)} working boards found in {time.time() - t0:.0f}s. boards.csv: {before} -> {len(rows)} "
          f"({len(rows) - unverified} with a verified company name, {unverified} unverified)")
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  + {k}: {v}")
    return 0


async def prune() -> int:
    """Drop boards that are gone, empty, or (Pinpoint) only serve demo postings."""
    rows = read_boards()
    print(f"Re-checking {len(rows)} boards ...")
    dead: list[str] = []
    async with Http() as http:
        async def one(key, r):
            src = sources.get(r["ats"])
            if r["ats"] == "smartrecruiters":
                ok = await probe(http, "smartrecruiters", r["company"], r["token"])
            elif r["ats"] == "workday":
                ok = await _wd_count(http, r["host"], r["token"], r["site"])
            else:
                ok = await src.list_jobs(http, Board(company=r["company"], ats=r["ats"], token=r["token"],
                                                     host=r.get("host", ""), site=r.get("site", "")))
            if not ok:
                dead.append(key)
        await asyncio.gather(*(one(k, r) for k, r in rows.items()))
    for k in dead:
        print(f"  - {k} ({rows[k]['company']})".encode("ascii", "replace").decode())
        rows.pop(k)
    write_boards(rows)
    unverified = sum(1 for r in rows.values() if "(name unverified)" in r["company"])
    print(f"Removed {len(dead)}. boards.csv: {len(rows)} boards "
          f"({len(rows) - unverified} with a verified company name, {unverified} unverified)")
    return 0


async def reverify_names() -> int:
    rows = read_boards()
    todo = [r for r in rows.values()
            if r["ats"] not in NAMED_BY_SYSTEM and r["ats"] not in ("workday", "oraclehcm")
            and "(name unverified)" not in r["company"]]
    print(f"Re-checking names of {len(todo)} boards ...")
    changed = 0
    async with Http() as http:
        async def one(r):
            nonlocal changed
            src = sources.get(r["ats"])
            jobs = await src.list_jobs(http, Board(company=r["company"], ats=r["ats"], token=r["token"],
                                                   host=r.get("host", ""), site=r.get("site", "")))
            if not jobs:
                return
            name = await verified_name(http, src, r["company"], r["token"], jobs)
            if name != r["company"]:
                print(f"  {r['ats']}:{r['token']}: '{r['company']}' -> '{name}'".encode("ascii", "replace").decode())
                r["company"] = name
                changed += 1
        await asyncio.gather(*(one(r) for r in todo))
    write_boards(rows)
    print(f"{changed} labels changed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default=str(SEEDS))
    ap.add_argument("--ats", help=f"comma-separated systems to probe (default all: {', '.join(SYSTEMS)})")
    ap.add_argument("--skip-known", action="store_true",
                    help="don't re-probe companies that already have a board in boards.csv")
    ap.add_argument("--from-feeds", action="store_true",
                    help="also probe every company currently advertising a QA job on the open job sites")
    ap.add_argument("--verify-names", action="store_true",
                    help="re-check company names of existing boards whose system doesn't state them")
    ap.add_argument("--from-candidates", nargs="?", const=str(config.DATA_DIR / "cc_candidates.csv"),
                    help="verify boards harvested from Common Crawl (default data/cc_candidates.csv)")
    ap.add_argument("--limit", type=int, help="with --from-candidates: only check the first N")
    ap.add_argument("--prune", action="store_true",
                    help="re-check every board in boards.csv and remove those that no longer return real jobs")
    args = ap.parse_args()
    if args.verify_names:
        return asyncio.run(reverify_names())
    if args.prune:
        return asyncio.run(prune())
    if args.from_candidates:
        systems = [a.strip() for a in args.ats.split(",")] if args.ats else None
        return asyncio.run(from_candidates(args.from_candidates, systems, args.limit))

    systems = [a.strip() for a in args.ats.split(",")] if args.ats else SYSTEMS
    seeds = read_seeds(args.seeds)
    rows = read_boards()
    if args.skip_known:
        known = {r["company"].lower() for r in rows.values()}
        seeds = [(n, s) for n, s in seeds if n.lower() not in known]
    if args.from_feeds:
        extra = asyncio.run(companies_from_feeds())
        have = {n.lower() for n, _ in seeds}
        seeds += [(n, []) for n in extra if n.lower() not in have]
        print(f"+ {len(extra)} companies hiring QA on the open job sites")
    wd_urls = read_workday_seeds(WORKDAY_SEEDS) if "workday" in systems else []
    oracle_urls = read_workday_seeds(ORACLE_SEEDS) if "oraclehcm" in systems else []
    print(f"Probing {len(seeds)} companies on {', '.join(systems)}"
          + (f" + {len(wd_urls)} Workday URLs" if wd_urls else "") + " ...")
    t0 = time.time()
    found = asyncio.run(discover(seeds, systems, wd_urls, oracle_urls))
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
