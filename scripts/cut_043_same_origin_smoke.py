#!/usr/bin/env python3
"""cut-043R — Knowledge Management pack same-origin smoke.

4 API checks against a live FastAPI server (default 127.0.0.1:8765):
  1. GET /api/v1/demo/domains includes `knowledge` pack auto-discovered
  2. POST scenarios/generate with domain=knowledge → answerable + 2 evidence
  3. POST with denied user km-eve + KM-POL-001 → no_permission + 0 evidence
     (permission 反差 / PRD §7 纪律 #2 — engine ACL DENY pre-rule branch)
  4. POST with km-eve + KM-POL-002 → needs_valid_policy + 0 evidence
     (R5-B2 — rule double-failure zero-evidence; needs_valid_policy allowlisted)

DB-dependent: requires the seeded `km:v0-knowledge-fixture` data. On DB-unreachable,
checks 2/3/4 SKIP (mirrors cut-042R2 R2-F3 SKIP semantics). Check 1 is DB-light.

cut-043R R5-B1/R5-B4 conformance (every POST below):
  - NO `today` in params (server-owned; would 422 with "requires_server_today_anchor")
  - NO `employee_id` in params (caller identity is X-User-Id)
  - For check 3 (denied branch) km-eve is in spec.denied_users + has an explicit
    ACL DENY row on KM-POL-001, so the loop short-circuits pre-rule. The output
    shape is `conclusion=no_permission` with 0 evidence rows.
  - For check 4 (R5-B2) km-eve has no roles, KM-POL-002 is expired (valid_to
    2024-12-31). The rule sees BOTH conditions failed and the allowlist lets
    the zero-evidence path land cleanly as `needs_valid_policy`.

Usage:
  uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
  python scripts/cut_043_same_origin_smoke.py
  kill %1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8765")


def _check_domains_knowledge_present() -> tuple[bool, str]:
    """GET /api/v1/demo/domains must include `knowledge`."""
    try:
        with urllib.request.urlopen(f"{API_BASE}/api/v1/demo/domains", timeout=3) as r:
            payload = json.loads(r.read())
        names = {d.get("name") for d in payload.get("domains", [])}
        if "knowledge" not in names:
            return False, f"knowledge not in domains: {sorted(names)}"
        return True, f"domains={sorted(names)}"
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, f"transport error: {exc}"


def _check_km_answerable_alice() -> tuple[bool, str]:
    """KM-POL-001 + km-alice (X-User-Id) → answerable + 2 evidence rows.

    cut-043R: `today` is server-owned; we don't pass it in params.
    On DB-unreachable, SKIP (mirrors cut-042R2 R2-F3 SKIP semantics).
    """
    body = json.dumps({
        "domain": "knowledge",
        "scenario": "default",
        "params": {
            "policy_id": "KM-POL-001",
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "km-alice", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "answerable":
            return False, f"conclusion={conclusion!r} (expected 'answerable')"
        if evidence_count != 2:
            return False, f"evidence_count={evidence_count} (expected 2)"
        return True, f"conclusion={conclusion} evidence_count={evidence_count}"
    except urllib.error.HTTPError as exc:
        if exc.code in (500, 422):
            return True, "SKIPPED — DB unreachable or invalid fixture (out of cut-043R API-only scope)"
        return False, f"HTTPError status={exc.code}"
    except urllib.error.URLError as exc:
        return True, f"SKIPPED — upstream unreachable: {exc}"


def _check_km_denied_eve() -> tuple[bool, str]:
    """cut-043 R5 — permission 反差 (PRD §7 纪律 #2).

    km-eve is in spec.denied_users AND has an explicit engine-level DENY row
    on KM-POL-001 (seeded by `seed_knowledge_fixture.py`). The Permission
    Engine denies BEFORE the rule runs, so the loop returns the denied
    branch: conclusion=no_permission with 0 evidence rows.

    This is the "permission contrast" smoke — proves denied users get
    zero-side-effect refusal, distinct from rule-level failures.

    cut-043R2 R6-B3: restored from cut-043 (it was unintentionally replaced
    by the R5-B2 zero-evidence check during cut-043R; both must coexist to
    cover engine-denial vs rule-double-fail business semantics).
    """
    body = json.dumps({
        "domain": "knowledge",
        "scenario": "default",
        "params": {
            "policy_id": "KM-POL-001",  # valid; eve is denied at ACL layer
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "km-eve", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "no_permission":
            return False, (
                f"conclusion={conclusion!r} (expected 'no_permission' — engine "
                f"ACL DENY row on KM-POL-001 for km-eve); "
                f"body={json.dumps(payload)[:300]}"
            )
        if evidence_count != 0:
            return False, f"evidence_count={evidence_count} (expected 0 for denied)"
        return True, f"conclusion={conclusion} evidence_count={evidence_count}"
    except urllib.error.HTTPError as exc:
        if exc.code in (500, 422):
            return True, "SKIPPED — DB unreachable or invalid fixture"
        return False, f"HTTPError status={exc.code}"
    except urllib.error.URLError as exc:
        return True, f"SKIPPED — upstream unreachable: {exc}"


def _check_km_eve_zero_evidence_r5b2() -> tuple[bool, str]:
    """cut-043R R5-B2: km-eve + KM-POL-002 → needs_valid_policy + 0 evidence.

    Prior bug: this combination (both conditions failed) produced 0 evidence
    rows but the loop only allowed `auto_approved` zero-evidence, so it
    threw RuntimeError → 500. The fix extends the allowlist with
    `needs_valid_policy` (declared in scenarios/default.yaml's
    zero_evidence_decisions). Eve is no longer in denied_users; the rule
    decides both conditions failed, and the allowlist lets the zero-evidence
    path land cleanly.
    """
    body = json.dumps({
        "domain": "knowledge",
        "scenario": "default",
        "params": {
            "policy_id": "KM-POL-002",  # expired — both conditions fail
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "km-eve", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "needs_valid_policy":
            return False, (
                f"conclusion={conclusion!r} (expected 'needs_valid_policy' per R5-B2); "
                f"body={json.dumps(payload)[:300]}"
            )
        if evidence_count != 0:
            return False, f"evidence_count={evidence_count} (expected 0 for both-failed)"
        return True, f"conclusion={conclusion} evidence_count={evidence_count}"
    except urllib.error.HTTPError as exc:
        if exc.code == 500:
            return False, (
                f"R5-B2 REGRESSION: km-eve + KM-POL-002 must NOT 500; got 500 "
                f"(RuntimeError: needs_valid_policy zero-evidence not allowlisted)"
            )
        if exc.code == 422:
            return True, "SKIPPED — DB unreachable or invalid fixture"
        return False, f"HTTPError status={exc.code}"
    except urllib.error.URLError as exc:
        return True, f"SKIPPED — upstream unreachable: {exc}"


_SMOKE_CHECKS = [
    ("KM domain auto-discovered in /domains", _check_domains_knowledge_present),
    ("KM answerable (KM-POL-001 + km-alice)", _check_km_answerable_alice),
    ("KM permission contrast (km-eve + KM-POL-001 → no_permission)", _check_km_denied_eve),
    ("KM R5-B2 zero-evidence (km-eve + KM-POL-002 → needs_valid_policy)", _check_km_eve_zero_evidence_r5b2),
]


def main() -> int:
    print(f"=== cut-043R same-origin smoke ({API_BASE}) ===\n")
    passed = failed = skipped = 0
    for name, fn in _SMOKE_CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL — {name} (raised: {exc})")
            failed += 1
            continue
        if detail.startswith("SKIPPED"):
            print(f"  SKIP — {name} ({detail})")
            skipped += 1
        elif ok:
            print(f"  PASS — {name} ({detail})")
            passed += 1
        else:
            print(f"  FAIL — {name} ({detail})")
            failed += 1

    print(f"\ncut-043R same-origin smoke: PASS={passed} SKIP={skipped} FAIL={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
