# Handoff: QA Job Scraper (read this fully before doing anything)

You are taking over an existing project mid-way. Everything below was built and
verified in a previous session. Read this file, then skim the code it points to,
then follow "Your first step" at the end.

---

## 1. The project in one paragraph

`D:\QA-job-scraper` is a Python scraper that collects **software QA / testing jobs
worldwide** that are **fresh** (posted within the last 7 days, configurable) and
**legitimate** (from the employer's own job board, or from an open job site after
scam checks). It uses **no API keys and no AI**: only public job-board feeds, and
rule-based filtering. Output today is CSV files plus a text run report.

- GitHub: `https://github.com/ammar-06/QA-job-scraper` (private), branch `main`.
- Owner: Ammar (GitHub `ammar-06`). Windows 11, Python 3.11, VS Code.
- Commits so far: Milestone 1 (b04aebb), Milestone 2 (b54d5bd), Milestone 3 (572e833).

### Hard rules from the user (do not break these)

1. **Never touch `D:\Scrapping_project`** (a separate legal-jobs scraper belonging to
   someone else's repo). Don't read its data into this project, don't commit or push
   anything there. All work happens in `D:\QA-job-scraper` only.
2. **No API keys, no paid services, no AI/LLM calls** in the scraper.
3. **Only public feeds.** Identify honestly in the User-Agent
   (`qa-job-scraper/0.x (+https://github.com/ammar-06/QA-job-scraper)`, set in
   `qa_scraper/config.py`). **Do not impersonate a browser or try to get around bot
   protection** (an attempt to send fake browser headers to get past a Workday 406
   was refused as bot-check circumvention; don't retry it).
4. **Do not scrape LinkedIn, Indeed or Glassdoor** (their terms forbid it).
   Rozee.pk was discussed: only consider it after checking its terms, and ask first.
5. Open job sites (Remotive, Remote OK, Jobicy, Arbeitnow, Himalayas, WWR) ask for
   attribution: always keep the source name and the original posting URL.
6. **Never invent data.** Blank is better than a guess (location, date, salary,
   company name).

### How the user likes to work

- For a big new phase: **explain the plan first and wait for "go"**. Then build.
- Give short progress updates; the user asks "update??" often during long runs.
- At the end of each phase: run the tests, do a full run, audit the results, then
  **commit and push to `main`** (this has been the pattern for every milestone).
  Commit messages describe what changed and the run numbers.
- The user writes casually with typos; read for intent.

---

## 2. What exists now

### Layout

```
D:\QA-job-scraper\
  run.py              full run -> output/*.csv + run report
                      flags: --max-age N, --ats a,b, --limit N, --no-feeds, --feeds-only, --quiet
  check_board.py      test one board: `python check_board.py lever spotify --all`
                      or one job site: `python check_board.py feed himalayas`
                      workday/oracle need --host and --site
  discover.py         find + verify boards -> data/boards.csv
                      --ats, --seeds, --skip-known, --from-feeds, --verify-names, --prune
  qa_scraper/
    config.py         MAX_AGE_DAYS, concurrency, USER_AGENT, SEARCH_TERMS, paths
    models.py         Board (company, ats, token, host, site) and Job dataclasses
    http.py           async httpx client: global + per-host semaphores, retries on 429/5xx,
                      never raises (returns None)
    text.py           html_to_text, iso_date, relative_date ("Posted 3 Days Ago"),
                      days_between, xml_text (BeautifulSoup has NO findtext())
    pipeline.py       orchestration: boards + feeds -> filters -> dedupe -> RunResult
    export.py         CSV files (utf-8-sig for Excel) + run_report_*.txt
    store.py          SQLite first-seen history (data/history.db, gitignored)
    sources/          one module per job-board system (see 2.2)
    feeds/            one module per open job site (see 2.3)
    filters/
      qa_match.py     is it a software QA job? (title tiers + description evidence)
      freshness.py    days_old stamp, <= max age
      legitimacy.py   trust: company_ats | aggregator_verified | flagged
      enrich.py       country, remote/hybrid/onsite, seniority, experience, tools, salary
  data/
    boards.csv          679 verified boards (company, ats, token, host, site, careers_url,
                        jobs_at_check, verified_on)
    seed_companies.txt  ~1,000 company names for discover.py ("Name | slug1, slug2")
    workday_seeds.txt   "Company | https://tenant.wdN.myworkdayjobs.com/Site" or just "Company"
    oracle_seeds.txt    "Company | https://host.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_n"
  tests/              python -m unittest discover tests   (16 tests, all passing)
  output/             run outputs (gitignored)
```

### 2.1 Run flow (`pipeline.run`)

For every board and feed, concurrently:
1. `list_jobs` (or `fetch` for feeds) -> list of `Job`.
2. **Title check** `qa_match.title_candidate` -> drop non-QA titles (cheap, before any
   detail request). Every QA-titled job is recorded in the store (first_seen/last_seen).
3. **Freshness** from the source's date; too old -> drop.
4. `fill_detail` if the source has one and the job lacks a description or a date
   (BambooHR, Zoho, Rippling only give dates on the detail).
5. No date at all -> **first-seen fallback**: earlier first_seen, or today if the board
   was already scanned on a previous day and the job is new. A board's very first scan
   never guesses: those jobs go to the "undated" file.
6. `qa_match.classify(title, description)` -> final QA decision.
7. `enrich`, then `legitimacy.assess`: flagged -> flagged file; undated -> undated file;
   else kept.
8. After all boards: drop open-site copies of jobs that exist on the company's own
   board, then dedupe by company + title + location.

### 2.2 Company job-board systems (16), all public JSON/XML/RSS, no key

| ats | feed | notes |
|---|---|---|
| greenhouse | `boards-api.greenhouse.io/v1/boards/{t}/jobs` (+ `/jobs/{id}` detail) | use `first_published`, NOT `updated_at` |
| lever | `api.lever.co/v0/postings/{t}?mode=json` | falls back to `api.eu.lever.co`; `createdAt` ms |
| ashby | `api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true` | `publishedAt` |
| workday | POST `{host}/wday/cxs/{tenant}/{site}/jobs` with `searchText` per term in `config.SEARCH_TERMS` | list gives "Posted N Days Ago"; detail gives `startDate`. Wrong tenant/host -> 422, right tenant wrong site -> 404 (used by discovery). Root URL always 406: do not try to bypass |
| smartrecruiters | `api.smartrecruiters.com/v1/companies/{id}/postings?q=` | keyword search; `releasedDate` |
| workable | `apply.workable.com/api/v1/widget/accounts/{slug}?details=true` | one entry per city: merged by shortcode |
| recruitee | `{slug}.recruitee.com/api/offers/` | `published_at` |
| personio | `{slug}.jobs.personio.de/xml?language=en` (or .com) | `createdAt` |
| teamtailor | `{slug}.teamtailor.com/jobs.rss` | `pubDate`, tt:locations |
| bamboohr | `{slug}.bamboohr.com/careers/list` + `/careers/{id}/detail` | list has no date; non-customers return HTML |
| breezy | `{slug}.breezy.hr/json` | description scraped from the public posting page `.description` |
| zohorecruit | `{slug}.zohorecruit.com/recruit/v2/public/Job_Openings?pagename=Careers` + `/Job_Openings/{id}?pagename=Careers` | also .in/.eu; unknown org -> 403 ORG_NOT_FOUND; keep jobs where `Publish` OR `Keep_on_Career_Site` is true |
| oraclehcm | `{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?...finder=findReqs;siteNumber=...,keyword=...` | newest first; JPMorgan Chase + Oracle so far |
| rippling | `api.rippling.com/platform/api/ats/v1/board/{slug}/jobs` (+ `/{uuid}`) | date only on detail |
| manatal | `www.careers-page.com/api/v1.0/c/{slug}/jobs/` | **no dates** -> first-seen |
| pinpoint | `{slug}.pinpointhq.com/postings.json` | **no dates** -> first-seen. Trial accounts serve demo postings ("Head of DEI - UK", "Marketing Manager", "Customer Service Rep"...): `_is_demo` rejects them |

### 2.3 Open job sites (`feeds/`)

Himalayas (search API, the biggest contributor), Arbeitnow (paged, newest first),
Jobicy (latest + tags `testing`/`tester`; tags must be 3-20 chars), Remote OK
(latest ~100), We Work Remotely (RSS, "Company: Title"), Remotive (its free API now
returns only 12 jobs; kept but low value).

### 2.4 Filters: what was learned from live audits

The QA classifier (`qa_match.py`) has: STRONG titles (QA Engineer, SDET, tester,
test automation, tool names like Playwright/Selenium/Cypress/Appium, test-infra),
MEDIUM ambiguous titles (Quality Assurance, Quality Engineer, Test Engineer,
Validation...) that need software context, and exclusion lists:
- `HARD_EXCLUDE`: other industries, ops/compliance "QA", pharma GxP/CSV, physical
  product testing. Overridden by software words in the title.
- `HARDWARE_EXCLUDE`: chip/electronics validation (GPU/SerDes/IC/SoC/ATE/pre-si,
  "Electrical Test Automation"). **Only "software"/"SW" in the title overrides it.**
- `ROLE_EXCLUDE`: other professions (marketer, product manager, producer, recruiter,
  customer/solutions/security engineer...). No override.
- `SOFT_EXCLUDE`: applies to MEDIUM titles only (so "QA Engineer - Growth" is kept).
- Description counts of software vs non-software (incl. chip-design) terms.

Every false positive/negative found in an audit was added to `tests/test_filters.py`
(`QA_TITLES` / `NOT_QA_TITLES`). **Keep doing that.** After any rule change, replay
the rules over the last saved `output/qa_jobs_*.csv` (it contains descriptions) to see
exactly what would be dropped, before re-running.

Legitimacy: company boards are trusted; only strong scam signs flag them (apply on
Telegram/WhatsApp, personal Gmail, reshipping, money transfer). Open-site jobs also
need a company name and a real description; a missing company website is only a note.

### 2.5 Discovery and data quality

- Systems that don't state the employer (lever, ashby, personio, bamboohr,
  zohorecruit, rippling, manatal, pinpoint): the seed name is kept only if the board's
  own job text mentions it; otherwise the company is labelled `<slug> (name
  unverified)`. 609 of 679 boards have verified names.
- Generic slugs ("unity", "square", "test") often belong to unrelated small companies.
- `--prune` re-checks every board and removes dead/demo ones.

### 2.6 Latest full run (2026-11-06)

685 sources (679 boards + 6 sites), 0 failures, 65,413 jobs read in ~280 s.
**338 fresh QA jobs** (+40 undated from Manatal/Pinpoint awaiting first-seen).
Top: US 84, India 75, multi-country remote 42, Poland 21, UK 15. Biggest sources:
Workday 142, Himalayas 117.
Pakistan: 237 Pakistan-located jobs are reachable (Zameen, Tkxel, Careem, Devsinc,
Educative...) but only ~5 are QA, none fresh. Pakistani QA hiring is mostly on Rozee.pk,
LinkedIn and companies' own sites (possible later work; ask the user).

### 2.7 Gotchas (each one cost time before)

- **Windows console is cp1252**: never print raw unicode; encode `ascii/replace`
  (the scripts already do this).
- **Don't write regex-containing Python through a bash heredoc with `\b`**: it turned
  into backspace characters (`\x08`) once and silently broke every word boundary.
  Use the Edit/Write tools for code with regexes, then verify (`chr(8) in source`).
- Python stdout is buffered in background runs; use `PYTHONUNBUFFERED=1`.
- `data/history.db` drives first-seen dates. Deleting it resets "NEW"/first-seen;
  only do that deliberately (it was reset once before the Milestone 3 baseline run).
- Full runs and discovery take minutes: run them in the background and report progress
  from the log when asked.
- Line-ending warnings (LF->CRLF) on commit are harmless.

---

## 3. What to build next (agreed in principle; confirm open questions first)

The user asked for: **a proper UI with a Run button that lists all jobs with
sorting and filtering, at least 1,000 job boards and at least 5,000 companies, and
every run must fetch the latest jobs.** The plan below was proposed to the user.

### Open questions: ask these FIRST, before building

1. **Local web app OK?** Proposed: runs on the user's PC, opens at
   `http://localhost:8000`. (A version reachable from anywhere needs hosting; later.)
2. **"1,000 job boards / 5,000 companies"**: proposed interpretation is **5,000+
   verified company boards** (each board = one company), which covers both numbers;
   the open job sites add more companies on top. If the user meant 1,000 separate job
   *sites* like Himalayas, say honestly that nowhere near that many have free public
   feeds, and re-plan.

### Phase A: Database and backend

- SQLite `data/jobs.db` (or extend `history.db`): tables `runs` (id, started, finished,
  status, counts, max_age, mode), `jobs` (identity PK + every Job field + first_seen,
  last_seen, status open/closed, closed_on, last_run_id), `boards` (key PK + last
  status, last_error, jobs_total, qa_jobs, last_scanned).
- Persist results at the end of each board's processing (not only at the end), so the
  UI can show jobs live.
- Open/closed: after a run, a job on a board that was scanned **successfully** but no
  longer lists it -> `closed`. Never close jobs of boards that failed this run.
- "NEW" = first_seen in this run.
- FastAPI app (`app/` or `qa_scraper/web/`): `POST /api/runs` (mode: full | quick |
  feeds; max_age), `GET /api/runs/current` (progress: boards done/total, jobs found,
  errors), `GET /api/runs` (history), `GET /api/jobs` (server-side filter/sort/search/
  pagination), `GET /api/jobs/{id}`, `GET /api/boards`, `GET /api/export.xlsx|csv`.
- Run the scrape in a background task/thread; only one run at a time.
- "Quick" run = job sites + boards that produced a QA job in the last N runs.
- Keep `run.py` working (CLI) on top of the same code.
- Add tests for open/closed and NEW logic.

### Phase B: UI

- Single HTML page served by FastAPI + a data-table library from a CDN (Tabulator was
  proposed). No heavy JS build.
- Run panel: Full / Quick / Job-sites-only, max-age picker, live progress bar, cancel.
- Jobs table: sort any column; filters for country, remote type, role type, seniority,
  tools, source/system, trust, days old, status (open/closed/new); global search over
  title/company/description; NEW and Closed badges; row click -> detail drawer with
  full description and "Open posting" link (keep source attribution visible).
- Export the filtered view to Excel (openpyxl) / CSV.
- Boards page (status, last error, counts) and Run history page.
- Works in light and dark mode; readable on a laptop screen.
- Start with one command, e.g. `python serve.py` (document it in the README).

### Phase C: Scale to 5,000+ verified boards

- Use the **Common Crawl URL index** (free, public, no key) to harvest real board URLs:
  list collections at `https://index.commoncrawl.org/collinfo.json`, then query e.g.
  `https://index.commoncrawl.org/CC-MAIN-<latest>-index?url=boards.greenhouse.io/*&output=json`
  (use `showNumPages` / `page` for paging; be gentle, it rate-limits). Do the same for
  `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, `apply.workable.com`,
  `*.recruitee.com`, `*.bamboohr.com`, `*.breezy.hr`, `*.teamtailor.com`,
  `*.jobs.personio.de`, `*.zohorecruit.com`, `*.myworkdayjobs.com` (tenant/wdN/site come
  straight from the URL), `ats.rippling.com`, `jobs.smartrecruiters.com`.
  Verify the exact query format live before relying on it.
- Extract slugs, dedupe, then verify each through the existing `discover.py` probe
  logic (must return real jobs; name verification; Pinpoint demo check). Add this as a
  new discover mode (e.g. `--from-commoncrawl`) and keep the harvested candidate list in
  a file so it can be re-verified later.
- Re-run `--prune`. Target: 5,000+ boards with jobs; report verified-name vs unverified
  counts honestly.

### Phase D: Keep full runs practical at 5,000 boards

- Expect roughly 15-30 min per full run. Raise overall concurrency (most boards are
  distinct hosts) while keeping per-host limits polite; keep keyword search for big
  employers (Workday/SmartRecruiters/Oracle); stream results to the DB/UI as boards
  finish. Measure and report the real run time.

### Phase E: Test, audit, ship

- Full run from the UI end to end; audit kept jobs for false positives (add any to the
  tests); check NEW/closed across two runs; update README; commit and push to `main`.

### Later (after the UI work)

- Remaining Milestone 4 item: scheduled runs (Windows Task Scheduler, or a schedule
  option in the UI).
- Pakistan coverage options (ask the user): custom scrapers for the top 20-30 Pakistani
  software houses' own careers pages, and Rozee.pk only if its terms allow it.

---

## 4. Your first step

1. Read the code: `qa_scraper/pipeline.py`, `qa_scraper/store.py`, `qa_scraper/models.py`,
   `discover.py`, one source (e.g. `sources/greenhouse.py`) and one feed.
2. Run `python -m unittest discover tests` and confirm 16 tests pass.
3. Then message the user: a short confirmation of what you understood, and the two
   **open questions** in section 3. Do not start building until they answer.
