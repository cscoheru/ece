"""S3.4 — POST /context endpoint tests.

Per docs/API.md §1:
- POST /api/v1/context assembles Context Package
- 200 with package body, 400 on missing user, 404 on unknown spec
- Anti-probing: missing resources + forbidden resources uniform envelope

Pre-condition: alembic head = 0005_context_audit + demo seed (≥1 PR).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_post_context_requires_user_id(client: TestClient) -> None:
    """Missing X-User-Id AND user_id body → 400."""
    r = client.post("/api/v1/context", json={
        "intent": "evaluate_purchase_request",
        "entities": [],
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_post_context_with_x_user_id_header(client: TestClient) -> None:
    """X-User-Id header accepted; user dict populated."""
    r = client.post(
        "/api/v1/context",
        json={
            "intent": "evaluate_purchase_request",
            "entities": [{"type": "purchase_request", "id": "PR001"}],
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == "demo-user-procurement"
    assert body["user"]["department"] == "procurement"
    assert "procurement_manager" in body["user"]["roles"]
    assert body["task"]["intent"] == "evaluate_purchase_request"


def test_post_context_user_id_body_fallback(client: TestClient) -> None:
    """No header but body user_id accepted (back-compat per docs/API.md §0)."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "evaluate_purchase_request",
            "entities": [],
        },
    )
    assert r.status_code == 200
    assert r.json()["user"]["id"] == "demo-user-procurement"


def test_post_context_unknown_intent_returns_404(client: TestClient) -> None:
    """Unknown intent → 404 (anti-probing: not_found envelope)."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "does_not_exist_intent",
            "entities": [],
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_post_context_insufficient_when_no_entities(client: TestClient) -> None:
    """No root entities → insufficient_context flag + empty lists."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "evaluate_purchase_request",
            "entities": [],
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["insufficient_context"] is True
    assert body["entities"] == []
    assert body["relationships"] == []
    assert body["request_id"]  # uuid assigned


def test_post_context_denied_entity_recorded(client: TestClient) -> None:
    """Non-existent entity → denied list contains ref; insufficient flag set."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "evaluate_purchase_request",
            "entities": [{"type": "purchase_request", "id": "PR_DOES_NOT_EXIST"}],
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    body = r.json()
    assert any(d.get("ref") == "PR_DOES_NOT_EXIST" for d in body["denied"])
    assert body["metadata"]["insufficient_context"] is True
    assert body["metadata"]["counts"]["denied"] >= 1


def test_post_context_response_structure(client: TestClient) -> None:
    """Response has all ContextPackage fields per ARCHITECTURE §2.2."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "evaluate_purchase_request",
            "entities": [],
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    body = r.json()
    # Required keys per ContextPackage + ContextResponse
    required_keys = {
        "package_id", "request_id", "task", "user",
        "entities", "relationships", "documents", "business_data",
        "denied", "sources", "metadata",
    }
    assert required_keys.issubset(body.keys()), (
        f"missing keys: {required_keys - body.keys()}"
    )


def test_post_context_with_as_of(client: TestClient) -> None:
    """as_of parameter accepted (no error; may affect query)."""
    r = client.post(
        "/api/v1/context",
        json={
            "user_id": "demo-user-procurement",
            "intent": "evaluate_purchase_request",
            "entities": [{"type": "purchase_request", "id": "PR001"}],
            "as_of": "2025-12-31",
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    assert r.json()["metadata"]["as_of"] == "2025-12-31"
