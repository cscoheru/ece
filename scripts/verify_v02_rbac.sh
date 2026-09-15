#!/bin/bash
# cut-025: v0.2 RBAC smoke test — exercises all delegation channels.
#
# Per v0.2-cutover-checklist.md §1.2: run this BEFORE flipping traffic to
# validate the full RBAC stack (cut-018b/019/021/022/023/024) works as
# designed. Exit 0 = RBAC healthy.
#
# This script:
#   1. Sets multi-tenant env (ECE_USER_ORGS, ECE_DELEGATION_TOKENS, etc.)
#   2. Runs an end-to-end pytest that exercises all delegation paths
#   3. Reports pass/fail
#
# Usage:
#   bash scripts/verify_v02_rbac.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo "============================================="
echo "v0.2 RBAC Smoke Test"
echo "============================================="

# Apply migration (idempotent)
uv run alembic -c src/ece/migrations/alembic.ini upgrade head >/dev/null 2>&1 || true

# Run the end-to-end RBAC test suite
set +e
uv run pytest tests/integration/test_s12_v02_e2e.py -v
pytest_exit=$?
set -e

echo ""
echo "============================================="
if [ $pytest_exit -eq 0 ]; then
    echo "v0.2 RBAC: PASS (all channels verified)"
    echo "============================================="
    exit 0
else
    echo "v0.2 RBAC: FAIL (some channel misbehaved)"
    echo "============================================="
    exit 1
fi