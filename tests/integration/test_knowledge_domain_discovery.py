"""cut-043 — Knowledge Management domain auto-discovery test.

PRD §5 底座泛化: GET /api/v1/demo/domains MUST automatically include the
`knowledge` pack without API-layer changes — discovery is purely filesystem-driven
(scan `src/ece/domain_packs/<pack>/scenarios/*.yaml`).

This test pins that contract: if a future refactor breaks auto-discovery,
this test fails with a single readable message.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from ece.main import app


def test_knowledge_domain_auto_discovered_in_manifest() -> None:
    """GET /api/v1/demo/domains must include `knowledge` (label='制度知识审查')."""
    client = TestClient(app)
    resp = client.get("/api/v1/demo/domains")
    assert resp.status_code == 200, (
        f"GET /domains failed: {resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    domains = body.get("domains", [])

    # Find the knowledge entry.
    km = next((d for d in domains if d.get("name") == "knowledge"), None)
    assert km is not None, (
        f"knowledge domain not auto-discovered; got {domains!r}. "
        "Check that src/ece/domain_packs/knowledge/scenarios/*.yaml exists "
        "and the __init__.py triggers self-registration."
    )

    # Label is read from the first scenario's YAML (per cut-042R F2).
    assert km.get("label") == "制度知识审查", (
        f"knowledge label must be '制度知识审查'; got {km.get('label')!r}"
    )

    # At least one scenario (default.yaml) must be listed.
    scenarios = km.get("scenarios", [])
    assert "default" in scenarios, (
        f"knowledge domain must list 'default' scenario; got {scenarios!r}"
    )


def test_knowledge_post_route_uses_pack_specific_scenario_spec() -> None:
    """POST /api/v1/demo/scenarios/generate with domain=knowledge must route to
    `src/ece/domain_packs/knowledge/scenarios/default.yaml`.

    This test does NOT assert the rule's behavior (covered by
    `test_knowledge_boundary.py`); it pins the routing contract.

    cut-043R R5-B1/R5-B4 conformance: NO `today` (server-owned), NO
    `employee_id` (caller identity is X-User-Id).
    """
    client = TestClient(app)
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {
                "policy_id": "KM-POL-001",
            },
        },
    )
    assert resp.status_code == 200, (
        f"POST scenarios/generate with domain=knowledge failed: {resp.status_code} "
        f"body={resp.text[:300]}"
    )
    body = resp.json()
    # cut-042R F4 + cut-043 mapper contract: the API response shape is
    # business-named; internal field names like `decision_rule_id` /
    # `decision_key` are STRIPPED (PRD §5 #2 forbids leaking them).
    # We probe routing by inspecting business-language signals instead:
    assert body.get("domain") == "knowledge", (
        f"knowledge POST must echo domain='knowledge'; got {body.get('domain')!r}"
    )
    assert body.get("scenario") == "evaluate_policy_question", (
        f"knowledge POST must use spec='evaluate_policy_question' "
        f"(from scenarios/default.yaml); got {body.get('scenario')!r}"
    )
    # KM rule writes "有据可答" in `reason`; procurement would write "需人工复核".
    reason = body.get("reason", "")
    assert "有据可答" in reason, (
        f"knowledge POST must invoke R-KM-ACCESS (reason contains '有据可答'); "
        f"got reason={reason!r}"
    )
    # State change writes back to `review_status` slot (S4 hardcoded JSONB key).
    state_change = body.get("state_change", {})
    assert state_change.get("key") == "review_status", (
        f"knowledge POST must write back decision_key='review_status'; "
        f"got state_change={state_change!r}"
    )
