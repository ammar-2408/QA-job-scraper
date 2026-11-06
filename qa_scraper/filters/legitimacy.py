"""Legitimacy (anti-scam) scoring.

A posting on a company's OWN job board (Greenhouse, Lever, Workday, ...) can only be
created by that employer, so it starts as trusted. Postings from open job sites
(aggregators) must additionally show a real company identity.

Both kinds are checked for classic job-scam signals; any hit -> trust = "flagged"
(kept in a separate file for review, never mixed into the clean output).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from ..models import Job

_I = re.IGNORECASE

SCAM_PATTERNS = [
    (r"\b(telegram|whats ?app|signal app|wechat)\b.{0,40}\b(apply|contact|interview|message|reach)", "contact via messaging app"),
    (r"\b(apply|contact|interview|message|reach)\b.{0,40}\b(telegram|whats ?app|wechat)\b", "contact via messaging app"),
    (r"\byou (must|will (need to|have to)|are required to|need to) (first )?(pay|purchase|buy)\b.{0,40}"
     r"\b(training|equipment|starter kit|registration|certification|software|laptop|kit)", "asks candidate to pay"),
    (r"\b(pay|send)\b.{0,15}\b(a |an |the )?(registration|training|processing|onboarding) fee\b", "asks candidate to pay"),
    (r"\bwe will (send|mail) you a (check|cheque)\b", "check/cheque scheme"),
    (r"\b(bitcoin|usdt|crypto ?currency)\b.{0,40}\b(salary|payment|paid)\b", "paid in crypto"),
    (r"\b(no (experience|interview) (needed|required))\b.{0,60}\$\s?\d{3,}", "no experience + high pay"),
    (r"\$\s?\d{3,}\s*(per|a|/)\s*(day|hour)\b.{0,60}\b(from home|no experience)", "unrealistic pay"),
    (r"\b(earn|make)\b.{0,20}\$\s?\d{1,3},?\d{3}\s*(per|a|/)\s*week\b", "unrealistic pay"),
    (r"\b(reshipping|re-shipping|package forwarding|parcel forwarding)\b", "reshipping scheme"),
    (r"\b(bank account|ssn|social security number|passport (copy|scan))\b.{0,40}\b(before|to apply|send)\b", "asks for sensitive data up front"),
    (r"\bmoney (transfer|mule)\b", "money transfer scheme"),
]
_SCAM = [(re.compile(p, _I), why) for p, why in SCAM_PATTERNS]
_FREE_MAIL = re.compile(r"[\w.+-]+@(gmail|yahoo|hotmail|outlook|aol|proton|protonmail|icloud|mail|yandex)\.(com|me|ru)\b", _I)


def _domain(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def assess(job: Job) -> None:
    reasons: list[str] = []
    text = f"{job.title}\n{job.description}"
    for rx, why in _SCAM:
        if rx.search(text) and why not in reasons:
            reasons.append(why)
    if _FREE_MAIL.search(job.description or ""):
        m = re.search(r"(apply|send|email|cv|resume).{0,60}" + _FREE_MAIL.pattern, job.description or "", _I)
        if m:
            reasons.append("apply via personal email address")

    notes: list[str] = []
    if job.source_kind == "aggregator":
        if not (job.company or "").strip():
            reasons.append("no company name")
        if not job.company_url:
            # Most job sites don't publish the employer's website at all, so this
            # alone is only a note, not a reason to drop the job.
            notes.append("no company website listed")
        if len(job.description or "") < 250:
            reasons.append("very short description")
        if job.apply_url and job.company_url:
            a, c = _domain(job.apply_url), _domain(job.company_url)
            ats_hosts = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "workable.com",
                         "smartrecruiters.com", "recruitee.com", "personio", "teamtailor.com", "bamboohr.com",
                         "breezy.hr", "jobvite.com", "icims.com")
            if a and c and c.split(".")[-2] not in a and not any(h in a for h in ats_hosts):
                reasons.append(f"apply link domain ({a}) differs from company ({c})")

    if job.source_kind == "company_ats":
        # Only the employer can post on its own board. Text patterns there are far
        # more likely to be innocent ("we deposit checks", "we pay for training"),
        # so only the unmistakable signals flag it; the rest are recorded as notes.
        if any(r in reasons for r in COMPANY_BOARD_RED_FLAGS):
            job.trust = "flagged"
        else:
            job.trust = "company_ats"
    elif reasons:
        job.trust = "flagged"
    else:
        job.trust = "aggregator_verified"
    job.trust_reasons = "; ".join(reasons + notes)


COMPANY_BOARD_RED_FLAGS = ("contact via messaging app", "apply via personal email address",
                           "reshipping scheme", "money transfer scheme")


def is_legit(job: Job) -> bool:
    return job.trust in ("company_ats", "aggregator_verified")
