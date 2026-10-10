#!/usr/bin/env python3
"""Load the hackathon sample dataset through the public API (exactly as a user would) and run an analysis.

    python3 scripts/seed_sample_data.py --base-url http://localhost:8080 [--token TOKEN]

Standard library only, so it runs anywhere Python 3.10+ is available.
Order: regulations (v1 before v2, using doc_metadata.csv) → rule files → trade CSV → impact run.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample_input"


class ApiHTTPError(Exception):
    def __init__(self, status: int, body: dict, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class Api:
    def __init__(self, base: str, token: str | None) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def _req(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None) -> dict:
        req = urllib.request.Request(self.base + path, data=body, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode(errors="replace")
            try:
                body = json.loads(payload)
            except json.JSONDecodeError:
                body = {}
            raise ApiHTTPError(exc.code, body, f"{method} {path} → HTTP {exc.code}: {payload}") from exc

    def get(self, path: str) -> dict:
        return self._req("GET", path)

    def post_json(self, path: str, data: dict) -> dict:
        return self._req("POST", path, json.dumps(data).encode(), "application/json")

    def post_files(self, path: str, file_path: Path, fields: dict[str, str] | None = None) -> dict:
        boundary = uuid.uuid4().hex
        parts: list[bytes] = []
        for k, v in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n".encode()
            + file_path.read_bytes()
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return self._req("POST", path, b"".join(parts), f"multipart/form-data; boundary={boundary}")


def wait_until(predicate, what: str, timeout: float = 120) -> None:  # type: ignore[no-untyped-def]
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return
        except (ApiHTTPError, OSError):
            pass
        time.sleep(1.5)
    raise SystemExit(f"Timed out waiting for {what}")


def iso_date(ddmmyy: str) -> str:
    return datetime.strptime(ddmmyy, "%d-%m-%y").date().isoformat()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--token", default=None)
    args = ap.parse_args()
    api = Api(args.base_url, args.token)

    wait_until(lambda: api.get("/api/v1/documents?size=1") is not None, "ingestion API")
    wait_until(lambda: api.get("/api/v1/rule-sets") is not None, "rules API")

    # 1. Regulations, in metadata order so v2 is uploaded as a new version of v1
    doc_by_meta_id: dict[str, str] = {}
    with (DATA / "metadata" / "doc_metadata.csv").open(encoding="utf-8") as fh:
        rows = sorted(csv.DictReader(fh), key=lambda r: int(r["document_id"]))
    for row in rows:
        path = DATA / "regulations" / row["file_name"]
        fields = {"effective_date": iso_date(row["effective_date"]), "version_label": row["version"]}
        try:
            if row["parent_doc_id"]:
                doc_id = doc_by_meta_id[row["parent_doc_id"]]
                res = api.post_files(f"/api/v1/documents/{doc_id}/versions", path, fields)
            else:
                fields |= {
                    "regulator": row["regulator"],
                    "jurisdiction": row["jurisdiction"],
                    "category": row["category"],
                    "title": f"{row['regulator']} — {row['category']}",
                }
                res = api.post_files("/api/v1/documents", path, fields)
            version_id, document_id = res["version"]["id"], res["document"]["id"]
        except ApiHTTPError as exc:  # re-running the seed: reuse what is already there
            details = exc.body.get("error", {}).get("details", {})
            if exc.status != 409 or "version_id" not in details:
                raise SystemExit(str(exc)) from exc
            version_id, document_id = details["version_id"], details["document_id"]
        doc_by_meta_id[row["document_id"]] = document_id
        wait_until(
            lambda vid=version_id: api.get(f"/api/v1/versions/{vid}")["processing_status"] in ("READY", "FAILED"),
            f"processing of {row['file_name']}",
        )
        v = api.get(f"/api/v1/versions/{version_id}")
        print(
            f"  ✓ {row['file_name']:<32} {v['version_label']:<6} {v['status']:<8} {v['clause_count']} clauses"
            + (f"  ⚠ {v['quality_warnings'][0]}" if v.get("quality_warnings") else "")
        )

    # Wait until search-service has indexed every version, so rules can be auto-linked to clauses.
    total_versions = sum(1 for _ in rows)
    wait_until(
        lambda: len([s for s in api.get("/api/v1/search/index-status") if s["keyword_indexed"]]) >= total_versions,
        "search indexing",
        timeout=180,
    )
    print(f"  ✓ search index ready ({total_versions} versions)")

    # 2. Rule files
    for rules_file in sorted((DATA / "rules").glob("*.json")):
        rs = api.post_files("/api/v1/rule-sets", rules_file)["rule_set"]
        warnings = [i for i in rs["lint"] if i["level"] != "INFO"]
        print(
            f"  ✓ {rules_file.name:<32} {rs['regulator']:<9} {rs['rule_count']} rules"
            + (f"  ⚠ {len(warnings)} lint warning(s)" if warnings else "")
        )

    # Give the asynchronous rule → clause linking a moment so the run snapshot carries citations.
    time.sleep(3)

    # 3. Trades + run
    ds = api.post_files("/api/v1/datasets", DATA / "trades" / "sample_trades.csv")["dataset"]
    print(f"  ✓ sample_trades.csv                {ds['row_count']} rows, {ds['status']}")
    run = api.post_json("/api/v1/runs", {"dataset_id": ds["id"]})
    wait_until(lambda: api.get(f"/api/v1/runs/{run['id']}")["status"] in ("COMPLETED", "FAILED"), "impact run")
    stats = api.get(f"/api/v1/runs/{run['id']}/stats")
    print(
        f"\nImpact run {run['id']}: {stats['passed']} PASS / {stats['failed']} FAIL / "
        f"{stats['not_applicable']} N/A — {stats['trades_with_failures']} of {stats['total_trades']} trades need action"
    )
    print(f"Open {args.base_url}/impact/runs/{run['id']}")


if __name__ == "__main__":
    sys.exit(main())
