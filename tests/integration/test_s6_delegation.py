"""Sprint 6 v0.1 deployment — multi-user PermissionScope delegation tests (cut-018b).

Per ECE/CLAUDE.md 私有化 acceptance + v0.1 deployment hardening:
multi-user sharing via `X-Delegation-Token` header. Env config
ECE_DELEGATION_TOKENS="token1:user1,user2;token2:user3" grants
managers / shared-services access to multiple users' audit traces.
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.delegation import (
    parse_delegation_tokens,
    resolve_user_refs,
    user_can_access,
)
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


def test_parse_delegation_tokens_basic() -> None:
    """parse_delegation_tokens parses 'token1:user1,user2;token2:user3' format."""
    os.environ["ECE_DELEGATION_TOKENS"] = "secret_abc:demo-user-procurement,demo-user-finance;secret_def:demo-user-engineering"
    try:
        tokens = parse_delegation_tokens()
        assert tokens == {
            "secret_abc": ["demo-user-procurement", "demo-user-finance"],
            "secret_def": ["demo-user-engineering"],
        }
    finally:
        os.environ.pop("ECE_DELEGATION_TOKENS", None)


def test_parse_delegation_tokens_empty() -> None:
    """parse_delegation_tokens returns empty dict when env not set."""
    os.environ.pop("ECE_DELEGATION_TOKENS", None)
    assert parse_delegation_tokens() == {}


def test_resolve_user_refs_with_token() -> None:
    """resolve_user_refs returns listed users + x_user_id (self)."""
    os.environ["ECE_DELEGATION_TOKENS"] = "secret:demo-user-finance"
    try:
        refs = resolve_user_refs(
            x_user_id="demo-user-procurement",
            x_delegation_token="secret",
        )
        # Should include delegated user + self
        assert "demo-user-finance" in refs
        assert "demo-user-procurement" in refs
    finally:
        os.environ.pop("ECE_DELEGATION_TOKENS", None)


def test_resolve_user_refs_without_token() -> None:
    """resolve_user_refs returns just x_user_id when no token."""
    refs = resolve_user_refs(
        x_user_id="demo-user-procurement",
        x_delegation_token=None,
    )
    assert refs == ["demo-user-procurement"]


def test_user_can_access_owner() -> None:
    """Owner can always access their own trace (no token needed)."""
    assert user_can_access(
        x_user_id="demo-user-procurement",
        x_delegation_token=None,
        trace_user_ref="demo-user-procurement",
    ) is True


def test_user_can_access_delegated() -> None:
    """Delegated user can access if trace_user_ref in token's list."""
    os.environ["ECE_DELEGATION_TOKENS"] = "secret:demo-user-procurement"
    try:
        # Manager with token "secret" (delegated to demo-user-procurement) can
        # access that user's trace even if manager's own x_user_id differs.
        assert user_can_access(
            x_user_id="demo-user-finance",
            x_delegation_token="secret",
            trace_user_ref="demo-user-procurement",
        ) is True
    finally:
        os.environ.pop("ECE_DELEGATION_TOKENS", None)


def test_user_can_access_rejected() -> None:
    """User without delegation cannot access other user's trace."""
    os.environ["ECE_DELEGATION_TOKENS"] = "secret:demo-user-finance"
    try:
        # demo-user-engineering has no delegation; cannot access
        # demo-user-procurement's trace.
        assert user_can_access(
            x_user_id="demo-user-engineering",
            x_delegation_token=None,
            trace_user_ref="demo-user-procurement",
        ) is False
    finally:
        os.environ.pop("ECE_DELEGATION_TOKENS", None)


def test_audit_context_with_valid_delegation_token(
    client: TestClient, own_request_id: str
) -> None:
    """/audit with X-Delegation-Token grants access to delegated user's trace."""
    saved = os.environ.get("ECE_DELEGATION_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = "secret_token:demo-user-procurement"
    try:
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={
                "X-Delegation-Token": "secret_token",
                "X-User-Id": "demo-user-finance",  # the bearer
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_ref"] == "demo-user-procurement"  # the trace owner
    finally:
        if saved is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved


def test_audit_context_with_invalid_delegation_token(
    client: TestClient, own_request_id: str
) -> None:
    """/audit with X-Delegation-Token not matching any user → 403."""
    saved = os.environ.get("ECE_DELEGATION_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = "valid_token:demo-user-procurement"
    try:
        r = client.get(
            f"/api/v1/audit/context/{own_request_id}",
            headers={
                "X-Delegation-Token": "WRONG_token",
                "X-User-Id": "demo-user-finance",
            },
        )
        assert r.status_code == 403
    finally:
        if saved is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved


def test_audit_context_requires_user_or_token(
    client: TestClient, own_request_id: str
) -> None:
    """/audit with neither X-User-Id nor X-Delegation-Token → 400."""
    saved = os.environ.get("ECE_DELEGATION_TOKENS")
    os.environ.pop("ECE_DELEGATION_TOKENS", None)
    try:
        r = client.get(f"/api/v1/audit/context/{own_request_id}")
        assert r.status_code == 400
    finally:
        if saved is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved
