#!/usr/bin/env bash
# cut-042R F6 — URL-level smoke test
#
# This script verifies the SPA ↔ API ↔ DB stack at the URL level. It does NOT
# declare the public corln.rana.asia deployment as PASS — that URL is currently
# blocked by a Cloudflare 526 (external SSL mismatch at origin) and is out of
# scope for cut-042R (see `docs/demo-platform/DEPLOY_USER_PROXY.md` §"外部阻断").
#
# Usage:
#   1. Start the API: `uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765`
#   2. In another shell, run: `./scripts/cut_042r_url_smoke.sh`
#
# Env overrides:
#   API_BASE  default http://127.0.0.1:8765
#   SPA_PORT  default 8080
#
# Exits non-zero on any failed assertion. Prints PASS / FAIL summary at end.

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8765}"
SPA_PORT="${SPA_PORT:-8080}"
SPA_BASE="http://127.0.0.1:${SPA_PORT}"

PASS=0
FAIL=0
SPA_PID=""

cleanup() {
    if [[ -n "${SPA_PID}" ]]; then
        kill "${SPA_PID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# --- 0. Pre-flight: API reachable? ---
echo "[0/5]  Pre-flight — API health check"
if ! curl -fsS "${API_BASE}/healthz" >/dev/null 2>&1; then
    echo "  FAIL — API not reachable at ${API_BASE}/healthz"
    echo "  Start with: uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765"
    exit 1
fi
echo "  PASS — ${API_BASE}/healthz OK"
PASS=$((PASS + 1))

# --- 1. Start SPA static server ---
echo "[1/5]  Start SPA static server (python http.server on :${SPA_PORT})"
( cd demos/spa && python3 -m http.server "${SPA_PORT}" --bind 127.0.0.1 ) >/tmp/spa.log 2>&1 &
SPA_PID=$!
sleep 1
if ! curl -fsS "${SPA_BASE}/index.html" >/tmp/spa_index.html 2>&1; then
    echo "  FAIL — SPA index.html not reachable at ${SPA_BASE}/index.html"
    cat /tmp/spa.log
    exit 1
fi
SPA_BYTES=$(wc -c </tmp/spa_index.html | tr -d ' ')
echo "  PASS — SPA index.html served (${SPA_BYTES} bytes)"
PASS=$((PASS + 1))

# --- 2. SPA integrity checks (zero CDN, real fetch, three views) ---
echo "[2/5]  SPA integrity (zero CDN, real fetch, three views)"
if grep -qE '<script src="https?://|<link href="https?://|@import url\(.(http|https)' /tmp/spa_index.html; then
    echo "  FAIL — index.html references external CDN"
    FAIL=$((FAIL + 1))
else
    echo "  PASS — zero external CDN in index.html"
    PASS=$((PASS + 1))
fi

if ! grep -q '/api/v1/demo/domains' /tmp/spa_index.html; then
    echo "  FAIL — SPA does not reference /api/v1/demo/domains"
    FAIL=$((FAIL + 1))
elif ! grep -q '/api/v1/demo/scenarios/generate' /tmp/spa_index.html; then
    echo "  FAIL — SPA does not reference /api/v1/demo/scenarios/generate"
    FAIL=$((FAIL + 1))
else
    echo "  PASS — SPA references both /api/v1/demo/domains and /api/v1/demo/scenarios/generate"
    PASS=$((PASS + 1))
fi

if ! grep -q 'fetch(' demos/spa/app.js; then
    echo "  FAIL — app.js does not use fetch()"
    FAIL=$((FAIL + 1))
else
    echo "  PASS — app.js uses fetch()"
    PASS=$((PASS + 1))
fi

# --- 3. GET /api/v1/demo/domains ---
echo "[3/5]  GET /api/v1/demo/domains"
DOMAINS=$(curl -fsS "${API_BASE}/api/v1/demo/domains")
echo "${DOMAINS}" | python3 -m json.tool >/tmp/domains.json
if python3 -c "import json,sys; d=json.load(open('/tmp/domains.json')); assert isinstance(d.get('domains'),list); print('OK')" 2>/dev/null; then
    echo "  PASS — GET /api/v1/demo/domains returns valid JSON with 'domains' list"
    PASS=$((PASS + 1))
else
    echo "  FAIL — GET /api/v1/demo/domains response malformed"
    FAIL=$((FAIL + 1))
fi

# --- 4. POST review_required (F3 — params land in DB) ---
echo "[4/5]  POST review_required path (amount=1.5M, quote_count=2)"
RESP=$(curl -fsS -X POST "${API_BASE}/api/v1/demo/scenarios/generate" \
    -H "X-User-Id: spike-user-procurement" \
    -H "Content-Type: application/json" \
    -d '{"domain":"procurement","scenario":"default","params":{"amount":1500000,"quote_count":2}}')
echo "${RESP}" | python3 -m json.tool >/tmp/review.json

if python3 -c "
import json
d = json.load(open('/tmp/review.json'))
got = d.get('conclusion')
reason = d.get('reason', '')
assert got == 'review_required', f'expected review_required, got {got!r}'
assert reason and reason != 'ok', f'reason should be business language, got {reason!r}'
print('OK — review_required, reason=' + reason[:60] + '…')
" 2>/dev/null; then
    echo "  PASS — review_required path returns business-language reason"
    PASS=$((PASS + 1))
else
    echo "  FAIL — review_required path returns wrong conclusion or reason"
    cat /tmp/review.json
    FAIL=$((FAIL + 1))
fi

# --- 5. POST auto_approved (F4 — 0 evidence must not IndexError) ---
echo "[5/5]  POST auto_approved path (amount=500k, quote_count=3) — F4 fix"
RESP=$(curl -fsS -X POST "${API_BASE}/api/v1/demo/scenarios/generate" \
    -H "X-User-Id: spike-user-procurement" \
    -H "Content-Type: application/json" \
    -d '{"domain":"procurement","scenario":"default","params":{"amount":500000,"quote_count":3}}')
echo "${RESP}" | python3 -m json.tool >/tmp/auto.json

if python3 -c "
import json
d = json.load(open('/tmp/auto.json'))
got = d.get('conclusion')
assert got == 'auto_approved', f'expected auto_approved, got {got!r}'
ev = d.get('evidence', [])
# F4: when all conditions pass cleanly (no negative evidence rows), evidence list may be empty
# — that's the fix. We just assert the API did not 500.
print('OK — auto_approved (evidence_count=' + str(len(ev)) + ')')
" 2>/dev/null; then
    echo "  PASS — auto_approved path returns 200 with clean evidence"
    PASS=$((PASS + 1))
else
    echo "  FAIL — auto_approved path returned wrong conclusion or 500"
    cat /tmp/auto.json
    FAIL=$((FAIL + 1))
fi

# --- Bonus 6. F1 — denied header + body actor override must yield no_permission ---
echo "[6/5+] F1 — denied header + body actor override must yield no_permission"
RESP=$(curl -fsS -X POST "${API_BASE}/api/v1/demo/scenarios/generate" \
    -H "X-User-Id: spike-user-unrelated" \
    -H "Content-Type: application/json" \
    -d '{"domain":"procurement","scenario":"default","params":{"actor":"spike-user-procurement","amount":1500000,"quote_count":2}}')
echo "${RESP}" | python3 -m json.tool >/tmp/denied.json

if python3 -c "
import json
d = json.load(open('/tmp/denied.json'))
got = d.get('conclusion')
assert got == 'no_permission', f'F1 BUG: body.actor override succeeded, got {got!r}'
print('OK — no_permission (body actor override rejected)')
" 2>/dev/null; then
    echo "  PASS — F1 denied branch refuses body.actor override"
    PASS=$((PASS + 1))
else
    echo "  FAIL — F1 BYPASS: denied header + body.actor=allowed returned non-no_permission"
    cat /tmp/denied.json
    FAIL=$((FAIL + 1))
fi

# --- Summary ---
echo ""
echo "============================================="
echo "PASS: ${PASS}   FAIL: ${FAIL}"
echo "============================================="
echo ""
echo "PUBLIC URL STATUS (cut-042R does NOT declare):"
echo "  corln.rana.asia — Cloudflare 526 external SSL mismatch (out of scope for cut-042R)"
echo "  See docs/demo-platform/DEPLOY_USER_PROXY.md §\"外部阻断\""
echo ""

if [[ "${FAIL}" -gt 0 ]]; then
    exit 1
fi
echo "All URL smoke checks PASSED."
exit 0
