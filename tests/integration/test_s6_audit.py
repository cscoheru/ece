"""Sprint 6 — /audit/context + Debugger UI tests.

Verifies:
1. /audit/context returns trace (JSON) for own request_id
2. /audit/context returns 403 for other user's trace
3. /audit/context returns 404 for non-existent
4. /debug/context returns HTML in local mode (ECE_DEPLOYMENT_MODE=local)
5. /debug/context returns 404 in production mode

Pre-condition: scripts/seed_relationships.py run + demo seed.
"""
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def own_request_id() -> Iterator[str]:
    """Create a context_request via assemble_context; return its id."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR201"}],
    )
    yield pkg.request_id
    # Cleanup not needed; assemble_context writes to context_requests + context_items


def test_audit_context_endpoint_requires_x_user_id(
    client: TestClient, own_request_id: str
) -> None:
    """Missing X-User-Id header → 400."""
    r = client.get(f"/api/v1/audit/context/{own_request_id}")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_audit_context_not_found(client: TestClient) -> None:
    """Non-existent request_id → 404."""
    r = client.get(
        "/api/v1/audit/context/00000000-0000-0000-0000-000000000000",
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_audit_context_returns_trace(
    client: TestClient, own_request_id: str
) -> None:
    """Existing request_id returns trace with metadata + items."""
    r = client.get(
        f"/api/v1/audit/context/{own_request_id}",
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_ref"] == "demo-user-procurement"
    assert body["intent"] == "evaluate_purchase_request"
    assert "items" in body
    assert isinstance(body["items"], list)
    assert body["latency_ms"] is not None


def test_audit_context_forbidden_other_user(
    client: TestClient, own_request_id: str
) -> None:
    """Other user accessing trace → 403 (per ADR-004 PermissionScope)."""
    r = client.get(
        f"/api/v1/audit/context/{own_request_id}",
        headers={"X-User-Id": "demo-user-finance"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "forbidden"


def test_debug_context_404_in_production(client: TestClient) -> None:
    """/debug/* returns 404 in production (ECE_DEPLOYMENT_MODE=production)."""
    saved = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_DEPLOYMENT_MODE"] = "production"
    try:
        r = client.get(
            "/debug/context/00000000-0000-0000-0000-000000000000",
            headers={"X-User-Id": "demo-user-procurement"},
        )
        assert r.status_code == 404
    finally:
        if saved is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved


def test_debug_context_html_in_local(
    client: TestClient, own_request_id: str
) -> None:
    """/debug/* returns HTML in local mode (default for dev)."""
    saved = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-procurement"},
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/html")
        assert "Context Trace" in r.text
        assert own_request_id in r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved


def test_debug_context_forbidden_other_user_local(
    client: TestClient, own_request_id: str
) -> None:
    """/debug/* enforces same PermissionScope as /audit/* (per ADR-004)."""
    saved = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-finance"},
        )
        assert r.status_code == 403
    finally:
        if saved is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved


def test_audit_trace_module_importable() -> None:
    """get_context_trace is importable + has Engine + request_id params."""
    from ece.audit.trace import get_context_trace
    assert callable(get_context_trace)
    import inspect
    sig = inspect.signature(get_context_trace)
    assert "engine" in sig.parameters
    assert "request_id" in sig.parameters
