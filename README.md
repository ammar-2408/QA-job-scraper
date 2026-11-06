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
python check_board.py lever spotify    # test one board
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

## Job-board systems

| System | Feed | Status |
|---|---|---|
| Greenhouse | `boards-api.greenhouse.io` | done |
| Lever | `api.lever.co` | done |
| Ashby | `api.ashbyhq.com/posting-api` | done |
| Workday, SmartRecruiters, Workable, Recruitee, Personio, Teamtailor, BambooHR, Breezy | public JSON feeds | next |
| Remote job sites (Remotive, RemoteOK, Arbeitnow, Himalayas, Jobicy, We Work Remotely) | public feeds | next |

LinkedIn, Indeed and Glassdoor are deliberately not scraped. Their terms forbid it.

## Adding boards

Add company names to `data/seed_companies.txt` and run `python discover.py`. It tries
each name on every supported system and adds a board to `data/boards.csv` only if
that board really returns jobs. If you already know a board's exact slug, write it
after a pipe: `Sauce Labs | saucelabs`.

## Layout

```
qa_scraper/
  sources/      one file per job-board system
  filters/      qa_match (is it QA?), freshness, legitimacy, enrich (extra columns)
  pipeline.py   run orchestration and de-duplication
  export.py     CSV files and the run report
  http.py       async HTTP with rate limits and retries
data/
  boards.csv            verified boards (written by discover.py)
  seed_companies.txt    company names for discover.py to try
```
