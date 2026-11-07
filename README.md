# QA Job Scraper

Finds remote software QA and testing jobs for interns, juniors and mid-level testers,
from companies' own job boards and from open remote-job sites. A job is kept only if it
passes every rule:

- Software QA: manual testers, automation testers, QA engineers and analysts, SDETs and
  Engineers in Test, game QA, and titles that name a testing tool (Selenium, Playwright,
  Cypress, Appium and others). Developer roles, test-tooling engineering, language
  testing (LQA, proofreading), user-research "testers" and risk or compliance "QA" are
  dropped.
- Fully remote. Hybrid, on-site and jobs that never clearly say remote are dropped. A
  "Remote" label is also dropped when the description says otherwise ("hybrid, 3 days in
  the office", "this role is on-site").
- Intern, junior or mid level: senior, lead, staff, principal, manager and director titles
  are dropped, and so are jobs asking for more than 5 years of experience.
- Outside India: jobs limited to India are dropped (jobs open in a long list of countries
  are kept).
- Fresh: posted in the last 30 days by default.
- Legitimate: company boards are trusted; open-site jobs need a company name, a real
  description and no scam signs (apply on Telegram or WhatsApp, personal Gmail, fees).

No API keys, no AI. Everything comes from public feeds, and the filters are plain rules
in `qa_scraper/filters/`. All rules can be changed in `qa_scraper/config.py` or with
environment variables (see below).

## Setup

```bash
pip install -r requirements.txt
```

Python 3.11 or newer.

## The website

```bash
python serve.py
```

Opens http://localhost:8000. From there you can:

- Start a run: Full (every board and job site), Quick (job sites plus boards that had a QA
  job in the last 30 days) or Job sites only. Progress is shown live and new jobs appear
  as boards finish. Runs can be cancelled.
- Browse the jobs table, newest first. Sort any column, filter by country, role type,
  seniority, tool, source, trust, age and status, and search titles, companies,
  descriptions and tools.
- Mark jobs as applied. This is saved in the browser, so each computer keeps its own list.
- Open a job to read the full description and go to the original posting.
- Export what is on screen to Excel or CSV.
- See every board's last scan on the Boards page, and past runs on Run history.

NEW means the job first appeared in the latest run. Closed means the company's board
was scanned successfully and no longer lists it.

## Command line

```bash
python run.py                          # full run, writes CSVs and a report to output/
python run.py --mode quick             # job sites + recently active boards
python run.py --mode feeds             # job sites only
python run.py --max-age 7              # only jobs from the last 7 days
python run.py --ats greenhouse,lever   # only some job-board systems
python check_board.py lever spotify    # test one board
python check_board.py feed himalayas   # test one job site
python -m unittest discover tests      # run the tests
```

Every run is also saved to the database (`data/jobs.db`, or Postgres when
`DATABASE_URL` is set), which is what the website reads.

## Sources

Company job boards, listed in `data/boards.csv` (about 31,500 verified boards):

| System | Public feed |
|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` |
| Lever | `api.lever.co/v0/postings/{slug}` |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` |
| Workday | `{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (keyword search) |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{id}/postings` (keyword search) |
| Workable | `apply.workable.com/api/v1/widget/accounts/{slug}` |
| Recruitee | `{slug}.recruitee.com/api/offers/` |
| Personio | `{slug}.jobs.personio.de/xml` |
| Teamtailor | `{slug}.teamtailor.com/jobs.rss` |
| BambooHR | `{slug}.bamboohr.com/careers/list` |
| Breezy HR | `{slug}.breezy.hr/json` |
| Zoho Recruit | `{slug}.zohorecruit.com/recruit/v2/public/Job_Openings` |
| Oracle Recruiting Cloud | `{host}.oraclecloud.com/hcmRestApi/.../recruitingCEJobRequisitions` (keyword search) |
| Rippling | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` |
| Manatal | `careers-page.com/api/v1.0/c/{slug}/jobs/` |
| Pinpoint | `{slug}.pinpointhq.com/postings.json` |

Open job sites: Himalayas (36 QA searches, the biggest source of matching jobs),
Arbeitnow, Jobicy, Remote OK, We Work Remotely, Remotive and Get on Board. These sites
ask to be credited, so every job keeps its source and the original posting URL. If the
same job is also on the company's own board, the company-board copy wins. Some open
sites re-date old postings when they are refreshed; when the scraper saw a job earlier,
that earlier date is used.

Manatal and Pinpoint publish no posted date. For those, the scraper remembers when it
first saw each job. On a board's first scan such jobs are "undated"; from the next run
on, a job that wasn't there before is dated the day it appeared.

The scraper identifies itself honestly in its User-Agent, only uses public feeds and
respects robots.txt and rate limits. LinkedIn, Indeed and Glassdoor are not scraped
because their terms forbid it. Sites that block the scraper are left alone.

## Adding boards

From Common Crawl (how most boards were found):

```bash
python harvest_commoncrawl.py --crawls 3      # board slugs from the 3 latest monthly crawls
python discover.py --from-candidates          # check each one, add the working boards
```

`harvest_commoncrawl.py` reads Common Crawl's public URL index files directly (the index
server is often overloaded) and writes `data/cc_candidates.csv`. `discover.py
--from-candidates` keeps a board only if it really returns open jobs.

From company names:

```bash
python discover.py                                   # names in data/seed_companies.txt
python discover.py --seeds data/qa_heavy_seeds.txt   # testing and outsourcing companies
python discover.py --from-feeds --skip-known         # companies posting QA jobs on job sites
python discover.py --prune                           # remove boards that stopped working
```

Workday boards go in `data/workday_seeds.txt` (`Company | careers URL`) and Oracle boards
in `data/oracle_seeds.txt`. For systems that don't state the employer's name (Lever,
Ashby, Personio, BambooHR, Zoho Recruit, Rippling, Manatal, Pinpoint, Workday), the name
is kept only if the board's own job descriptions mention it. Otherwise the board is
labelled `<slug> (name unverified)`, so no job is shown under the wrong employer.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `QA_MAX_AGE_DAYS` | 30 | keep jobs posted within this many days |
| `QA_REMOTE_ONLY` | 1 | 0 keeps hybrid and on-site jobs too |
| `QA_EXCLUDE_SENIOR` | 1 | 0 keeps senior, lead and manager roles |
| `QA_MAX_EXPERIENCE_YEARS` | 5 | drop jobs asking for more years than this |
| `QA_EXCLUDE_COUNTRIES` | India | comma-separated |
| `QA_MAX_CONCURRENCY` | 64 | requests in flight overall |
| `QA_PER_HOST` | 4 | requests in flight per host (big APIs have their own limits in config.py) |
| `QA_BOARDS_AT_ONCE` | 300 | boards processed at the same time |
| `DATABASE_URL` | (unset) | Postgres connection string; unset uses `data/jobs.db` |
| `RUN_PASSWORD` | (unset) | password for starting and cancelling runs on the website |

## Hosting

The website runs anywhere that can run a Python web app. Two modes exist because hosts
differ:

- `RUNNER=process` (default for `serve.py`): a run is started as a background process on
  the server, so the page can be closed while it runs.
- `RUNNER=batch` (for Vercel, where a request stops after a few minutes): the open page
  drives the run in slices, each scraping part of the boards within `STEP_SECONDS`.
  Slices are claimed safely, so several open pages can share one run.

Vercel deployment: `vercel.json` routes `/api/*` to `api/index.py` and serves `public/`.
Set `DATABASE_URL` (a free Neon Postgres database works), `RUN_PASSWORD` and
`RUNNER=batch`, then `vercel deploy --prod`. `.github/workflows/scrape.yml` can also run
the scraper on GitHub Actions where that is available.

## Layout

```
api/index.py            website API (FastAPI)
public/index.html       the website (one page, Tabulator table)
serve.py                run the website locally
run.py                  command-line runs
discover.py             find and verify boards
harvest_commoncrawl.py  board candidates from Common Crawl
qa_scraper/
  sources/              one file per job-board system
  feeds/                one file per open job site
  filters/              qa_match (is it software QA?), freshness, legitimacy, enrich
  pipeline.py           run orchestration and de-duplication
  batch.py              runs in slices (Vercel)
  store.py, db.py       runs, boards, jobs, NEW / closed tracking (SQLite or Postgres)
  http.py               async HTTP with per-host limits and retries
data/
  boards.csv            verified boards
  cc_candidates.csv     board candidates from Common Crawl
  seed_companies.txt    company names for discover.py
  qa_heavy_seeds.txt    testing and outsourcing companies
tests/                  python -m unittest discover tests
```
