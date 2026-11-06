"""Shared data structures."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class Board:
    """One company's job board on one job-board system (e.g. GitLab on Greenhouse)."""
    company: str
    ats: str                     # greenhouse, lever, ashby, workday, ...
    token: str                   # the board's id/slug on that system
    host: str = ""               # workday only: e.g. nvidia.wd5.myworkdayjobs.com
    site: str = ""               # workday only: e.g. NVIDIAExternalCareerSite
    careers_url: str = ""

    @property
    def key(self) -> str:
        return f"{self.ats}:{self.token}".lower()


@dataclass
class Job:
    title: str
    company: str
    job_url: str
    source: str                  # greenhouse, lever, remotive, ...
    source_kind: str = "company_ats"   # company_ats | aggregator
    board: str = ""              # board key, e.g. greenhouse:gitlab
    external_id: str = ""

    location: str = ""
    country: str = ""
    remote_type: str = ""        # Remote | Hybrid | Onsite | ""
    salary: str = ""
    posted_date: str = ""        # YYYY-MM-DD as stated by the source
    date_source: str = ""        # source | unknown
    days_old: int | None = None
    description: str = ""
    company_url: str = ""
    apply_url: str = ""

    # Filled by the filters / enrichment step.
    role_type: str = ""
    seniority: str = ""
    experience: str = ""
    tools: str = ""
    trust: str = ""              # company_ats | aggregator_verified | flagged
    trust_reasons: str = ""
    qa_match: str = ""           # why it was classified as QA

    # Source-specific details used during the run, not exported.
    detail_ref: dict = field(default_factory=dict, repr=False)

    def identity(self) -> str:
        if self.external_id:
            return f"{self.source}:{self.board}:{self.external_id}".lower()
        return self.job_url.split("?")[0].rstrip("/").lower()

    def dedupe_key(self) -> str:
        """Same role at the same company and place, posted on two sources."""
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
        return f"{norm(self.company)}|{norm(self.title)}|{norm(self.location)}"

    def as_row(self) -> dict:
        d = asdict(self)
        d.pop("detail_ref", None)
        return d
