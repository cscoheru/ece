#!/usr/bin/env bash
# cut-045 — One-shot reset of all demo fixtures.
#
# Scope lock: this resets the founder's OWN demo server's three-domain
# fixtures (procurement / knowledge / compliance). It does NOT touch any
# customer deployment.
#
# Per directive §4.1.4:
#   1. alembic upgrade head
#   2. seed procurement fixture (seed_v0_spike_fixture.py)
#   3. seed knowledge fixture (seed_knowledge_fixture.py)
#   4. seed compliance fixture (seed_compliance_fixture.py)
#
# Usage:
#   ./deploy/scripts/reset-demo-fixtures.sh
#
# Exit code 0 on success; non-zero on first failure (subsequent steps skipped).

set -euo pipefail

# Resolve the project root (this script lives in deploy/scripts/, repo root is ../..)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "${SCRIPT_DIR}/../.." && pwd )"

cd "${PROJECT_ROOT}"

# Use the project's virtualenv Python (same as `make test`).
if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

# Database URL fallback (env wins). The deploy .env is not auto-sourced here —
# operators set DATABASE_URL in the environment, or rely on the .venv defaults.
DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://ece:ece@127.0.0.1:55440/ece}"
export DATABASE_URL

echo "[reset] Running alembic upgrade head ..."
alembic upgrade head

echo "[reset] Seeding procurement fixture ..."
"${PYTHON}" scripts/seed_v0_spike_fixture.py

echo "[reset] Seeding knowledge fixture ..."
"${PYTHON}" scripts/seed_knowledge_fixture.py

echo "[reset] Seeding compliance fixture ..."
"${PYTHON}" scripts/seed_compliance_fixture.py

echo "[reset] All three fixtures reseeded. Demo ready."