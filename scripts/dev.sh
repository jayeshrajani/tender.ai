#!/usr/bin/env bash
# Run API (8010), worker and web (3010) together. Ctrl+C stops all three.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
trap 'kill 0' EXIT INT TERM

(cd "$ROOT/apps/api" && .venv/bin/uvicorn app.main:app --reload --port 8010) &
(cd "$ROOT/apps/api" && PYTHONPATH="$ROOT/apps/worker" .venv/bin/python -m worker.main) &
(cd "$ROOT" && pnpm --filter @tenderos/web dev) &
wait
