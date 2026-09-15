"""Sprint 14 v0.2 — user-level revocation tests (cut-028).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: revoked users
(ECE_REVOKED_USERS env) are denied ALL access — even owner check on
their own traces. Different from cut-024 (token revocation) which
preserves owner access.

Use cases:
- Firing an employee: add their user_ref to ECE_REVOKED_USERS
- Terminated account: same
- Banned user: same

Env format:
    ECE_REVOKED_USERS="fired_employee,banned_user,terminated_contractor"
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.delegation import (
    is_user_revoked,
    parse_revoked_users,
    user_can_access,
)
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

USER_FIRED = "demo-user-fired"
USER_OTHER = "demo-user-other-ok"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fired_trace_id() -> str:
    """Create a trace owned by USER_FIRED (before they were revoked)."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_FIRED,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_FIRED_1"}],
    )
    return pkg.request_id


def test_parse_revoked_users_basic() -> None:
    """parse_revoked_users parses comma-separated list."""
    os.environ["ECE_REVOKED_USERS"] = "alice,bob,carol"
    try:
        assert parse_revoked_users() == {"alice", "bob", "carol"}
    finally:
        os.environ.pop("ECE_REVOKED_USERS", None)


def test_parse_revoked_users_empty() -> None:
    """parse_revoked_users returns empty set when env not set."""
    os.environ.pop("ECE_REVOKED_USERS", None)
    assert parse_revoked_users() == set()


def test_is_user_revoked_match() -> None:
    """User in revocation list → True."""
    os.environ["ECE_REVOKED_USERS"] = "fired_user"
    try:
        assert is_user_revoked("fired_user") is True
    finally:
        os.environ.pop("ECE_REVOKED_USERS", None)


def test_is_user_revoked_not_in_list() -> None:
    """User not in revocation list → False."""
    os.environ["ECE_REVOKED_USERS"] = "fired_user"
    try:
        assert is_user_revoked("active_user") is False
    finally:
        os.environ.pop("ECE_REVOKED_USERS", None)


def test_is_user_revoked_no_user() -> None:
    """No user_ref → False."""
    assert is_user_revoked(None) is False
    assert is_user_revoked("") is False


def test_user_can_access_revoked_caller_blocks_owner() -> None:
    """Revoked caller cannot access even own trace (cut-028 stronger than cut-024)."""
    saved = os.environ.get("ECE_REVOKED_USERS")
    os.environ["ECE_REVOKED_USERS"] = USER_FIRED
    try:
        # USER_FIRED is the owner of a trace but is now revoked
        # cut-024 (token revocation) would still allow owner access
        # cut-028 (user revocation) blocks even owner
        assert (
            user_can_access(
                x_user_id=USER_FIRED,
                x_delegation_token=None,
                trace_user_ref=USER_FIRED,
            )
            is False
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_REVOKED_USERS", None)
        else:
            os.environ["ECE_REVOKED_USERS"] = saved


def test_user_can_access_revoked_owner_blocks_delegated() -> None:
    """Revoked trace owner blocks delegated access to that trace."""
    saved = os.environ.get("ECE_REVOKED_USERS")
    os.environ["ECE_REVOKED_USERS"] = USER_FIRED
    try:
        # USER_OTHER with valid delegation to USER_FIRED's traces
        # USER_FIRED is revoked → their traces are inaccessible
        assert (
            user_can_access(
                x_user_id=USER_OTHER,
                x_delegation_token=None,
                trace_user_ref=USER_FIRED,
            )
            is False
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_REVOKED_USERS", None)
        else:
            os.environ["ECE_REVOKED_USERS"] = saved


def test_user_can_access_non_revoked_unaffected() -> None:
    """Non-revoked users retain normal access patterns."""
    saved = os.environ.get("ECE_REVOKED_USERS")
    os.environ["ECE_REVOKED_USERS"] = "some_other_user"
    try:
        # USER_FIRED's user_ref is NOT in revocation list
        assert (
            user_can_access(
                x_user_id=USER_FIRED,
                x_delegation_token=None,
                trace_user_ref=USER_FIRED,
            )
            is True
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_REVOKED_USERS", None)
        else:
            os.environ["ECE_REVOKED_USERS"] = saved


def test_audit_revoked_user_blocks_own_trace(
    client: TestClient, fired_trace_id: str
) -> None:
    """/audit: revoked user cannot access own trace → 403."""
    saved = os.environ.get("ECE_REVOKED_USERS")
    os.environ["ECE_REVOKED_USERS"] = USER_FIRED
    try:
        r = client.get(
            f"/api/v1/audit/context/{fired_trace_id}",
            headers={"X-User-Id": USER_FIRED},
        )
        assert r.status_code == 403, r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_REVOKED_USERS", None)
        else:
            os.environ["ECE_REVOKED_USERS"] = saved


def test_audit_revoked_user_blocks_delegated_access(
    client: TestClient, fired_trace_id: str
) -> None:
    """/audit: trace of revoked user is inaccessible to all → 403."""
    saved_users = os.environ.get("ECE_DELEGATION_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_USERS")
    os.environ["ECE_DELEGATION_TOKENS"] = f"manager_tok:{USER_FIRED}"
    os.environ["ECE_REVOKED_USERS"] = USER_FIRED
    try:
        # Even with delegation token granting access to USER_FIRED's traces,
        # USER_FIRED being revoked blocks all access to those traces
        r = client.get(
            f"/api/v1/audit/context/{fired_trace_id}",
            headers={
                "X-User-Id": USER_OTHER,
                "X-Delegation-Token": "manager_tok",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        if saved_users is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved_users
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_USERS", None)
        else:
            os.environ["ECE_REVOKED_USERS"] = saved_rev


def test_cut024_vs_cut028_difference() -> None:
    """cut-024 (token revoke) preserves owner; cut-028 (user revoke) blocks owner."""
    # cut-024 scenario: USER_FIRED is owner, token revoked
    os.environ.pop("ECE_REVOKED_USERS", None)
    os.environ["ECE_REVOKED_TOKENS"] = "irrelevant_token"
    try:
        # Owner can still access even with revoked token in env
        assert (
            user_can_access(
                x_user_id=USER_FIRED,
                x_delegation_token="irrelevant_token",
                trace_user_ref=USER_FIRED,
            )
            is True
        )
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)

    # cut-028 scenario: USER_FIRED is owner, USER_FIRED is revoked
    os.environ["ECE_REVOKED_USERS"] = USER_FIRED
    try:
        # Owner cannot access own trace when revoked
        assert (
            user_can_access(
                x_user_id=USER_FIRED,
                x_delegation_token=None,
                trace_user_ref=USER_FIRED,
            )
            is False
        )
    finally:
        os.environ.pop("ECE_REVOKED_USERS", None)
