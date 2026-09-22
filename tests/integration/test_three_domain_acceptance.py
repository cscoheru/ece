"""cut-045 — Three-domain acceptance + 422 strict date binding tests.

Per `codex给cut-045的指令.md §7.6/#7.7`: View A 三域均可参数化实时运行 + 三域均有 denied user 反差.

These tests confirm the existing API contract (cut-042R/cut-043R/cut-044R2) is
preserved through cut-045. They use FastAPI TestClient (in-process) — for the
deployment smoke (cross-origin via DEMO_BASE_URL) see
`scripts/cut_045_demo_deployment_smoke.py`.

Status on cut-044R2 baseline: GREEN (binding invariant preserved).
After cut-045 sub-knife A/B/C, must remain GREEN.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _post_scenario(
    client: TestClient, *, domain: str, params: dict[str, Any], user: str
) -> dict[str, Any]:
    """POST to /api/v1/demo/scenarios/generate and return parsed JSON."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": domain,
            "scenario": "default",
            "params": params,
        },
        headers={"X-User-Id": user},
    )
    return {"status": r.status_code, "body": r.json() if r.content else {}}


# ---------------------------------------------------------------------------
# Domain discovery (procurement + knowledge + compliance) — directive §7
# ---------------------------------------------------------------------------


def test_domains_endpoint_lists_all_three(client: TestClient) -> None:
    """GET /api/v1/demo/domains must list procurement, knowledge, compliance."""
    r = client.get("/api/v1/demo/domains")
    assert r.status_code == 200, r.text
    names = {d["name"] for d in r.json()["domains"]}
    for required in ("procurement", "knowledge", "compliance"):
        assert required in names, (
            f"domains missing {required!r}; got {sorted(names)}"
        )


# ---------------------------------------------------------------------------
# Procurement valid + denied — directive §7.7
# ---------------------------------------------------------------------------


def test_procurement_valid_alice_200(client: TestClient) -> None:
    """procurement + spike-user-procurement (valid seeded user) → 200 + auto_approved/review_required.

    R3-B3 fix (Codex R1 HOLD): the previous version used `proc-alice`,
    which is NOT a seeded actor in the procurement fixture. Per
    `scripts/seed_v0_spike_fixture.py` + `scenarios/default.yaml`, the
    actual valid procurement actor is `spike-user-procurement`
    (dept=procurement, roles=[buyer]).
    """
    out = _post_scenario(
        client,
        domain="procurement",
        params={"amount": 50000, "quote_count": 3},
        user="spike-user-procurement",
    )
    assert out["status"] == 200, out
    body = out["body"]
    assert body.get("conclusion") in ("auto_approved", "review_required"), (
        f"unexpected conclusion: {body.get('conclusion')!r}"
    )


def test_procurement_denied_eve_no_permission(client: TestClient) -> None:
    """procurement + spike-user-unrelated (denied user) → 200 + no_permission.

    Per `src/ece/domain_packs/procurement/scenarios/default.yaml`
    `denied_users`, procurement's denied user is `spike-user-unrelated`.
    proc-eve is NOT a denied user (that's for the other domains' role checks).
    """
    out = _post_scenario(
        client,
        domain="procurement",
        params={"amount": 50000, "quote_count": 3},
        user="spike-user-unrelated",
    )
    assert out["status"] == 200, out
    assert out["body"].get("conclusion") == "no_permission", (
        f"expected no_permission, got {out['body'].get('conclusion')!r}"
    )


# ---------------------------------------------------------------------------
# Knowledge valid + denied — directive §7.7
# ---------------------------------------------------------------------------


def test_knowledge_valid_alice_answerable(client: TestClient) -> None:
    """knowledge + km-alice + KM-POL-001 → 200 + answerable (with 2 evidence)."""
    out = _post_scenario(
        client,
        domain="knowledge",
        params={"policy_id": "KM-POL-001"},
        user="km-alice",
    )
    assert out["status"] == 200, out
    body = out["body"]
    # Knowledge: server-owned today; no today/employee_id in params
    assert "today" not in out["body"], "today must be server-owned (KM)"
    assert body.get("conclusion") == "answerable", (
        f"expected answerable, got {body.get('conclusion')!r}"
    )
    assert len(body.get("evidence", [])) >= 1, (
        f"answerable should have evidence; got {len(body.get('evidence', []))}"
    )


def test_knowledge_denied_eve_no_permission(client: TestClient) -> None:
    """knowledge + km-eve + KM-POL-001 → 200 + no_permission (ACL DENY)."""
    out = _post_scenario(
        client,
        domain="knowledge",
        params={"policy_id": "KM-POL-001"},
        user="km-eve",
    )
    assert out["status"] == 200, out
    assert out["body"].get("conclusion") == "no_permission", (
        f"expected no_permission, got {out['body'].get('conclusion')!r}"
    )


# ---------------------------------------------------------------------------
# Compliance valid + denied — directive §7.7
# ---------------------------------------------------------------------------


COMPLIANCE_TODAY = "2026-09-22"
COMPLIANCE_VALID_PARAMS = {
    "control_id": "COMP-CTL-001",
    "period_start": "2026-07-01",
    "period_end": "2026-09-30",
    "today": COMPLIANCE_TODAY,
}


def test_compliance_valid_alice_sufficient(client: TestClient) -> None:
    """compliance + comp-alice + COMP-CTL-001 → 200 + evidence_package_sufficient."""
    out = _post_scenario(
        client,
        domain="compliance",
        params=COMPLIANCE_VALID_PARAMS,
        user="comp-alice",
    )
    assert out["status"] == 200, out
    body = out["body"]
    assert body.get("conclusion") == "evidence_package_sufficient", (
        f"expected evidence_package_sufficient, got {body.get('conclusion')!r}"
    )


def test_compliance_denied_eve_no_permission(client: TestClient) -> None:
    """compliance + comp-eve + COMP-CTL-001 → 200 + no_permission."""
    out = _post_scenario(
        client,
        domain="compliance",
        params=COMPLIANCE_VALID_PARAMS,
        user="comp-eve",
    )
    assert out["status"] == 200, out
    assert out["body"].get("conclusion") == "no_permission", (
        f"expected no_permission, got {out['body'].get('conclusion')!r}"
    )


# ---------------------------------------------------------------------------
# 422 strict date (compliance today="not-a-date") — directive §5.2 #5
# ---------------------------------------------------------------------------


def test_compliance_malformed_today_422(client: TestClient) -> None:
    """compliance + today="not-a-date" → 422 (cut-044R2 R2-B2 strict YYYY-MM-DD)."""
    bad_params = {**COMPLIANCE_VALID_PARAMS, "today": "not-a-date"}
    out = _post_scenario(
        client,
        domain="compliance",
        params=bad_params,
        user="comp-alice",
    )
    assert out["status"] == 422, (
        f"malformed today should 422; got status={out['status']} body={out['body']!r}"
    )


def test_compliance_basic_iso_today_422(client: TestClient) -> None:
    """compliance + today="20260922" (basic ISO, not canonical) → 422."""
    bad_params = {**COMPLIANCE_VALID_PARAMS, "today": "20260922"}
    out = _post_scenario(
        client,
        domain="compliance",
        params=bad_params,
        user="comp-alice",
    )
    assert out["status"] == 422, (
        f"basic ISO today should 422; got status={out['status']}"
    )


def test_compliance_reversed_period_422(client: TestClient) -> None:
    """compliance + period_start > period_end → 422 (reversal check)."""
    bad_params = {
        **COMPLIANCE_VALID_PARAMS,
        "period_start": "2026-09-30",
        "period_end": "2026-07-01",
    }
    out = _post_scenario(
        client,
        domain="compliance",
        params=bad_params,
        user="comp-alice",
    )
    assert out["status"] == 422, (
        f"reversed period should 422; got status={out['status']}"
    )


# ---------------------------------------------------------------------------
# Permission before intelligence — directive §7.8 (denied contrast in 3 domains)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "domain,user,params",
    [
        # Per spec.yaml denied_users:
        #   procurement: spike-user-unrelated
        #   knowledge:   km-eve
        #   compliance:  comp-eve
        ("procurement", "spike-user-unrelated", {"amount": 50000, "quote_count": 3}),
        ("knowledge", "km-eve", {"policy_id": "KM-POL-001"}),
        ("compliance", "comp-eve", COMPLIANCE_VALID_PARAMS),
    ],
)
def test_three_domains_denied_contrast(
    client: TestClient, domain: str, user: str, params: dict[str, Any]
) -> None:
    """All 3 domains must return no_permission for their respective denied user."""
    out = _post_scenario(client, domain=domain, params=params, user=user)
    assert out["status"] == 200, out
    assert out["body"].get("conclusion") == "no_permission", (
        f"{domain} + {user} expected no_permission; got {out['body'].get('conclusion')!r}"
    )