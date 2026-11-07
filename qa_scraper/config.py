"""Central settings. Every value can be overridden with an environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / os.getenv("QA_OUTPUT_DIR", "output")
BOARDS_CSV = DATA_DIR / "boards.csv"

# Only keep postings at most this many days old.
MAX_AGE_DAYS = int(os.getenv("QA_MAX_AGE_DAYS", "30"))

# Network behaviour.
REQUEST_TIMEOUT = float(os.getenv("QA_REQUEST_TIMEOUT", "30"))
MAX_CONCURRENCY = int(os.getenv("QA_MAX_CONCURRENCY", "64"))   # requests in flight overall
PER_HOST_CONCURRENCY = int(os.getenv("QA_PER_HOST", "4"))      # requests in flight per host
BOARD_CONCURRENCY = int(os.getenv("QA_BOARDS_AT_ONCE", "300"))  # boards being processed at the same time
# Shared API hosts serve thousands of boards each: big public APIs get a few more parallel
# requests, hosts known to rate-limit get fewer. Everything else uses PER_HOST_CONCURRENCY.
HOST_LIMITS = {
    "boards-api.greenhouse.io": 10, "api.ashbyhq.com": 8, "api.lever.co": 6, "api.eu.lever.co": 4,
    "api.smartrecruiters.com": 6, "api.rippling.com": 6, "apply.workable.com": 2, "www.careers-page.com": 1,
}
RETRIES = int(os.getenv("QA_RETRIES", "3"))

# Identify honestly as a scraper (no browser impersonation, no personal contact details).
USER_AGENT = os.getenv("QA_USER_AGENT", "qa-job-scraper/0.2 (+https://github.com/ammar-06/QA-job-scraper)")

# Keyword searches sent to job boards that support server-side search (Workday,
# SmartRecruiters). Results are still classified by qa_match; this only avoids
# downloading thousands of unrelated postings from very large employers.
SEARCH_TERMS = ["QA", "quality assurance", "test", "tester", "testing", "SDET", "quality engineer", "automation"]

# Keep only fully remote jobs (hybrid, on-site and jobs with no clear remote statement are dropped).
REMOTE_ONLY = os.getenv("QA_REMOTE_ONLY", "1") != "0"

# Level: drop senior / lead / staff / principal / manager / director titles, and jobs whose
# description asks for more than MAX_EXPERIENCE_YEARS years (interns, juniors and mid-level stay).
EXCLUDE_SENIOR = os.getenv("QA_EXCLUDE_SENIOR", "1") != "0"
MAX_EXPERIENCE_YEARS = int(os.getenv("QA_MAX_EXPERIENCE_YEARS", "5"))

# Jobs only open in these countries are dropped. A job open in a long list of countries
# (region-wide remote, more than 3) is kept even if the list includes one of them.
# Only keep remote jobs that someone living here can apply to: worldwide jobs, jobs open to this
# country or to a region that contains it. Empty = keep remote jobs limited to any country.
APPLY_FROM = os.getenv("QA_APPLY_FROM", "Pakistan").strip()
APPLY_FROM_REGIONS = [r.strip() for r in os.getenv(
    "QA_APPLY_FROM_REGIONS", "Asia,South Asia,APAC,Asia Pacific,Asia-Pacific,MENAP,Middle East and South Asia").split(",")
    if r.strip()]
EXCLUDE_COUNTRIES = [c.strip() for c in os.getenv("QA_EXCLUDE_COUNTRIES", "India").split(",") if c.strip()]

# Hard cap on stored description length (Excel cell limit is 32,767).
MAX_DESC = 30000
