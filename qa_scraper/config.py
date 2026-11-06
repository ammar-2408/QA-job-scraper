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
RETRIES = int(os.getenv("QA_RETRIES", "3"))

# A plain browser-like UA. No personal contact details are sent anywhere.
USER_AGENT = os.getenv(
    "QA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
)

# Hard cap on stored description length (Excel cell limit is 32,767).
MAX_DESC = 30000
