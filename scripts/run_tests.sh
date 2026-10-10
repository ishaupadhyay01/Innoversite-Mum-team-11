#!/usr/bin/env bash
# Run each service's test suite in isolation (every service has its own `app` package).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
status=0
for target in shared services/ingestion-service services/search-service services/rules-service services/gateway; do
  echo "=== $target"
  ( cd "$ROOT/$target" && PYTHONPATH="$ROOT/shared:$ROOT/$target${PYTHONPATH:+:$PYTHONPATH}" python -m pytest -q tests ) || status=1
done
exit $status
