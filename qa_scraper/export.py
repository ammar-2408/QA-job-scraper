"""Write run results: CSV files (UTF-8 with BOM so Excel opens them correctly)
and a plain-text run report."""
from __future__ import annotations

import csv
import time
from pathlib import Path

from . import config
from .pipeline import RunResult

COLUMNS = [
    ("title", "Title"), ("company", "Company"), ("location", "Location"), ("country", "Country"),
    ("remote_type", "Remote / Hybrid / Onsite"), ("role_type", "Role Type"), ("seniority", "Seniority"),
    ("experience", "Experience"), ("salary", "Salary"), ("tools", "Tools"),
    ("posted_date", "Posted Date"), ("days_old", "Days Old"), ("source", "Job Board System"),
    ("board", "Board"), ("trust", "Trust"), ("trust_reasons", "Trust Notes"), ("job_url", "Job URL"),
    ("apply_url", "Apply URL"), ("qa_match", "Why Matched"), ("description", "Description"),
]


def _write(path: Path, jobs) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([label for _, label in COLUMNS])
        for j in jobs:
            row = j.as_row()
            w.writerow(["" if row.get(k) is None else row.get(k) for k, _ in COLUMNS])


def write_all(res: RunResult, max_age: int, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or config.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    paths = {
        "jobs": out_dir / f"qa_jobs_{stamp}.csv",
        "undated": out_dir / f"qa_jobs_undated_{stamp}.csv",
        "flagged": out_dir / f"qa_jobs_flagged_{stamp}.csv",
        "boards": out_dir / f"boards_status_{stamp}.csv",
        "report": out_dir / f"run_report_{stamp}.txt",
    }
    _write(paths["jobs"], res.kept)
    _write(paths["undated"], res.undated)
    _write(paths["flagged"], res.flagged)

    with open(paths["boards"], "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "ats", "token", "ok", "total_jobs", "qa_jobs_in_window", "kept", "seconds", "error"])
        for b in sorted(res.boards, key=lambda b: (not b.ok, b.board.key)):
            w.writerow([b.board.company, b.board.ats, b.board.token, b.ok, b.total_jobs, b.qa_jobs, b.kept,
                        b.seconds, b.error])

    ok = sum(1 for b in res.boards if b.ok)
    by_role, by_country = {}, {}
    for j in res.kept:
        by_role[j.role_type] = by_role.get(j.role_type, 0) + 1
        countries = [c for c in (j.country or "").split("; ") if c]
        if not countries:
            keys = ["Unknown / worldwide"]
        elif len(countries) > 3 or "more)" in j.country:
            keys = ["Multiple countries (region-wide remote)"]   # don't count one job 40 times
        else:
            keys = countries
        for c in keys:
            by_country[c] = by_country.get(c, 0) + 1
    lines = [
        f"QA job scraper - run {stamp}",
        f"Window: posted within the last {max_age} days",
        f"Boards: {len(res.boards)} total, {ok} OK, {len(res.boards) - ok} failed",
        f"Jobs seen on boards: {res.counts['jobs_seen']}",
        f"  not a QA title:            {res.counts['not_qa_title']}",
        f"  QA title but too old:      {res.counts['too_old']}",
        f"  rejected by description:   {res.counts['rejected_by_description']}",
        f"  flagged (legitimacy):      {res.counts['flagged']}",
        f"  QA but no posted date:     {res.counts['undated']}",
        f"  KEPT (before dedupe):      {res.counts['kept']}",
        f"Duplicates merged: {res.duplicates_merged}",
        f"FINAL QA JOBS: {len(res.kept)}",
        f"Run time: {res.seconds}s, HTTP errors: {res.counts['http_errors']}",
        "",
        "By role type:", *[f"  {k}: {v}" for k, v in sorted(by_role.items(), key=lambda x: -x[1])],
        "",
        "By source:", *[f"  {k}: {v}" for k, v in sorted(
            {s: sum(1 for j in res.kept if j.source == s) for s in {j.source for j in res.kept}}.items(),
            key=lambda x: -x[1])],
        "",
        "By country (top 25; a job open in several countries counts once per country):", *[f"  {k}: {v}" for k, v in sorted(by_country.items(), key=lambda x: -x[1])[:25]],
    ]
    failed = [b for b in res.boards if not b.ok]
    if failed:
        lines += ["", "Failed boards:", *[f"  {b.board.key}: {b.error}" for b in failed]]
    paths["report"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return paths
