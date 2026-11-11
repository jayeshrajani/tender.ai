#!/usr/bin/env bash
# One-time local setup without Docker: Python venv, web deps, databases, migrations, DEMO seed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3.12}"

echo "→ Python environment"
cd "$ROOT/apps/api"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"

echo "→ Web dependencies"
cd "$ROOT"
pnpm install

echo "→ Databases (needs a running PostgreSQL ≥ 15 on localhost)"
for db in tenderos tenderos_test; do
  psql -h localhost -d postgres -Atc "select 1 from pg_database where datname='$db'" | grep -q 1 || createdb -h localhost "$db"
done

echo "→ Migrations + DEMO seed"
cd "$ROOT/apps/api"
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed

echo "Done. Run: pnpm dev"
