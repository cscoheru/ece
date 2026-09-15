#!/bin/bash
# cut-020: Real LLM + multi-tenant E6 + perf bench verification.
#
# Per EVALUATION.md §1 + ADR-009 SLA + cut-019 multi-tenant: real LLM E6
# runner must hit ≥80% accuracy AND multi-tenant perf bench must pass
# (p95 < 1.5s + cross-org denial rate 100%).
#
# Usage:
#   export ECE_LLM_BASE_URL="http://your-llm-endpoint/v1"
#   export ECE_LLM_API_KEY="your-key"
#   export ECE_LLM_MODEL="your-model"
#   export ECE_USER_ORGS="user1:org_a;user2:org_b"
#   bash scripts/bench_e6_real_llm_multi_tenant.sh
#
# Exit codes:
#   0 = all gates passed (perf + multi-tenant + E6 accuracy)
#   1 = some gate failed (cut-over blocked; investigate)

set -euo pipefail

# Required env
: "${ECE_LLM_BASE_URL:?ECE_LLM_BASE_URL not set (e.g. http://localhost:11434/v1)}"
: "${ECE_LLM_API_KEY:=EMPTY}"
: "${ECE_LLM_MODEL:=gpt-4}"
: "${ECE_USER_ORGS:?ECE_USER_ORGS not set (e.g. user1:org_a;user2:org_b)}"

# Repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo "============================================="
echo "v0.2 Real LLM + Multi-tenant Gate"
echo "============================================="
echo "BASE_URL:  $ECE_LLM_BASE_URL"
echo "MODEL:     $ECE_LLM_MODEL"
echo "USER_ORGS: $ECE_USER_ORGS"
echo "============================================="
echo

# 1. E6 runner (≥80% accuracy)
E6_DATA="data/eval/e6_agent.json"
if [ ! -f "$E6_DATA" ]; then
    echo "ERROR: $E6_DATA not found. Run scripts/gen_eval_datasets.py first." >&2
    exit 2
fi

echo "[1/2] E6 Runner — ≥80% accuracy"
echo "============================================="
set +e
uv run python scripts/run_e6_agent.py --data "$E6_DATA" --base-url "$ECE_LLM_BASE_URL"
e6_exit=$?
set -e
echo
if [ $e6_exit -ne 0 ]; then
    echo "FAIL: E6 accuracy <80%" >&2
    exit 1
fi
echo "PASS: E6 ≥80% accuracy"
echo

# 2. Multi-tenant perf bench (p95 < 1.5s + cross-org denial 100%)
echo "[2/2] Multi-tenant Perf Bench + Cross-org Verify"
echo "============================================="
set +e
uv run python scripts/bench_multi_tenant.py --n 200 --base-url "$ECE_LLM_BASE_URL"
bench_exit=$?
set -e
echo
if [ $bench_exit -ne 0 ]; then
    echo "FAIL: Multi-tenant bench failed" >&2
    exit 1
fi
echo "PASS: Multi-tenant bench"
echo

echo "============================================="
echo "v0.2 PASS: All gates met (E6 + Multi-tenant)"
echo "============================================="
exit 0