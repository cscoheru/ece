#!/usr/bin/env bash
# cut-040 R40.5: E6 real-LLM gate with MiniMax minimax-m3.
#
# Per cut-039 §10 R40.5: prove E6 real-LLM reaches ≥80% direction + 100%
# evidence real-rate. Uses api.minimaxi.com (per memory note:
# Token Plan `sk-cp-` vs pay-as-you-go `sk-api-` share api.minimaxi.com).
#
# Usage:
#   export ECE_LLM_BASE_URL='https://api.minimaxi.com/v1'
#   export ECE_LLM_API_KEY='sk-cp-...'
#   export ECE_LLM_MODEL='minimax-m3'   # default if unset
#   bash scripts/verify_cut040_e6_minimax.sh
#
# Exit 0 = PASS (≥80% direction AND 100% evidence real-rate)
# Exit 1 = FAIL (below threshold OR other runner error)

set -euo pipefail

# Strict env guards (per "禁止编数" directive)
: "${ECE_LLM_BASE_URL:?cut-040 R40.5: ECE_LLM_BASE_URL must be set (default: https://api.minimaxi.com/v1)}"
: "${ECE_LLM_API_KEY:?cut-040 R40.5: ECE_LLM_API_KEY must be set (user-provided sk-cp-... key)}"
: "${ECE_LLM_MODEL:=minimax-m3}"  # default to MiniMax-M3

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E6_DATA="$REPO_ROOT/data/eval/e6_agent.json"
[ -f "$E6_DATA" ] || { echo "E6 data missing: $E6_DATA" >&2; exit 1; }

# Make sure API is up
API_URL="${API_URL:-http://127.0.0.1:8765}"
HEALTHZ=$(curl -s -o /dev/null -w '%{http_code}' "$API_URL/healthz" 2>/dev/null || echo "000")
if [ "$HEALTHZ" != "200" ]; then
    echo "API not reachable at $API_URL/healthz (code=$HEALTHZ)." >&2
    echo "Run: docker compose up -d api" >&2
    exit 1
fi

CASES=$(python3 -c "import json; print(len(json.load(open('$E6_DATA'))['cases']))")
echo "=== cut-040 R40.5 E6 real-LLM verification ==="
echo "  BASE_URL  = $ECE_LLM_BASE_URL"
echo "  MODEL     = $ECE_LLM_MODEL"
echo "  API       = $API_URL"
echo "  CASES     = $CASES"
echo "  THRESHOLD = ≥80% direction + 100% evidence real-rate"
echo "=========================================="

cd "$REPO_ROOT"
set +e
uv run python scripts/run_e6_agent.py \
    --data "$E6_DATA" \
    --base-url "$ECE_LLM_BASE_URL" 2>&1 | tail -25
EXIT=$?
set -e

if [ $EXIT -eq 0 ]; then
    echo
    echo "PASS: E6 real-LLM with $ECE_LLM_MODEL meets PRD §35 threshold"
    exit 0
else
    echo
    echo "FAIL: E6 runner exit $EXIT (expect 0; see output above for accuracy)"
    exit 1
fi
