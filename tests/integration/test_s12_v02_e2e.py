"""Sprint 12 v0.2 — end-to-end RBAC integration test (cut-025).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening closure: full
RBAC flow across cut-018b / cut-019 / cut-021 / cut-022 / cut-023 /
cut-024. Single test file that proves all delegation channels work
together (or correctly block) for realistic multi-tenant scenarios.

Setup:
    org_a: alice, bob
    org_b: carol, dave
    org_x: manager_x (cross-org manager)
    Tokens:
        manager_tok: per-org delegation for manager_x (org_a, org_b)
        audit_tok: per-resource delegation for specific request_ids
        bad_tok: per-user delegation for alice (revoked)
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from ece.api.rate_limit import reset_buckets
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

ORG_A = "org_a"
ORG_B = "org_b"
ORG_X = "org_x"
USER_ALICE = "demo-v02-alice"  # org_a
USER_BOB = "demo-v02-bob"  # org_a
USER_CAROL = "demo-v02-carol"  # org_b
USER_DAVE = "demo-v02-dave"  # org_b
USER_MANAGER = "demo-v02-manager"  # org_x

ENV_USER_ORGS = f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_A};{USER_CAROL}:{ORG_B};{USER_DAVE}:{ORG_B};{USER_MANAGER}:{ORG_X}"
ENV_DELEGATION_TOKENS = f"user_tok:{USER_ALICE};manager_tok:{USER_CAROL};bad_tok:{USER_ALICE}"
ENV_DELEGATION_ORG_TOKENS = "manager_tok:org_a,org_b"
ENV_RATE_LIMITS = "org_a:3/m;org_b:5/m"


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure env for v0.2 RBAC scenarios."""
    monkeypatch.setenv("ECE_USER_ORGS", ENV_USER_ORGS)
    monkeypatch.setenv("ECE_DELEGATION_TOKENS", ENV_DELEGATION_TOKENS)
    monkeypatch.setenv("ECE_DELEGATION_ORG_TOKENS", ENV_DELEGATION_ORG_TOKENS)
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", ENV_RATE_LIMITS)
    reset_buckets()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def alice_trace_id() -> str:
    """alice (org_a) creates a trace."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_ALICE,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_V02_A"}],
    )
    return pkg.request_id


@pytest.fixture
def carol_trace_id() -> str:
    """carol (org_b) creates a trace."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_CAROL,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_V02_C"}],
    )
    return pkg.request_id


# === Scenario 1: Owner access (no token, no X-Org-Id needed in single-tenant-ish) ===
def test_owner_can_read_own_trace(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 1: alice reads own trace → 200 (owner check)."""
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={"X-User-Id": USER_ALICE, "X-Org-Id": ORG_A},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_ref"] == USER_ALICE


# === Scenario 2: Per-USER delegation (cut-018b) ===
def test_per_user_delegation_grants_access(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 2: bob reads alice's trace with user_tok → 200 (per-user)."""
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_BOB,
            "X-Org-Id": ORG_A,
            "X-Delegation-Token": "user_tok",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_ref"] == USER_ALICE


# === Scenario 3: Cross-org blocked (cut-019) ===
def test_cross_org_blocked_without_token(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 3: carol (org_b) reads alice's (org_a) trace without token → 403."""
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_CAROL,
            "X-Org-Id": ORG_B,
        },
    )
    assert r.status_code == 403, r.text


# === Scenario 4: Per-ORG delegation (cut-021) ===
def test_per_org_delegation_grants_cross_org_access(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 4: manager_x (org_x) reads alice (org_a) with manager_tok → 200."""
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_MANAGER,
            "X-Delegation-Token": "manager_tok",
            # No X-Org-Id — token grants cross-org
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_ref"] == USER_ALICE


# === Scenario 5: Per-RESOURCE delegation (cut-022) ===
def test_per_resource_delegation_grants_specific_request(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 5: external with audit_tok + rq → 200 (per-resource)."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{alice_trace_id}"
    try:
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={
                "X-User-Id": "external_auditor",
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["user_ref"] == USER_ALICE
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


def test_per_resource_denies_other_request(
    client: TestClient, alice_trace_id: str, carol_trace_id: str
) -> None:
    """Scenario 5b: external with audit_tok for alice's rq tries carol's rq → 403."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{alice_trace_id}"
    try:
        r = client.get(
            f"/api/v1/audit/context/{carol_trace_id}",
            headers={
                "X-User-Id": "external_auditor",
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


# === Scenario 6: Rate limit (cut-023) ===
def test_rate_limit_per_org_isolation(
    client: TestClient, alice_trace_id: str, carol_trace_id: str
) -> None:
    """Scenario 6: org_a limited to 3/min; org_b unaffected."""
    reset_buckets()
    # 3 requests to org_a (limit is 3/m) → all 200
    for _ in range(3):
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={"X-User-Id": USER_ALICE, "X-Org-Id": ORG_A},
        )
        assert r.status_code == 200
    # 4th request to org_a → 429
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={"X-User-Id": USER_ALICE, "X-Org-Id": ORG_A},
    )
    assert r.status_code == 429, r.text
    # org_b still works (independent bucket, limit 5/m)
    r = client.get(
        f"/api/v1/audit/context/{carol_trace_id}",
        headers={"X-User-Id": USER_CAROL, "X-Org-Id": ORG_B},
    )
    assert r.status_code == 200


# === Scenario 7: Token revocation (cut-024) ===
def test_revoked_token_blocks_delegated_access(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 7: bad_tok is revoked → bob's delegated access blocked."""
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        # bad_tok would have granted access to alice for bob; but revoked
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={
                "X-User-Id": USER_BOB,
                "X-Org-Id": ORG_A,
                "X-Delegation-Token": "bad_tok",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)


def test_revocation_does_not_affect_owner(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 7b: alice can still read own trace even with revoked tokens."""
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok,user_tok"
    try:
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={"X-User-Id": USER_ALICE, "X-Org-Id": ORG_A},
        )
        assert r.status_code == 200, r.text
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)


# === Scenario 8: Combined — multi-channel delegation ===
def test_combined_owner_and_token_both_work(
    client: TestClient, alice_trace_id: str
) -> None:
    """Scenario 8: alice (owner) with valid token reads own trace → 200 (redundant ok)."""
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_ALICE,
            "X-Org-Id": ORG_A,
            "X-Delegation-Token": "user_tok",  # would grant access to alice
        },
    )
    assert r.status_code == 200, r.text


# === Scenario 9: All channels combined ===
def test_full_v02_flow(
    client: TestClient, alice_trace_id: str, carol_trace_id: str
) -> None:
    """Scenario 9: full v0.2 RBAC matrix — every delegation channel exercised."""
    reset_buckets()

    # 1. Owner → 200
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={"X-User-Id": USER_ALICE, "X-Org-Id": ORG_A},
    )
    assert r.status_code == 200

    # 2. Per-USER delegation → 200
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_BOB,
            "X-Org-Id": ORG_A,
            "X-Delegation-Token": "user_tok",
        },
    )
    assert r.status_code == 200

    # 3. Cross-org blocked → 403
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={"X-User-Id": USER_CAROL, "X-Org-Id": ORG_B},
    )
    assert r.status_code == 403

    # 4. Per-ORG delegation → 200 (cross-org via token)
    r = client.get(
        f"/api/v1/audit/context/{alice_trace_id}",
        headers={
            "X-User-Id": USER_MANAGER,
            "X-Delegation-Token": "manager_tok",
        },
    )
    assert r.status_code == 200

    # 5. Per-RESOURCE delegation → 200 (with audit_tok)
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{carol_trace_id}"
    try:
        r = client.get(
            f"/api/v1/audit/context/{carol_trace_id}",
            headers={
                "X-User-Id": "external_auditor",
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 200
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
