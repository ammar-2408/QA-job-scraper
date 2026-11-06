"""Deploy the website to a Hugging Face Space (Docker) from the command line.

  set HF_TOKEN=hf_...                (a Write token from huggingface.co/settings/tokens)
  python deploy/deploy_hf.py --database-url postgresql://... --password <run password>
  python deploy/deploy_hf.py         # later deploys: just uploads the code again

Creates the Space (private) on first use, stores DATABASE_URL and RUN_PASSWORD as
Space secrets (never in the code), and uploads the project files.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
IGNORE = ["output/**", "data/*.db", "data/*.db-*", "data/seed_companies.txt", "data/*_seeds.txt", "docs/**",
          "tests/**", ".github/**", "**/__pycache__/**", "*.pyc", ".git/**", ".vscode/**", "README.md",
          ".vercelignore", "vercel.json", "deploy/**", "*.log"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--space", default="qa-job-finder", help="Space name (default qa-job-finder)")
    ap.add_argument("--database-url", help="Postgres connection string (stored as a secret)")
    ap.add_argument("--password", help="password for the Run button (stored as a secret)")
    ap.add_argument("--public", action="store_true", help="make the Space public (default private)")
    args = ap.parse_args()

    token = os.getenv("HF_TOKEN")
    if not token:
        print("Set HF_TOKEN first (a Write token from https://huggingface.co/settings/tokens).")
        return 1
    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo = f"{user}/{args.space}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", private=not args.public, exist_ok=True)
    if args.database_url:
        api.add_space_secret(repo, "DATABASE_URL", args.database_url)
    if args.password:
        api.add_space_secret(repo, "RUN_PASSWORD", args.password)
    api.add_space_variable(repo, "RUNNER", "process")

    api.upload_folder(folder_path=str(ROOT), repo_id=repo, repo_type="space", ignore_patterns=IGNORE,
                      commit_message="Deploy QA Job Finder")
    api.upload_file(path_or_fileobj=str(ROOT / "deploy" / "space_README.md"), path_in_repo="README.md",
                    repo_id=repo, repo_type="space", commit_message="Space settings")
    host = f"{user}-{args.space}".lower().replace("_", "-")
    print(f"Space:   https://huggingface.co/spaces/{repo}")
    print(f"Website: https://{host}.hf.space")
    return 0


if __name__ == "__main__":
    sys.exit(main())
