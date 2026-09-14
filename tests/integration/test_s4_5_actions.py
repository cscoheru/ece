"""S4.5+ — POST /actions/preview endpoint tests.

Verifies:
1. create_task action returns preview (status='would_create')
2. send_message action returns preview (status='would_send')
3. unknown action → 400
4. missing user_id → 400

Per ADR-004 + ECE/CLAUDE.md: /actions/execute v0 disabled; this endpoint
mirrors the MCP create_task/send_message preview behavior.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_actions_preview_create_task(client: TestClient) -> None:
    """POST /actions/preview with action='create_task' returns preview."""
    r = client.post(
        "/api/v1/actions/preview",
        json={
            "user_id": "demo-user-procurement",
            "action": "create_task",
            "params": {"title": "Test Task", "description": "Test Description"},
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is True
    assert body["status"] == "would_create"
    assert body["title"] == "Test Task"


def test_actions_preview_send_message(client: TestClient) -> None:
    """POST /actions/preview with action='send_message' returns preview."""
    r = client.post(
        "/api/v1/actions/preview",
        json={
            "user_id": "demo-user-procurement",
            "action": "send_message",
            "params": {"to": "x@y.z", "body": "Test message body"},
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["preview"] is True
    assert body["status"] == "would_send"
    assert body["body_length"] == len("Test message body")


def test_actions_preview_unknown_action(client: TestClient) -> None:
    """POST /actions/preview with unknown action → 400."""
    r = client.post(
        "/api/v1/actions/preview",
        json={
            "user_id": "demo-user-procurement",
            "action": "nonexistent_action",
            "params": {},
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_actions_preview_requires_user_id(client: TestClient) -> None:
    """Missing X-User-Id AND body user_id → 400."""
    r = client.post(
        "/api/v1/actions/preview",
        json={"action": "create_task", "params": {"title": "x", "description": "y"}},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_actions_preview_user_id_body_fallback(client: TestClient) -> None:
    """Body user_id accepted if no header (back-compat per docs/API.md §0)."""
    r = client.post(
        "/api/v1/actions/preview",
        json={
            "user_id": "demo-user-procurement",
            "action": "create_task",
            "params": {"title": "Body fallback test", "description": "OK"},
        },
    )
    assert r.status_code == 200
