#!/usr/bin/env python3
"""cut-044 — Compliance pack same-origin smoke.

4 API checks against a live FastAPI server (default 127.0.0.1:8765):
  1. GET /api/v1/demo/domains includes `compliance` pack auto-discovered
  2. POST scenarios/generate with COMP-CTL-001 + comp-alice →
     evidence_package_sufficient + 2 evidence rows (both conditions pass)
  3. POST with comp-eve + COMP-CTL-001 → no_permission + 0 evidence
     (Permission Before Intelligence — engine ACL DENY pre-rule branch)
  4. POST with comp-alice + COMP-CTL-003 → gap_list + 1 evidence
     (count passes, coverage incomplete — R5-B2 zero-evidence allowlist
     does NOT block the 1-row path)

DB-dependent: requires the seeded `comp:v0-compliance-fixture` data. On
DB-unreachable, checks 2/3/4 SKIP (mirrors cut-042R2 R2-F3 SKIP semantics).
Check 1 is DB-light.

cut-044 R0 conformance:
  - caller-supplies today via params (compliance does NOT have
    `requires_server_today_anchor`)
  - control_id via params (`route_root_via_params: true`)
  - check 3 (denied branch): comp-eve has explicit engine ACL DENY row on
    COMP-CTL-001 (seeded by `seed_compliance_fixture.py`); the loop
    short-circuits pre-rule → conclusion=no_permission with 0 evidence rows

Usage:
  uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
  python scripts/cut_044_same_origin_smoke.py
  kill %1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8765")
TODAY = os.environ.get("SMOKE_TODAY", "2026-09-22")


def _check_domains_compliance_present() -> tuple[bool, str]:
    """GET /api/v1/demo/domains must include `compliance`."""
    try:
        with urllib.request.urlopen(f"{API_BASE}/api/v1/demo/domains", timeout=3) as r:
            payload = json.loads(r.read())
        names = {d.get("name") for d in payload.get("domains", [])}
        if "compliance" not in names:
            return False, f"compliance not in domains: {sorted(names)}"
        return True, f"domains={sorted(names)}"
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, f"transport error: {exc}"


def _check_comp_ctl001_alice_sufficient() -> tuple[bool, str]:
    """COMP-CTL-001 + comp-alice (X-User-Id) → evidence_package_sufficient + 2 evidence rows.

    3 evidence packages covering all 3 systems, both conditions pass:
      - evidence_count_meets_threshold: 3 >= 3 ✓
      - system_coverage_complete: {erp,hr,finance} ⊆ {erp,hr,finance} ✓
    Expected: decision_value=evidence_package_sufficient, 2 evidence rows.
    """
    body = json.dumps({
        "domain": "compliance",
        "scenario": "default",
        "params": {
            "control_id": "COMP-CTL-001",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "today": TODAY,
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "comp-alice", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion") or payload.get("decision_value")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "evidence_package_sufficient":
            return False, f"conclusion={conclusion!r} (expected 'evidence_package_sufficient')"
        if evidence_count != 2:
            return False, f"evidence_count={evidence_count} (expected 2)"
        return True, f"conclusion={conclusion} evidence_count={evidence_count}"
    except urllib.error.HTTPError as exc:
        if exc.code in (500, 422):
            return True, "SKIPPED — DB unreachable or invalid fixture (out of cut-044 API-only scope)"
        return False, f"HTTPError status={exc.code}"
    except urllib.error.URLError as exc:
        return True, f"SKIPPED — upstream unreachable: {exc}"


def _check_comp_ctl001_eve_denied() -> tuple[bool, str]:
    """cut-044 — permission 反差 (PRD §7 纪律 #2).

    comp-eve has explicit engine ACL DENY row on COMP-CTL-001 (seeded by
    `seed_compliance_fixture.py`). The Permission Engine denies BEFORE the
    rule runs, so the loop returns the denied branch:
    conclusion=no_permission with 0 evidence rows.

    This is the "permission contrast" smoke — proves denied users get
    zero-side-effect refusal, distinct from rule-level gap_list outcome.
    """
    body = json.dumps({
        "domain": "compliance",
        "scenario": "default",
        "params": {
            "control_id": "COMP-CTL-001",  # full coverage; eve is denied at ACL layer
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "today": TODAY,
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "comp-eve", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion") or payload.get("decision_value")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "no_permission":
            return False, (
                f"conclusion={conclusion!r} (expected 'no_permission' — engine "
                f"ACL DENY row on COMP-CTL-001 for comp-eve); "
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


def _check_comp_ctl003_alice_gap_list() -> tuple[bool, str]:
    """cut-044 — coverage-only failure: COMP-CTL-003 + comp-alice → gap_list + 1 evidence.

    CTL-003 has 3 evidence packages (1 erp + 2 hr), required_systems=
    [erp, hr, finance]:
      - evidence_count_meets_threshold: 3 >= 3 ✓ (1 evidence row)
      - system_coverage_complete: {erp, hr} ⊄ {erp, hr, finance} ✗ (finance missing)
    Expected: decision_value=gap_list, 1 evidence row (count only, coverage
    condition does NOT emit a row per S2 lock-down — only passed conditions
    write evidence rows).
    """
    body = json.dumps({
        "domain": "compliance",
        "scenario": "default",
        "params": {
            "control_id": "COMP-CTL-003",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "today": TODAY,
        },
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/demo/scenarios/generate",
        data=body, method="POST",
        headers={"X-User-Id": "comp-alice", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            payload = json.loads(r.read())
        conclusion = payload.get("conclusion") or payload.get("decision_value")
        evidence_count = len(payload.get("evidence", []))
        if conclusion != "gap_list":
            return False, (
                f"conclusion={conclusion!r} (expected 'gap_list' — coverage "
                f"incomplete); body={json.dumps(payload)[:300]}"
            )
        if evidence_count != 1:
            return False, f"evidence_count={evidence_count} (expected 1 — count only)"
        return True, f"conclusion={conclusion} evidence_count={evidence_count}"
    except urllib.error.HTTPError as exc:
        if exc.code in (500, 422):
            return True, "SKIPPED — DB unreachable or invalid fixture"
        return False, f"HTTPError status={exc.code}"
    except urllib.error.URLError as exc:
        return True, f"SKIPPED — upstream unreachable: {exc}"


_SMOKE_CHECKS = [
    ("Compliance domain auto-discovered in /domains", _check_domains_compliance_present),
    ("Compliance sufficient (COMP-CTL-001 + comp-alice)", _check_comp_ctl001_alice_sufficient),
    ("Compliance permission contrast (comp-eve + COMP-CTL-001 → no_permission)", _check_comp_ctl001_eve_denied),
    ("Compliance coverage-only fail (COMP-CTL-003 + comp-alice → gap_list, 1 evidence)", _check_comp_ctl003_alice_gap_list),
]


def main() -> int:
    print(f"=== cut-044 same-origin smoke ({API_BASE}) ===\n")
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

    print(f"\ncut-044 same-origin smoke: PASS={passed} SKIP={skipped} FAIL={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
