"""Sprint 8 v0.2 — cross-org delegation tests (cut-021).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: cross-org read
via `ECE_DELEGATION_ORG_TOKENS` env. Token bearer can read users in
listed orgs (resolved via ECE_USER_ORGS) without X-Org-Id match.

Env:
    ECE_USER_ORGS="alice:org_a;bob:org_b;manager_x:org_x"
    ECE_DELEGATION_ORG_TOKENS="manager_tok:org_a,org_b;audit_tok:*"

manager_x with token "manager_tok" can read alice (org_a) AND bob
(org_b) traces. With "audit_tok:*" token, any user can read all
orgs (wildcard audit role).
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.delegation import (
    parse_org_delegation_tokens,
    resolve_user_refs,
)
from ece.api.org import check_org_access
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

ORG_A = "org_a"
ORG_B = "org_b"
ORG_X = "org_x"
USER_ALICE = "demo-cross-alice"  # org_a
USER_BOB = "demo-cross-bob"  # org_b
USER_MANAGER = "demo-cross-manager"  # org_x (no relation to org_a/b)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def alice_request_id() -> str:
    """Create a trace for USER_ALICE (org_a)."""
    engine = get_engine()
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    try:
        pkg = assemble_context(
            engine=engine,
            user_ref=USER_ALICE,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR_CROSS_A"}],
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved
    return pkg.request_id


@pytest.fixture
def bob_request_id() -> str:
    """Create a trace for USER_BOB (org_b)."""
    engine = get_engine()
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    try:
        pkg = assemble_context(
            engine=engine,
            user_ref=USER_BOB,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR_CROSS_B"}],
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved
    return pkg.request_id


def test_parse_org_delegation_tokens_basic() -> None:
    """parse_org_delegation_tokens parses 'token:org_a,org_b' format."""
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager:org_a,org_b;auditor:org_c"
    try:
        assert parse_org_delegation_tokens() == {
            "manager": ["org_a", "org_b"],
            "auditor": ["org_c"],
        }
    finally:
        os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)


def test_parse_org_delegation_tokens_wildcard() -> None:
    """parse_org_delegation_tokens accepts '*' wildcard (audit role)."""
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "audit:*"
    try:
        assert parse_org_delegation_tokens() == {"audit": ["*"]}
    finally:
        os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)


def test_parse_org_delegation_tokens_empty() -> None:
    """parse_org_delegation_tokens returns empty dict when env not set."""
    os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
    assert parse_org_delegation_tokens() == {}


def test_resolve_user_refs_includes_org_token_users() -> None:
    """resolve_user_refs adds users in token's orgs."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B}"
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager:org_a"
    try:
        refs = resolve_user_refs(
            x_user_id=USER_MANAGER, x_delegation_token="manager"
        )
        # Should include alice (org_a, in token's org list) + manager (self)
        assert USER_ALICE in refs
        assert USER_MANAGER in refs
        # bob is in org_b, NOT in token's orgs
        assert USER_BOB not in refs
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_resolve_user_refs_wildcard_org_token() -> None:
    """Wildcard '*' org token includes all mapped users."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B}"
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "audit:*"
    try:
        refs = resolve_user_refs(
            x_user_id=USER_MANAGER, x_delegation_token="audit"
        )
        assert USER_ALICE in refs
        assert USER_BOB in refs
        assert USER_MANAGER in refs  # self
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_check_org_access_delegated_cross_org() -> None:
    """Token with trace's org in its org list → allow cross-org access."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager_tok:org_a,org_b"
    try:
        # manager_x (org_x) with manager_tok accessing org_a trace
        allowed, code = check_org_access(
            x_org_id=ORG_X,
            trace_org_id=ORG_A,
            x_delegation_token="manager_tok",
        )
        assert allowed is True
        assert code == "ok"
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_check_org_access_token_does_not_grant_unlisted_org() -> None:
    """Token with org_a only — cannot access org_b."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager_tok:org_a"
    try:
        # Token includes only org_a. Caller claims x_org_id=org_x (their own
        # org). Trace is in org_b. Standard X-Org-Id check → org_mismatch.
        allowed, code = check_org_access(
            x_org_id=ORG_X,
            trace_org_id=ORG_B,
            x_delegation_token="manager_tok",
        )
        assert allowed is False
        assert code == "org_mismatch"
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_check_org_access_invalid_token_falls_through_to_org_check() -> None:
    """Invalid token (not in env) falls through to standard X-Org-Id check."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
    try:
        # Token not in env, x_org_id mismatch → 403
        allowed, code = check_org_access(
            x_org_id=ORG_X,
            trace_org_id=ORG_A,
            x_delegation_token="nonexistent_tok",
        )
        assert allowed is False
        assert code == "org_mismatch"
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_audit_cross_org_with_delegation_token(
    client: TestClient, alice_request_id: str
) -> None:
    """/audit cross-org access via org delegation token → 200."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager_tok:org_a,org_b"
    try:
        # manager_x (org_x) with manager_tok reading alice's (org_a) trace
        r = client.get(
            f"/api/v1/audit/context/{alice_request_id}",
            headers={
                "X-User-Id": USER_MANAGER,
                "X-Delegation-Token": "manager_tok",
                # No X-Org-Id — token grants cross-org access
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_ref"] == USER_ALICE
        assert body["org_id"] == ORG_A
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_audit_cross_org_without_token_blocked(
    client: TestClient, alice_request_id: str
) -> None:
    """/audit cross-org without delegation token → 403."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    try:
        # manager_x (org_x) with own org token (not in env) → no override
        r = client.get(
            f"/api/v1/audit/context/{alice_request_id}",
            headers={
                "X-User-Id": USER_MANAGER,
                "X-Org-Id": ORG_X,
            },
        )
        assert r.status_code == 403, r.text
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs


def test_audit_wildcard_org_token_grants_all_orgs(
    client: TestClient, alice_request_id: str, bob_request_id: str
) -> None:
    """/audit with wildcard '*' org token grants access to all orgs."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "audit_tok:*"
    try:
        for trace_id, expected_owner in [
            (alice_request_id, USER_ALICE),
            (bob_request_id, USER_BOB),
        ]:
            r = client.get(
                f"/api/v1/audit/context/{trace_id}",
                headers={
                    "X-User-Id": USER_MANAGER,
                    "X-Delegation-Token": "audit_tok",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["user_ref"] == expected_owner
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks


def test_debug_cross_org_with_delegation_token(
    client: TestClient, alice_request_id: str
) -> None:
    """/debug cross-org access via org delegation token → 200 HTML."""
    saved_orgs = os.environ.get("ECE_USER_ORGS")
    saved_org_toks = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    saved_mode = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_USER_ORGS"] = (
        f"{USER_ALICE}:{ORG_A};{USER_BOB}:{ORG_B};{USER_MANAGER}:{ORG_X}"
    )
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "manager_tok:org_a,org_b"
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{alice_request_id}",
            headers={
                "X-User-Id": USER_MANAGER,
                "X-Delegation-Token": "manager_tok",
            },
        )
        assert r.status_code == 200, r.text
        assert "<html" in r.text.lower()
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs
        if saved_org_toks is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_org_toks
        if saved_mode is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_mode
