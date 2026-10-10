#!/usr/bin/env python3
"""Measure readiness and smoke-test a running Reg IRIS stack (standard library only).

Start the stack and this script together to measure real readiness time:

    docker compose up --build -d && python scripts/verify_setup.py

Checks: all services healthy, dataset import finished, keyword search returns a
cited paragraph, impact analysis runs, CSV export works, Swagger is served.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request


def request(api: str, path: str, body: dict | None = None, raw: bool = False):  # type: ignore[no-untyped-def]
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + path, data=data, method="POST" if body is not None else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    started = time.monotonic()
    results: list[tuple[str, bool, str]] = []

    print(f"Waiting for {args.api} to become ready ...")
    ready_after = None
    while time.monotonic() - started < args.timeout:
        try:
            status = request(args.api, "/api/system/status")
            imp = status.get("import") or {}
            if status["overall"] == "ok" and imp.get("status") in {"completed", "completed_with_errors"}:
                ready_after = time.monotonic() - started
                break
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError):
            pass
        time.sleep(2)
    if ready_after is None:
        print(f"NOT READY after {args.timeout} s")
        return 1
    results.append(("Services healthy and dataset imported", True, f"ready {ready_after:.0f} s after this script started"))

    search = request(args.api, "/api/search", {"query": "Counterparty LEI", "record_history": False})
    top = search["results"][0] if search["results"] else None
    results.append(
        (
            "Keyword search 'Counterparty LEI'",
            bool(top),
            f"{search['total']} hits in {search['took_ms']} ms; top: {top['citation']['document_name']} {top['citation']['version']}, {top['citation']['location_label']}"
            if top
            else "no results",
        )
    )
    run = request(args.api, "/api/impact-matrix", {"include_related_text": False})
    counts = run["summary"]["status_counts"]
    results.append(("Impact analysis", run["status"] == "completed", f"{counts} across {run['summary']['total_trades']} trades"))
    csv_bytes = request(args.api, f"/api/impact-matrix/{run['id']}/export?status=FAIL", raw=True)
    rows = csv_bytes.decode().strip().splitlines()
    results.append(("CSV export", len(rows) - 1 == counts["FAIL"], f"{len(rows) - 1} FAIL rows"))
    docs = request(args.api, "/api/docs", raw=True)
    results.append(("Swagger UI", b"swagger" in docs.lower(), "/api/docs served"))

    width = max(len(r[0]) for r in results)
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
