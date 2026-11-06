"""Run the website on this computer (same app that Vercel hosts).

  python serve.py            # http://localhost:8000, Run button starts run.py locally
  python serve.py --port 9000

Uses data/jobs.db unless DATABASE_URL is set (then it shows the online database).
"""
import argparse
import os
import webbrowser

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("LOCAL_RUNNER", "1")
    os.makedirs("output", exist_ok=True)
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")
    uvicorn.run("api.index:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
