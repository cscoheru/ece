"""S2.2 Permission Engine + /permissions/check API contract."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.db import get_engine
from ece.identity.parser import resolve_identity
from ece.main import app
from ece.permissions.engine import check_permission


def test_check_permission_deny_for_unknown_user() -> None:
    engine = get_engine()
    decision = check_permission(
        identity=resolve_identity(engine, "X-NONEXISTENT-USER-002"),
        object_type="entity",
        object_ref="SUP001",
        classification="department",
        acl_entries=[],
    )
    assert decision.allowed is False
    assert decision.matched_rule == "default-deny"


def test_check_permission_public_classification_allows() -> None:
    # Build an identity via dataclass directly (no DB write needed)
    from ece.identity.parser import Identity

    ident = Identity(
        user_ref="X-TEST-USER-002",
        entity_id="fake-uuid",
        display_id="U999",
        department="D01",
        roles=["buyer"],
        is_management=False,
    )
    decision = check_permission(
        identity=ident,
        object_type="document",
        object_ref="DOC-PUBLIC-001",
        classification="public",
        acl_entries=[],
    )
    assert decision.allowed is True
    assert decision.matched_rule == "classification-public"


def test_check_permission_explicit_deny_beats_classification_default() -> None:
    from ece.identity.parser import Identity

    ident = Identity(
        user_ref="X-TEST-USER-002",
        entity_id="fake-uuid",
        display_id="U999",
        department="D01",
        roles=["buyer"],
        is_management=False,
    )
    decision = check_permission(
        identity=ident,
        object_type="document",
        object_ref="DOC-001",
        classification="public",  # would default allow
        acl_entries=[
            {"subject_type": "user", "subject_ref": "X-TEST-USER-002",
             "effect": "deny", "valid_from": None, "valid_to": None, "source_system": "test"},
        ],
    )
    # Per ADR-004: deny > user > role > dept > classification > default-deny
    # explicit deny for user -> decision.allowed = False
    assert decision.allowed is False
    assert decision.matched_rule == "deny"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_permissions_check_endpoint(client: TestClient) -> None:
    r = client.post(
        "/api/v1/permissions/check",
        json={
            "user_ref": "X-TEST-USER-002",
            "object_type": "document",
            "object_ref": "DOC-PUBLIC-001",
            "classification": "public",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "allowed" in body and "reason" in body and "matched_rule" in body
