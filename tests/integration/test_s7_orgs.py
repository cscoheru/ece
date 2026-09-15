"""Sprint 7 v0.2 — multi-tenant org scoping tests (cut-019).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: cross-org
isolation via `X-Org-Id` header on /audit + /debug. Env config
ECE_USER_ORGS="user1:org_a;user2:org_b" maps user_refs to orgs;
context_requests rows record org_id at assembly time; /audit/debug
enforce X-Org-Id match for cross-org access.
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.org import (
    check_org_access,
    get_user_org,
    is_multi_tenant_mode,
    parse_user_orgs,
)
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def own_request_id() -> str:
    """Create a context_request for demo-user-org-a via assemble_context.

    Returns the request_id (str of uuid).
    """
    engine = get_engine()
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a"
    try:
        pkg = assemble_context(
            engine=engine,
            user_ref="demo-user-org-a",
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR301"}],
        )
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
    return pkg.request_id


def test_parse_user_orgs_basic() -> None:
    """parse_user_orgs parses 'user1:org_a;user2:org_b' format."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a;bob:org_b;carol:org_a"
    try:
        assert parse_user_orgs() == {
            "alice": "org_a",
            "bob": "org_b",
            "carol": "org_a",
        }
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_parse_user_orgs_empty() -> None:
    """parse_user_orgs returns empty dict when env not set."""
    os.environ.pop("ECE_USER_ORGS", None)
    assert parse_user_orgs() == {}


def test_get_user_org_returns_org() -> None:
    """get_user_org returns mapped org_id for known users."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        assert get_user_org("alice") == "org_a"
        assert get_user_org("bob") is None
        assert get_user_org(None) is None
        assert get_user_org("") is None
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_is_multi_tenant_mode() -> None:
    """is_multi_tenant_mode returns True iff ECE_USER_ORGS is set."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ.pop("ECE_USER_ORGS", None)
    assert is_multi_tenant_mode() is False

    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        assert is_multi_tenant_mode() is True
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_check_org_access_disabled() -> None:
    """check_org_access always allows when ECE_USER_ORGS not set."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ.pop("ECE_USER_ORGS", None)
    try:
        allowed, code = check_org_access(None, None)
        assert allowed is True
        assert code == "ok"
        allowed, code = check_org_access("anything", "trace_org")
        assert allowed is True
        assert code == "ok"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_check_org_access_legacy_trace() -> None:
    """Legacy trace (org_id=NULL) is accessible without X-Org-Id even in multi-tenant mode."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        allowed, code = check_org_access(None, None)
        assert allowed is True
        assert code == "ok"
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_check_org_access_match() -> None:
    """X-Org-Id matches trace.org_id → allow."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        allowed, code = check_org_access("org_a", "org_a")
        assert allowed is True
        assert code == "ok"
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_check_org_access_required() -> None:
    """Multi-tenant + trace has org_id but X-Org-Id missing → reject."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        allowed, code = check_org_access(None, "org_a")
        assert allowed is False
        assert code == "org_id_required"
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_check_org_access_mismatch() -> None:
    """X-Org-Id != trace.org_id → cross-org blocked."""
    os.environ["ECE_USER_ORGS"] = "alice:org_a"
    try:
        allowed, code = check_org_access("org_b", "org_a")
        assert allowed is False
        assert code == "org_mismatch"
    finally:
        os.environ.pop("ECE_USER_ORGS", None)


def test_audit_context_with_matching_org_id(
    client: TestClient, own_request_id: str
) -> None:
    """/audit with matching X-Org-Id → 200."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a"
    try:
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={
                "X-User-Id": "demo-user-org-a",
                "X-Org-Id": "org_a",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_ref"] == "demo-user-org-a"
        assert body["org_id"] == "org_a"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_audit_context_with_missing_org_id_in_multi_tenant(
    client: TestClient, own_request_id: str
) -> None:
    """/audit without X-Org-Id in multi-tenant mode → 400."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a"
    try:
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-org-a"},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "bad_request"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_audit_context_cross_org_blocked(
    client: TestClient, own_request_id: str
) -> None:
    """/audit with X-Org-Id != trace.org_id → 403 (cross-org blocked)."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a;demo-user-org-b:org_b"
    try:
        # Caller is in org_b but trace was recorded for org_a
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={
                "X-User-Id": "demo-user-org-b",
                "X-Org-Id": "org_b",
            },
        )
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "forbidden"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_audit_context_single_tenant_no_org_header(
    client: TestClient, own_request_id: str
) -> None:
    """Single-tenant mode (ECE_USER_ORGS unset) → no X-Org-Id required."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ.pop("ECE_USER_ORGS", None)
    try:
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={"X-User-Id": "demo-user-org-a"},
        )
        assert r.status_code == 200, r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_debug_context_with_matching_org_id(
    client: TestClient, own_request_id: str
) -> None:
    """/debug with matching X-Org-Id → 200 HTML."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_mode = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a"
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={
                "X-User-Id": "demo-user-org-a",
                "X-Org-Id": "org_a",
            },
        )
        assert r.status_code == 200, r.text
        assert "<html" in r.text.lower()
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_mode is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_mode


def test_debug_context_cross_org_blocked(
    client: TestClient, own_request_id: str
) -> None:
    """/debug with cross-org X-Org-Id → 403."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_mode = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-a:org_a;demo-user-org-b:org_b"
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{own_request_id}",
            headers={
                "X-User-Id": "demo-user-org-b",
                "X-Org-Id": "org_b",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_mode is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_mode


def test_assemble_context_records_org_id() -> None:
    """assemble_context records user_org from ECE_USER_ORGS into context_requests."""
    engine = get_engine()
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = "demo-user-org-test:org_test"
    try:
        pkg = assemble_context(
            engine=engine,
            user_ref="demo-user-org-test",
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR999"}],
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved

    # Verify via get_context_trace
    from ece.audit.trace import get_context_trace

    trace = get_context_trace(engine, pkg.request_id)
    assert trace is not None
    assert trace["org_id"] == "org_test"
