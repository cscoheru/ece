"""cut-044 — Compliance Pack domain auto-discovery test.

PRD §5 底座泛化: GET /api/v1/demo/domains MUST automatically include the
`compliance` pack without API-layer changes — discovery is purely filesystem-driven
(scan `src/ece/domain_packs/<pack>/scenarios/*.yaml`).

This test pins that contract: if a future refactor breaks auto-discovery,
this test fails with a single readable message. Mirrors
`test_knowledge_domain_discovery.py`.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from ece.main import app


def test_compliance_domain_auto_discovered_in_manifest() -> None:
    """GET /api/v1/demo/domains must include `compliance` (label='企业合规审计')."""
    client = TestClient(app)
    resp = client.get("/api/v1/demo/domains")
    assert resp.status_code == 200, (
        f"GET /domains failed: {resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    domains = body.get("domains", [])

    # Find the compliance entry.
    comp = next((d for d in domains if d.get("name") == "compliance"), None)
    assert comp is not None, (
        f"compliance domain not auto-discovered; got {domains!r}. "
        "Check that src/ece/domain_packs/compliance/scenarios/*.yaml exists "
        "and the __init__.py triggers self-registration."
    )

    # Label is read from the first scenario's YAML (per cut-042R F2).
    assert comp.get("label") == "企业合规审计", (
        f"compliance label must be '企业合规审计'; got {comp.get('label')!r}"
    )

    # At least one scenario (default.yaml) must be listed.
    scenarios = comp.get("scenarios", [])
    assert "default" in scenarios, (
        f"compliance domain must list 'default' scenario; got {scenarios!r}"
    )


def test_compliance_post_route_uses_pack_specific_scenario_spec() -> None:
    """POST /api/v1/demo/scenarios/generate with domain=compliance must route to
    `src/ece/domain_packs/compliance/scenarios/default.yaml`.

    This test does NOT assert the rule's behavior (covered by
    `test_compliance_boundary.py`); it pins the routing contract.

    cut-044 plan §3.5: compliance has `requires_server_today_anchor: false`,
    so `today` is caller-supplied via params. We pass SERVER_TODAY to land
    inside the audit window.
    """
    client = TestClient(app)
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "comp-alice"},
        json={
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "today": "2026-09-22",
            },
        },
    )
    assert resp.status_code == 200, (
        f"POST scenarios/generate with domain=compliance failed: {resp.status_code} "
        f"body={resp.text[:300]}"
    )
    body = resp.json()
    # cut-042R F4 + cut-044 mapper contract: the API response shape is
    # business-named; internal field names like `decision_rule_id` /
    # `decision_key` are STRIPPED (PRD §5 #2 forbids leaking them).
    assert body.get("domain") == "compliance", (
        f"compliance POST must echo domain='compliance'; got {body.get('domain')!r}"
    )
    assert body.get("scenario") == "evaluate_audit_question", (
        f"compliance POST must use spec='evaluate_audit_question' "
        f"(from scenarios/default.yaml); got {body.get('scenario')!r}"
    )
    # R-COMP-AUDIT writes business-language claim with "无缺口" for full coverage.
    reason = body.get("reason", "")
    assert "无缺口" in reason, (
        f"compliance POST must invoke R-COMP-AUDIT (reason contains '无缺口'); "
        f"got reason={reason!r}"
    )
    # State change writes back to `review_status` slot (S4 hardcoded JSONB key
    # reused; cut-043 wart → cut-045 may generalize decision_key write-back).
    state_change = body.get("state_change", {})
    assert state_change.get("key") == "review_status", (
        f"compliance POST must write back decision_key='review_status'; "
        f"got state_change={state_change!r}"
    )
