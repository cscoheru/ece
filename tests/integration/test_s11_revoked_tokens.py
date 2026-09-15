"""Sprint 11 v0.2 — token revocation tests (cut-024).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: compromised
tokens can be revoked via `ECE_REVOKED_TOKENS` env. Revoked tokens
grant NO access via per-user / per-org / per-resource paths.

Env format:
    ECE_REVOKED_TOKENS="compromised_tok_1,leaked_tok_2"

Behavior:
- Revoked token: treated as no token (X-Delegation-Token effects disabled)
- Owner access via X-User-Id still works (revocation only disables delegation grants)
- No env restart required (env is re-read on each request via os.environ.get)
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.delegation import (
    is_token_revoked,
    parse_revoked_tokens,
    resolve_user_refs,
    user_can_access,
)
from ece.api.org import check_org_access
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

USER_OWNER = "demo-revocation-owner"
USER_OTHER = "demo-revocation-other"
ORG_A = "org_a"
ORG_B = "org_b"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def alice_trace_id() -> str:
    """Create a trace owned by USER_OWNER."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_OWNER,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_REV_1"}],
    )
    return pkg.request_id


def test_parse_revoked_tokens_basic() -> None:
    """parse_revoked_tokens parses comma-separated list."""
    os.environ["ECE_REVOKED_TOKENS"] = "tok_a,tok_b,tok_c"
    try:
        assert parse_revoked_tokens() == {"tok_a", "tok_b", "tok_c"}
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)


def test_parse_revoked_tokens_empty() -> None:
    """parse_revoked_tokens returns empty set when env not set."""
    os.environ.pop("ECE_REVOKED_TOKENS", None)
    assert parse_revoked_tokens() == set()


def test_is_token_revoked_match() -> None:
    """Token in revocation list → True."""
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        assert is_token_revoked("bad_tok") is True
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)


def test_is_token_revoked_not_in_list() -> None:
    """Token not in revocation list → False."""
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        assert is_token_revoked("good_tok") is False
    finally:
        os.environ.pop("ECE_REVOKED_TOKENS", None)


def test_is_token_revoked_no_token() -> None:
    """No token → False."""
    assert is_token_revoked(None) is False
    assert is_token_revoked("") is False


def test_resolve_user_refs_revoked_token_treated_as_none() -> None:
    """Revoked token → treated as no token in resolve_user_refs."""
    saved_users = os.environ.get("ECE_DELEGATION_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = "good_tok:some_user;bad_tok:other_user"
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        # good_tok still works
        refs = resolve_user_refs(x_user_id="caller", x_delegation_token="good_tok")
        assert "some_user" in refs
        # bad_tok is revoked → no users added
        refs = resolve_user_refs(x_user_id="caller", x_delegation_token="bad_tok")
        assert "other_user" not in refs
        # self still added
        assert "caller" in refs
    finally:
        if saved_users is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved_users
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_TOKENS", None)
        else:
            os.environ["ECE_REVOKED_TOKENS"] = saved_rev


def test_user_can_access_revoked_token_owner_still_allowed() -> None:
    """Owner check bypasses revocation (X-User-Id == trace.user_ref)."""
    assert (
        user_can_access(
            x_user_id=USER_OWNER,
            x_delegation_token="bad_tok",  # would be revoked, but owner
            trace_user_ref=USER_OWNER,
        )
        is True
    )


def test_user_can_access_revoked_token_blocks_delegated() -> None:
    """Revoked token blocks delegated access for non-owner."""
    saved_users = os.environ.get("ECE_DELEGATION_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = "bad_tok:some_user"
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        # bad_tok would grant access to some_user, but is revoked
        assert (
            user_can_access(
                x_user_id=USER_OTHER,
                x_delegation_token="bad_tok",
                trace_user_ref="some_user",
            )
            is False
        )
    finally:
        if saved_users is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved_users
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_TOKENS", None)
        else:
            os.environ["ECE_REVOKED_TOKENS"] = saved_rev


def test_check_org_access_revoked_token_blocks_cross_org() -> None:
    """Revoked token blocks cross-org access (per-org delegation disabled)."""
    saved_users = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_OWNER}:{ORG_A};{USER_OTHER}:{ORG_B}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "bad_tok:org_a,org_b"
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        # bad_tok would grant access to org_a (USER_OWNER's org), but is revoked
        allowed, code = check_org_access(
            x_org_id=ORG_B,
            trace_org_id=ORG_A,
            x_delegation_token="bad_tok",
        )
        assert allowed is False
        assert code == "token_revoked"
    finally:
        if saved_users is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_users
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_TOKENS", None)
        else:
            os.environ["ECE_REVOKED_TOKENS"] = saved_rev


def test_audit_revoked_token_blocks_delegation(
    client: TestClient, alice_trace_id: str
) -> None:
    """/audit with revoked token → 403 (delegation disabled, owner-only fails)."""
    saved_users = os.environ.get("ECE_DELEGATION_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = f"bad_tok:{USER_OWNER}"
    os.environ["ECE_REVOKED_TOKENS"] = "bad_tok"
    try:
        # USER_OTHER is not owner; bad_tok would grant access but is revoked
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={
                "X-User-Id": USER_OTHER,
                "X-Delegation-Token": "bad_tok",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        if saved_users is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved_users
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_TOKENS", None)
        else:
            os.environ["ECE_REVOKED_TOKENS"] = saved_rev


def test_audit_owner_access_unaffected_by_revocation(
    client: TestClient, alice_trace_id: str
) -> None:
    """/audit as owner works regardless of revoked tokens in env."""
    saved_users = os.environ.get("ECE_DELEGATION_TOKENS")
    saved_rev = os.environ.get("ECE_REVOKED_TOKENS")
    os.environ["ECE_DELEGATION_TOKENS"] = "any_tok:some_user"
    os.environ["ECE_REVOKED_TOKENS"] = "any_tok"
    try:
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={"X-User-Id": USER_OWNER},
        )
        assert r.status_code == 200, r.text
    finally:
        if saved_users is None:
            os.environ.pop("ECE_DELEGATION_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_TOKENS"] = saved_users
        if saved_rev is None:
            os.environ.pop("ECE_REVOKED_TOKENS", None)
        else:
            os.environ["ECE_REVOKED_TOKENS"] = saved_rev
