"""Sprint 6 v0.1 deployment — /debug IP allowlist tests (cut-018a).

Per ECE/CLAUDE.md 私有化 acceptance + v0.1 deployment hardening:
/debug/* only accessible from localhost by default (prevent audit
trace leakage to external networks). Override via DEBUG_ALLOWED_HOSTS
env var (comma-separated hosts).
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def own_request_id() -> str:
    """Create a context_request via assemble_context; return its id."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR201"}],
    )
    return pkg.request_id


def test_debug_context_localhost_allowed_default(
    client: TestClient, own_request_id: str
) -> None:
    """/debug/* allows 'testclient' host (default DEBUG_ALLOWED_HOSTS includes it)."""
    saved_dep = os.environ.get("ECE_DEPLOYMENT_MODE")
    saved_hosts = os.environ.get("DEBUG_ALLOWED_HOSTS")
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    os.environ.pop("DEBUG_ALLOWED_HOSTS", None)  # use default
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-procurement"},
        )
        assert r.status_code == 200, r.text
    finally:
        if saved_dep is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_dep
        if saved_hosts is None:
            os.environ.pop("DEBUG_ALLOWED_HOSTS", None)
        else:
            os.environ["DEBUG_ALLOWED_HOSTS"] = saved_hosts


def test_debug_context_remote_blocked(
    client: TestClient, own_request_id: str
) -> None:
    """/debug/* returns 403 when DEBUG_ALLOWED_HOSTS excludes 'testclient' (anti-exposure)."""
    saved_dep = os.environ.get("ECE_DEPLOYMENT_MODE")
    saved_hosts = os.environ.get("DEBUG_ALLOWED_HOSTS")
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    # Tighten allowlist to exclude 'testclient' (simulates remote access)
    os.environ["DEBUG_ALLOWED_HOSTS"] = "127.0.0.1,::1"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-procurement"},
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "forbidden"
        assert "localhost" in r.json()["detail"]["message"]
    finally:
        if saved_dep is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_dep
        if saved_hosts is None:
            os.environ.pop("DEBUG_ALLOWED_HOSTS", None)
        else:
            os.environ["DEBUG_ALLOWED_HOSTS"] = saved_hosts


def test_debug_context_env_override_allowlist(
    client: TestClient, own_request_id: str
) -> None:
    """DEBUG_ALLOWED_HOSTS=* allows any client (override for testing)."""
    saved_dep = os.environ.get("ECE_DEPLOYMENT_MODE")
    saved_hosts = os.environ.get("DEBUG_ALLOWED_HOSTS")
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    # Allow all hosts (e.g., for internal proxy / load balancer in front)
    os.environ["DEBUG_ALLOWED_HOSTS"] = "*"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-procurement"},
        )
        assert r.status_code == 200, r.text
    finally:
        if saved_dep is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_dep
        if saved_hosts is None:
            os.environ.pop("DEBUG_ALLOWED_HOSTS", None)
        else:
            os.environ["DEBUG_ALLOWED_HOSTS"] = saved_hosts
