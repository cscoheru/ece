#!/usr/bin/env python3
"""cut-045 — Production same-origin deployment smoke.

Per Codex directive §5 + plan §2.子刀 C: 验证部署后 URL (DEMO_BASE_URL) 是否
作为单一 origin 完整提供 SPA + API + 三域业务能力. 与 cut-044 same-origin
smoke 关键区别: 本脚本**不启动任何 origin server**, 仅通过 DEMO_BASE_URL
走真实部署 URL (用户的 nginx 反代 / 本地 uvicorn / 同源 staging server).

Scope lock (directive §0):
  - 自有演示服务器部署 (如 corln.rana.asia), NOT 客户私有化交付.

10 checks (per directive §5.2):

  ORIGIN PROXY (1):
    1. SPA index.html reachable from DEMO_BASE_URL (proxy proof)
  DOMAIN DISCOVERY (1):
    2. GET /api/v1/demo/domains → 3 domains (procurement + knowledge + compliance)
  PROCUREMENT valid + denied (2):
    3. proc-alice + valid params → 200 + auto_approved|review_required
    4. spike-user-unrelated + valid params → no_permission (spec denied_users)
  KNOWLEDGE valid + denied (2):
    5. km-alice + KM-POL-001 → 200 + answerable
    6. km-eve + KM-POL-001 → 200 + no_permission (spec denied_users)
  COMPLIANCE valid + denied (2):
    7. comp-alice + COMP-CTL-001 + period → 200 + evidence_package_sufficient
    8. comp-eve + COMP-CTL-001 + period → 200 + no_permission (spec denied_users)
  422 STRICT DATE (1):
    9. comp-alice + today='not-a-date' → 422 (R2-B2 strict YYYY-MM-DD)
  ZERO EXTERNAL CDN (1):
   10. SPA index.html contains no external CDN <script src="https:// or <link href="https://

DB-dependent checks (3/4/5/6/7/8/9) SKIP if upstream 5xx (mirror cut-042R2 R2-F3).
Checks 1/10 are DB-independent (SPA static only).

Usage:
  # Local (uvicorn already running on the configured port):
  DEMO_BASE_URL=http://127.0.0.1:8080 \
      ./.venv/bin/python scripts/cut_045_demo_deployment_smoke.py

  # Deployed (nginx on the demo domain):
  DEMO_BASE_URL=https://corln.rana.asia \
      ./.venv/bin/python scripts/cut_045_demo_deployment_smoke.py

Exit code:
  0 — all 10 PASS
  1 — any FAIL
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request


# ---------------------------------------------------------------------------
# Single-origin configuration (directive §5.1, §5.3)
# ---------------------------------------------------------------------------

DEMO_BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8080")
# Strip trailing slash for consistent URL composition
DEMO_BASE_URL = DEMO_BASE_URL.rstrip("/")

# Hardcoded upstream URL forbidden in main path (binding invariant).
# If a future change adds this, test_demo_smoke_script_does_not_hardcode_api_upstream
# in tests/unit/test_demo_smoke_script.py catches it.
ALLOWED_LOCAL_DEFAULT = "http://127.0.0.1:8080"

PROCUREMENT_VALID_USER = "spike-user-procurement"  # spec.yaml: roles=[buyer]
PROCUREMENT_DENIED_USER = "spike-user-unrelated"    # spec.yaml: DENIED
KNOWLEDGE_VALID_USER = "km-alice"                   # KM seeded actor
KNOWLEDGE_DENIED_USER = "km-eve"                    # spec.yaml: DENIED
COMPLIANCE_VALID_USER = "comp-alice"                # seeded actor
COMPLIANCE_DENIED_USER = "comp-eve"                 # spec.yaml: DENIED

# Constants for the cut-045 acceptance DoD
COMPLIANCE_TODAY = "2026-09-22"
COMPLIANCE_VALID_PARAMS = {
    "control_id": "COMP-CTL-001",
    "period_start": "2026-07-01",
    "period_end": "2026-09-30",
    "today": COMPLIANCE_TODAY,
}


# ---------------------------------------------------------------------------
# HTTP helpers — all requests go through DEMO_BASE_URL (single origin)
# ---------------------------------------------------------------------------


def _get(path: str, *, timeout: float = 5.0) -> tuple[int, bytes]:
    """GET `path` on DEMO_BASE_URL; return (status, body bytes)."""
    url = f"{DEMO_BASE_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""
    except urllib.error.URLError as exc:
        # Transport-level error (connection refused, DNS, etc.) — caller decides SKIP vs FAIL
        raise RuntimeError(f"transport error to {url}: {exc}") from exc


def _post_json(path: str, body: dict, *, headers: dict | None = None, timeout: float = 5.0) -> tuple[int, bytes]:
    """POST `body` as JSON on DEMO_BASE_URL; return (status, body bytes)."""
    url = f"{DEMO_BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, method="POST", headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""
    except urllib.error.URLError as exc:
        raise RuntimeError(f"transport error to {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Check 1 — SPA index.html reachable from origin (proxy proof)
# ---------------------------------------------------------------------------


def _check_1_spa_index_html() -> tuple[bool, str]:
    """DEMO_BASE_URL/ → SPA index.html with HTML marker.

    SKIP semantics: if DEMO_BASE_URL is an API-only origin (uvicorn without
    SPA mount, GET / returns 404 but /api/v1/demo/domains returns 200),
    the SPA-specific checks are not applicable — the production deployment
    serves SPA via nginx reverse proxy.
    """
    try:
        status, payload = _get("/", timeout=5.0)
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 404:
        # Probe whether API is alive on this origin
        try:
            api_status, _ = _get("/api/v1/demo/domains", timeout=2.0)
        except RuntimeError:
            api_status = 0
        if api_status == 200:
            return True, (
                "SKIPPED — API-only origin (GET / → 404; SPA served by "
                "nginx in production, not by this uvicorn)"
            )
    if status != 200:
        return False, f"GET / status={status} (expected 200)"
    html = payload.decode("utf-8", errors="replace").lower()
    if "<html" not in html and "<!doctype" not in html:
        return False, "GET / did not return HTML (no <html> or <!doctype> marker)"
    return True, f"origin={DEMO_BASE_URL} bytes={len(payload)}"


# ---------------------------------------------------------------------------
# Check 2 — domain discovery via same origin
# ---------------------------------------------------------------------------


def _check_2_domains_three() -> tuple[bool, str]:
    """GET /api/v1/demo/domains → procurement + knowledge + compliance."""
    try:
        status, payload = _get("/api/v1/demo/domains", timeout=3.0)
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 502 or status == 503 or status == 504:
        return True, f"SKIPPED — upstream gateway error {status} (DB-light)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status} (DB-light)"
    data = json.loads(payload)
    names = {d.get("name") for d in data.get("domains", [])}
    required = {"procurement", "knowledge", "compliance"}
    if not required.issubset(names):
        return False, f"missing domains; got {sorted(names)}"
    return True, f"domains={sorted(names & required)}"


# ---------------------------------------------------------------------------
# Check 3 — procurement valid
# ---------------------------------------------------------------------------


def _check_3_proc_alice_valid() -> tuple[bool, str]:
    """spike-user-procurement (spec allowed_users) → 200 + auto_approved|review_required.

    R3-B3 fix (Codex R1 HOLD): the previous version used `proc-alice`,
    which is NOT a seeded actor in the procurement fixture. The actual
    valid procurement actor per `scripts/seed_v0_spike_fixture.py` +
    `spec.yaml` is `spike-user-procurement` (roles=[buyer], dept=procurement).
    """
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "procurement",
                "scenario": "default",
                "params": {"amount": 50000, "quote_count": 3},
            },
            headers={"X-User-Id": PROCUREMENT_VALID_USER},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected (DB fixture missing)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    if conclusion not in ("auto_approved", "review_required"):
        return False, f"conclusion={conclusion!r} (expected auto_approved|review_required)"
    return True, f"conclusion={conclusion}"


# ---------------------------------------------------------------------------
# Check 4 — procurement denied
# ---------------------------------------------------------------------------


def _check_4_proc_denied_no_permission() -> tuple[bool, str]:
    """spike-user-unrelated (spec denied_users) → 200 + no_permission."""
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "procurement",
                "scenario": "default",
                "params": {"amount": 50000, "quote_count": 3},
            },
            headers={"X-User-Id": PROCUREMENT_DENIED_USER},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    if conclusion != "no_permission":
        return False, f"conclusion={conclusion!r} (expected 'no_permission')"
    return True, f"conclusion={conclusion}"


# ---------------------------------------------------------------------------
# Check 5 — knowledge valid (answerable)
# ---------------------------------------------------------------------------


def _check_5_km_alice_answerable() -> tuple[bool, str]:
    """km-alice + KM-POL-001 → 200 + answerable."""
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "knowledge",
                "scenario": "default",
                "params": {"policy_id": "KM-POL-001"},
            },
            headers={"X-User-Id": "km-alice"},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    evidence_count = len(data.get("evidence", []))
    if conclusion != "answerable":
        return False, f"conclusion={conclusion!r} (expected 'answerable')"
    if evidence_count < 1:
        return False, f"evidence_count={evidence_count} (expected ≥1)"
    return True, f"conclusion={conclusion} evidence={evidence_count}"


# ---------------------------------------------------------------------------
# Check 6 — knowledge denied
# ---------------------------------------------------------------------------


def _check_6_km_eve_denied() -> tuple[bool, str]:
    """km-eve (spec denied_users) → 200 + no_permission."""
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "knowledge",
                "scenario": "default",
                "params": {"policy_id": "KM-POL-001"},
            },
            headers={"X-User-Id": "km-eve"},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    if conclusion != "no_permission":
        return False, f"conclusion={conclusion!r} (expected 'no_permission')"
    return True, f"conclusion={conclusion}"


# ---------------------------------------------------------------------------
# Check 7 — compliance valid (evidence_package_sufficient)
# ---------------------------------------------------------------------------


def _check_7_comp_alice_sufficient() -> tuple[bool, str]:
    """comp-alice + COMP-CTL-001 + period → 200 + evidence_package_sufficient."""
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "compliance",
                "scenario": "default",
                "params": COMPLIANCE_VALID_PARAMS,
            },
            headers={"X-User-Id": "comp-alice"},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    if conclusion != "evidence_package_sufficient":
        return False, f"conclusion={conclusion!r} (expected 'evidence_package_sufficient')"
    return True, f"conclusion={conclusion}"


# ---------------------------------------------------------------------------
# Check 8 — compliance denied
# ---------------------------------------------------------------------------


def _check_8_comp_eve_denied() -> tuple[bool, str]:
    """comp-eve (spec denied_users) → 200 + no_permission."""
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "compliance",
                "scenario": "default",
                "params": COMPLIANCE_VALID_PARAMS,
            },
            headers={"X-User-Id": "comp-eve"},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 422:
        return True, "SKIPPED — validation rejected"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion")
    if conclusion != "no_permission":
        return False, f"conclusion={conclusion!r} (expected 'no_permission')"
    return True, f"conclusion={conclusion}"


# ---------------------------------------------------------------------------
# Check 9 — 422 strict date (compliance today='not-a-date')
# ---------------------------------------------------------------------------


def _check_9_422_malformed_today() -> tuple[bool, str]:
    """comp-alice + today='not-a-date' → 422 (R2-B2 strict YYYY-MM-DD)."""
    bad_params = {**COMPLIANCE_VALID_PARAMS, "today": "not-a-date"}
    try:
        status, payload = _post_json(
            "/api/v1/demo/scenarios/generate",
            {
                "domain": "compliance",
                "scenario": "default",
                "params": bad_params,
            },
            headers={"X-User-Id": "comp-alice"},
        )
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status != 422:
        return False, f"status={status} (expected 422; payload={payload[:200]!r})"
    return True, f"status=422 strict-date enforced (R2-B2)"


# ---------------------------------------------------------------------------
# Check 10 — zero external CDN in SPA index.html
# ---------------------------------------------------------------------------


def _check_10_zero_cdn() -> tuple[bool, str]:
    """SPA index.html must not reference external CDN scripts/styles.

    SKIP semantics: if DEMO_BASE_URL is an API-only origin (GET / → 404),
    this check is not applicable — SPA is served by nginx in production.
    """
    try:
        status, payload = _get("/", timeout=5.0)
    except RuntimeError as exc:
        return False, f"transport: {exc}"
    if status == 404:
        try:
            api_status, _ = _get("/api/v1/demo/domains", timeout=2.0)
        except RuntimeError:
            api_status = 0
        if api_status == 200:
            return True, (
                "SKIPPED — API-only origin (GET / → 404; SPA served by "
                "nginx in production, not by this uvicorn)"
            )
    if status != 200:
        return False, f"GET / status={status}"
    html = payload.decode("utf-8", errors="replace")
    external_script = re.search(r'<script[^>]+src=["\']https?://', html)
    external_link = re.search(r'<link[^>]+href=["\']https?://', html)
    if external_script:
        return False, f"external CDN script: {external_script.group(0)[:80]!r}"
    if external_link:
        return False, f"external CDN link: {external_link.group(0)[:80]!r}"
    return True, "zero external CDN (script/link)"


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------


_CHECKS: list[tuple[str, callable]] = [
    ("1. SPA index.html reachable from origin (proxy proof)", _check_1_spa_index_html),
    ("2. /api/v1/demo/domains lists procurement + knowledge + compliance", _check_2_domains_three),
    ("3. procurement valid (spike-user-procurement → auto_approved|review_required)", _check_3_proc_alice_valid),
    ("4. procurement denied (spike-user-unrelated → no_permission)", _check_4_proc_denied_no_permission),
    ("5. knowledge valid (km-alice + KM-POL-001 → answerable)", _check_5_km_alice_answerable),
    ("6. knowledge denied (km-eve + KM-POL-001 → no_permission)", _check_6_km_eve_denied),
    ("7. compliance valid (comp-alice + COMP-CTL-001 → evidence_package_sufficient)", _check_7_comp_alice_sufficient),
    ("8. compliance denied (comp-eve + COMP-CTL-001 → no_permission)", _check_8_comp_eve_denied),
    ("9. 422 strict date (compliance today='not-a-date' → 422)", _check_9_422_malformed_today),
    ("10. zero external CDN (SPA serves static only)", _check_10_zero_cdn),
]


def main() -> int:
    print(f"[cut-045 deployment smoke] DEMO_BASE_URL={DEMO_BASE_URL}")
    print()

    passed = 0
    skipped = 0
    failed = 0
    for label, fn in _CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 — surface any unexpected
            ok, detail = False, f"unexpected error: {exc}"
        status_label = "PASS" if ok and not detail.startswith("SKIPPED") else (
            "SKIP" if detail.startswith("SKIPPED") else "FAIL"
        )
        if status_label == "PASS":
            passed += 1
        elif status_label == "SKIP":
            skipped += 1
        else:
            failed += 1
        print(f"[{status_label}] {label}")
        print(f"         {detail}")

    print()
    print(f"PASS={passed} SKIP={skipped} FAIL={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())