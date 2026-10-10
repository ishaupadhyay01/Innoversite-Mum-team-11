#!/usr/bin/env python3
"""Trigger the (idempotent) dataset import through the API and follow its progress.

The import also runs automatically when the ingestion service starts; use this
script to re-run it or to watch it. Standard library only.

    python scripts/seed_data.py                     # gateway on http://localhost:8000
    python scripts/seed_data.py --api http://host:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def call(api: str, path: str, method: str = "GET", token: str | None = None) -> dict | None:
    req = urllib.request.Request(api + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        return json.loads(body) if body else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--token", default=None, help="API_TOKEN, if the gateway requires one")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    try:
        before = call(args.api, "/api/imports/latest")
        call(args.api, "/api/imports/run", "POST", args.token)
    except urllib.error.URLError as exc:
        print(f"Cannot reach the API at {args.api}: {exc}", file=sys.stderr)
        return 2
    previous_id = (before or {}).get("id")
    deadline = time.monotonic() + args.timeout
    seen = 0
    while time.monotonic() < deadline:
        run = call(args.api, "/api/imports/latest") or {}
        if run.get("id") != previous_id:
            for line in run.get("log", [])[seen:]:
                print(line)
            seen = len(run.get("log", []))
            if run.get("status") not in (None, "running"):
                print(
                    f"\nImport {run['status']}: {run['files_processed']} indexed, {run['files_skipped']} unchanged, {run['files_failed']} failed"
                )
                return 0 if run["status"] == "completed" else 1
        time.sleep(1)
    print("Timed out waiting for the import to finish", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
