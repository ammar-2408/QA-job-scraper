# QA Job Scraper

Collects software QA and testing jobs from company job boards worldwide and keeps
only the ones that are:

- **QA roles**: manual testers, automation testers, QA engineers and analysts, SDETs,
  game testers, performance testers, QA leads and managers, test-infrastructure
  engineers, and titles that name a testing tool (Selenium, Playwright, Cypress,
  Appium, JMeter and others).
- **Fresh**: posted in the last 7 days (configurable).
- **Legitimate**: taken from the employer's own job board, and checked for common
  job-scam signs (apply on Telegram or WhatsApp, apply to a personal Gmail address,
  pay-to-work schemes).

No API keys and no AI. Everything comes from public job-board feeds, and the
filtering uses rules you can read in `qa_scraper/filters/`.

## Setup

```bash
pip install -r requirements.txt
```

Python 3.11 or newer.

## Usage

```bash
python run.py                          # scrape every board in data/boards.csv
python run.py --max-age 3              # only jobs from the last 3 days
python run.py --ats greenhouse,lever   # only some job-board systems
python run.py --no-feeds               # company boards only
python run.py --feeds-only             # open job sites only
python check_board.py lever spotify    # test one board
python check_board.py feed himalayas   # test one job site
python discover.py                     # find more boards from data/seed_companies.txt
python -m unittest discover tests      # run the filter tests
```

Each run writes these files to `output/`:

| File | Contents |
|---|---|
| `qa_jobs_<time>.csv` | The result: fresh, legitimate QA jobs |
| `qa_jobs_undated_<time>.csv` | QA jobs whose source gives no posted date |
| `qa_jobs_flagged_<time>.csv` | QA jobs that failed the scam checks, kept for review |
| `boards_status_<time>.csv` | Which boards worked or failed, with job counts |
| `run_report_<time>.txt` | Counts at each filter step, by role type and country |

The CSV files open directly in Excel.

## Sources

**Company job boards** (listed in `data/boards.csv`):

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
| Zoho Recruit | `{slug}.zohorecruit.com/recruit/v2/public/Job_Openings` (common in Pakistan and India) |
| Oracle Recruiting Cloud | `{host}.oraclecloud.com/hcmRestApi/.../recruitingCEJobRequisitions` (keyword search) |
| Rippling | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` |
| Manatal | `careers-page.com/api/v1.0/c/{slug}/jobs/` |
| Pinpoint | `{slug}.pinpointhq.com/postings.json` |

Manatal and Pinpoint publish no posted date. For those (and any posting whose date
is missing) the scraper remembers when it first saw each job, in `data/history.db`.
On a board's first scan such jobs go to the "undated" file. From the next run on,
a job that wasn't there before is dated the day it appeared.

**Open job sites**: Himalayas, Arbeitnow, Jobicy, Remote OK, We Work Remotely and
Remotive. Anyone can post on these, so their jobs need a company name, a real
description and no scam signs before they are kept. If the same job is also on the
company's own board, the company-board copy wins. These sites ask to be credited,
so every row keeps its source and the original posting URL.

The scraper identifies itself honestly in its User-Agent and only uses public
feeds. LinkedIn, Indeed and Glassdoor are deliberately not scraped: their terms
forbid it.

## Adding boards

Add company names to `data/seed_companies.txt` and run `python discover.py`. It tries
each name on every supported system and adds a board to `data/boards.csv` only if
that board really returns jobs. If you already know a board's exact slug, write it
after a pipe: `Sauce Labs | saucelabs`.

Workday boards go in `data/workday_seeds.txt`, either as `Company | careers URL`
(checked directly) or just `Company` (the host and site name are guessed, which
works less often because Workday site names vary a lot). Oracle boards go in
`data/oracle_seeds.txt` as `Company | candidate-experience URL`.

`python discover.py --from-feeds` also probes every company currently advertising a
QA job on the open job sites, which is a good way to find employers that hire QA.
`--skip-known` skips companies that already have a board.

For systems that don't state the employer's name (Lever, Ashby, Personio, BambooHR,
Zoho Recruit, Rippling, Manatal, Pinpoint), discover.py keeps the seed name only if
the board's own job descriptions mention it. Otherwise the board is labelled
`<slug> (name unverified)`, so no job is ever shown under the wrong employer.

## Layout

```
qa_scraper/
  sources/      one file per job-board system
  feeds/        one file per open job site
  filters/      qa_match (is it QA?), freshness, legitimacy, enrich (extra columns)
  pipeline.py   run orchestration and de-duplication
  export.py     CSV files and the run report
  http.py       async HTTP with rate limits and retries
data/
  boards.csv            verified boards (written by discover.py)
  seed_companies.txt    company names for discover.py to try
  workday_seeds.txt     Workday careers URLs / company names for discover.py
```
