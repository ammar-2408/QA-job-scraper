"""Posted within the last N days?"""
from __future__ import annotations

from .. import config
from ..models import Job
from ..text import days_between


def stamp(job: Job) -> None:
    job.days_old = days_between(job.posted_date)
    if job.days_old is None:
        job.date_source = "unknown"
    elif job.days_old < 0:          # time-zone skew: posted "tomorrow" means today
        job.days_old = 0


def is_fresh(job: Job, max_age: int | None = None) -> bool:
    """True only for jobs WITH a known date inside the window. Undated jobs are
    reported separately, never silently treated as fresh."""
    max_age = config.MAX_AGE_DAYS if max_age is None else max_age
    return job.days_old is not None and job.days_old <= max_age
