#!/bin/bash
# cut-018c: Real LLM ≥80% accuracy gate verification.
#
# Per EVALUATION.md §1 + cut-015b §1.2: real LLM E6 runner must hit ≥80%
# accuracy. This script sets ECE_LLM_* env and invokes the E6 runner
# against your configured OpenAI-compatible LLM endpoint.
#
# Usage:
#   export ECE_LLM_BASE_URL="http://your-llm-endpoint/v1"
#   export ECE_LLM_API_KEY="your-key"
#   export ECE_LLM_MODEL="your-model"
#   bash scripts/verify_e6_real_llm.sh
#
# Optional env (cut-015b defaults):
#   ECE_DELEGATION_TOKENS (not used by E6 runner; only for /audit /debug)
#   DEBUG_ALLOWED_HOSTS (not used by E6 runner; only for /debug)
#
# Exit codes:
#   0 = ≥80% accuracy (EVALUATION.md §1 SLA met)
#   1 = <80% accuracy (v0.1 cut-over blocked)

set -euo pipefail

# Required env
: "${ECE_LLM_BASE_URL:?ECE_LLM_BASE_URL not set (e.g. http://localhost:11434/v1)}"
: "${ECE_LLM_API_KEY:=EMPTY}"
: "${ECE_LLM_MODEL:=gpt-4}"

# Repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

# E6 dataset
E6_DATA="data/eval/e6_agent.json"
if [ ! -f "$E6_DATA" ]; then
    echo "ERROR: $E6_DATA not found. Run scripts/gen_eval_datasets.py first." >&2
    exit 2
fi

echo "============================================="
echo "v0.1 Real LLM E6 Accuracy Gate"
echo "============================================="
echo "BASE_URL: $ECE_LLM_BASE_URL"
echo "MODEL:   $ECE_LLM_MODEL"
echo "DATASET: $E6_DATA ($(python3 -c "import json; print(len(json.load(open('$E6_DATA'))['cases']))") cases)"
echo "============================================="

# Run E6 runner with real LLM
set +e
uv run python scripts/run_e6_agent.py --data "$E6_DATA" --base-url "$ECE_LLM_BASE_URL"
runner_exit=$?
set -e

# runner_exit 0 = ≥80% accuracy, 1 = <80%
if [ $runner_exit -eq 0 ]; then
    echo ""
    echo "============================================="
    echo "v0.1 PASS: E6 ≥80% accuracy met"
    echo "============================================="
    exit 0
else
    echo ""
    echo "============================================="
    echo "v0.1 FAIL: E6 <80% accuracy"
    echo "============================================="
    exit 1
fi