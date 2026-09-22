#!/usr/bin/env bash
# cut-045R1 — One-shot reset of all demo fixtures (R3-B2 fix).
#
# Scope lock: this resets the founder's OWN demo server's three-domain
# fixtures (procurement / knowledge / compliance). It does NOT touch any
# customer deployment.
#
# R3-B2 fix (Codex R1 HOLD): the demo compose database is NOT published on
# any host port. alembic and seed scripts therefore run INSIDE the api
# container via `docker compose run --rm api ...`. The previous version
# of this script connected to 127.0.0.1:55440 — a port that no longer
# exists on a fresh deployment, so a fresh clone + fresh server would
# fail at step 5 of the runbook.
#
# R3-B2 also requires that this script works without a host-installed
# Python venv (operators on the demo server only need docker).
#
# Steps (per directive §4.1.4):
#   1. alembic upgrade head           (inside api container)
#   2. seed_v0_spike_fixture.py       (procurement)
#   3. seed_knowledge_fixture.py      (knowledge management)
#   4. seed_compliance_fixture.py     (compliance audit)
#
# Usage:
#   ./deploy/scripts/reset-demo-fixtures.sh
#
# Required environment:
#   - docker compose v2 on PATH
#   - the ece repo cloned at the path matching deploy/docker-compose.demo.yml
#   - deploy/.env present (from `cp deploy/.env.example deploy/.env`)
#
# Exit code 0 on success; non-zero on first failure.

set -euo pipefail

# Resolve the project root (this script lives in deploy/scripts/, repo root is ../..)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "${SCRIPT_DIR}/../.." && pwd )"

cd "${PROJECT_ROOT}"

# Use docker compose v2. Operators must have this on PATH.
COMPOSE_FILE="deploy/docker-compose.demo.yml"
if ! command -v docker >/dev/null 2>&1; then
    echo "[reset] FATAL: docker not found on PATH" >&2
    exit 2
fi

# Confirm the compose file exists at the expected path.
if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "[reset] FATAL: ${COMPOSE_FILE} not found (run from repo root or adjust path)" >&2
    exit 2
fi

# Confirm the api service is up. If not, the runbook step 4 was skipped.
if ! docker compose -f "${COMPOSE_FILE}" ps api --status running >/dev/null 2>&1; then
    # `ps` may exit 1 if no services are running; fall back to a simpler probe
    if ! docker compose -f "${COMPOSE_FILE}" ps 2>/dev/null | grep -qE '\bapi\b.*\bUp\b'; then
        echo "[reset] FATAL: api service is not running." >&2
        echo "[reset] Start it first: docker compose -f ${COMPOSE_FILE} --env-file deploy/.env up -d" >&2
        exit 3
    fi
fi

# Confirm DATABASE_URL is reachable from the api container. If not, abort
# with a clear error (the runbook step 4 healthcheck should have caught it).
if ! docker compose -f "${COMPOSE_FILE}" exec -T api \
        python -c "import os,sys; from urllib.parse import urlparse; u=urlparse(os.environ['DATABASE_URL']); sys.exit(0 if u.hostname else 1)" \
        >/dev/null 2>&1; then
    echo "[reset] FATAL: api container has no DATABASE_URL set" >&2
    exit 4
fi

echo "[reset] R3-B2: all migrations and seeds run INSIDE the api container"
echo "[reset] Running alembic upgrade head ..."
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head

echo "[reset] Seeding procurement fixture ..."
docker compose -f "${COMPOSE_FILE}" run --rm api \
    python scripts/seed_v0_spike_fixture.py

echo "[reset] Seeding knowledge fixture ..."
docker compose -f "${COMPOSE_FILE}" run --rm api \
    python scripts/seed_knowledge_fixture.py

echo "[reset] Seeding compliance fixture ..."
docker compose -f "${COMPOSE_FILE}" run --rm api \
    python scripts/seed_compliance_fixture.py

echo "[reset] All three fixtures reseeded. Demo ready."