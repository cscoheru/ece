"""Sprint 9 v0.2 — per-resource delegation tests (cut-022).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: external auditors
given specific request_ids to investigate. Token grants access to those
request_ids only, regardless of who owns them or what org they're in.

Env:
    ECE_AUDIT_TOKEN_REQUEST_IDS="audit_tok:req_abc,req_xyz"

Token "audit_tok" can read req_abc and req_xyz specifically. It does NOT
grant access to other request_ids, even if owned by a user the auditor
otherwise has access to.
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.delegation import (
    parse_request_id_delegation_tokens,
    request_id_can_access,
)
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

USER_OWNER = "demo-per-resource-owner"
USER_OTHER = "demo-per-resource-other"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def alice_trace_id() -> str:
    """Create a trace owned by USER_OWNER (will be the granted request_id)."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_OWNER,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_PER_RES_1"}],
    )
    return pkg.request_id


@pytest.fixture
def bob_trace_id() -> str:
    """Create a trace owned by USER_OWNER (NOT in token's grant list)."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_OWNER,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_PER_RES_2"}],
    )
    return pkg.request_id


def test_parse_request_id_delegation_tokens_basic() -> None:
    """parse_request_id_delegation_tokens parses 'token:req_abc,req_xyz'."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = (
        "audit_tok:req_abc,req_xyz;other_tok:req_def"
    )
    try:
        assert parse_request_id_delegation_tokens() == {
            "audit_tok": ["req_abc", "req_xyz"],
            "other_tok": ["req_def"],
        }
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


def test_parse_request_id_delegation_tokens_empty() -> None:
    """parse_request_id_delegation_tokens returns empty dict when env unset."""
    os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
    assert parse_request_id_delegation_tokens() == {}


def test_request_id_can_access_match() -> None:
    """Token in env with request_id in list → True."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = "audit_tok:req_abc,req_xyz"
    try:
        assert request_id_can_access("audit_tok", "req_abc") is True
        assert request_id_can_access("audit_tok", "req_xyz") is True
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


def test_request_id_can_access_no_match() -> None:
    """request_id NOT in token's list → False."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = "audit_tok:req_abc"
    try:
        assert request_id_can_access("audit_tok", "req_xyz") is False
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


def test_request_id_can_access_no_token() -> None:
    """No token → False (regardless of request_id)."""
    assert request_id_can_access(None, "req_abc") is False
    assert request_id_can_access("", "req_abc") is False


def test_request_id_can_access_no_request_id() -> None:
    """No request_id → False (regardless of token)."""
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = "audit_tok:req_abc"
    try:
        assert request_id_can_access("audit_tok", None) is False
        assert request_id_can_access("audit_tok", "") is False
    finally:
        os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)


def test_request_id_can_access_token_not_in_env() -> None:
    """Token not in ECE_AUDIT_TOKEN_REQUEST_IDS env → False."""
    os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
    assert request_id_can_access("nonexistent_tok", "req_abc") is False


def test_audit_per_resource_grants_specific_request(
    client: TestClient, alice_trace_id: str
) -> None:
    """/audit with per-resource token → 200 for granted request_id."""
    saved = os.environ.get("ECE_AUDIT_TOKEN_REQUEST_IDS")
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{alice_trace_id}"
    try:
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={
                "X-User-Id": USER_OTHER,  # NOT the trace owner
                "X-Delegation-Token": "audit_tok",
                # No X-Org-Id — per-resource bypasses org check
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_ref"] == USER_OWNER
        assert body["request_id"] == alice_trace_id
    finally:
        if saved is None:
            os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
        else:
            os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = saved


def test_audit_per_resource_denies_other_request(
    client: TestClient, bob_trace_id: str
) -> None:
    """/audit with per-resource token for DIFFERENT request_id → 403."""
    saved = os.environ.get("ECE_AUDIT_TOKEN_REQUEST_IDS")
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = "audit_tok:req_some_other"
    try:
        # bob_trace_id is not in token's list; user_other has no per-user
        # or per-org token; no X-Org-Id → 403
        r = client.get(
            f"/api/v1/audit/context/{bob_trace_id}",
            headers={
                "X-User-Id": USER_OTHER,
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 403, r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
        else:
            os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = saved


def test_audit_per_resource_no_token_uses_other_paths(
    client: TestClient, alice_trace_id: str
) -> None:
    """/audit without per-resource token falls through to standard checks."""
    saved = os.environ.get("ECE_AUDIT_TOKEN_REQUEST_IDS")
    os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
    try:
        # No per-resource token, USER_OTHER is not owner → 403
        r = client.get(
            f"/api/v1/audit/context/{alice_trace_id}",
            headers={"X-User-Id": USER_OTHER},
        )
        assert r.status_code == 403, r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
        else:
            os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = saved


def test_debug_per_resource_grants_specific_request(
    client: TestClient, alice_trace_id: str
) -> None:
    """/debug with per-resource token → 200 HTML."""
    saved_rq = os.environ.get("ECE_AUDIT_TOKEN_REQUEST_IDS")
    saved_mode = os.environ.get("ECE_DEPLOYMENT_MODE")
    os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = f"audit_tok:{alice_trace_id}"
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    try:
        r = client.get(
            f"/debug/context/{alice_trace_id}",
            headers={
                "X-User-Id": USER_OTHER,
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 200, r.text
        assert "<html" in r.text.lower()
    finally:
        if saved_rq is None:
            os.environ.pop("ECE_AUDIT_TOKEN_REQUEST_IDS", None)
        else:
            os.environ["ECE_AUDIT_TOKEN_REQUEST_IDS"] = saved_rq
        if saved_mode is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_mode
