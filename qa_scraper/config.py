"""Central settings. Every value can be overridden with an environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / os.getenv("QA_OUTPUT_DIR", "output")
BOARDS_CSV = DATA_DIR / "boards.csv"

# Only keep postings at most this many days old.
MAX_AGE_DAYS = int(os.getenv("QA_MAX_AGE_DAYS", "7"))

# Network behaviour.
REQUEST_TIMEOUT = float(os.getenv("QA_REQUEST_TIMEOUT", "30"))
MAX_CONCURRENCY = int(os.getenv("QA_MAX_CONCURRENCY", "24"))   # requests in flight overall
PER_HOST_CONCURRENCY = int(os.getenv("QA_PER_HOST", "4"))      # requests in flight per host
BOARD_CONCURRENCY = int(os.getenv("QA_BOARDS_AT_ONCE", "150"))  # boards being processed at the same time
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

# Hard cap on stored description length (Excel cell limit is 32,767).
MAX_DESC = 30000
