"""Sprint 10 v0.2 — org-level rate limit tests (cut-023).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: org-level rate
limit via `ECE_ORG_RATE_LIMITS` env for /audit + /debug. Prevents
runaway scripts / audit storms.

Env format:
    ECE_ORG_RATE_LIMITS="org_a:5/m;org_b:100/h"

`N/period` where period is s|m|h|d. Fixed-window counter: bucket
refills to N after period elapses.
"""
import os

import pytest
from fastapi.testclient import TestClient

from ece.api.rate_limit import (
    _period_to_seconds,
    check_rate_limit,
    parse_org_rate_limits,
    reset_buckets,
)
from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

USER_OWNER = "demo-rate-limit-owner"


@pytest.fixture(autouse=True)
def _reset_buckets() -> None:
    """Reset rate limit buckets before each test."""
    reset_buckets()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def trace_id() -> str:
    """Create a trace owned by USER_OWNER."""
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=USER_OWNER,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_RATE_1"}],
    )
    return pkg.request_id


def test_period_to_seconds() -> None:
    """Period string → seconds conversion."""
    assert _period_to_seconds("s") == 1.0
    assert _period_to_seconds("m") == 60.0
    assert _period_to_seconds("h") == 3600.0
    assert _period_to_seconds("d") == 86400.0
    assert _period_to_seconds("invalid") is None


def test_parse_org_rate_limits_basic() -> None:
    """parse_org_rate_limits parses 'org:N/period' format."""
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_a:100/m;org_b:500/h;org_c:5/s"
    try:
        result = parse_org_rate_limits()
        assert result["org_a"] == (100, 60.0)
        assert result["org_b"] == (500, 3600.0)
        assert result["org_c"] == (5, 1.0)
    finally:
        os.environ.pop("ECE_ORG_RATE_LIMITS", None)


def test_parse_org_rate_limits_empty() -> None:
    """parse_org_rate_limits returns empty dict when env unset."""
    os.environ.pop("ECE_ORG_RATE_LIMITS", None)
    assert parse_org_rate_limits() == {}


def test_parse_org_rate_limits_invalid_period() -> None:
    """Invalid period string is skipped."""
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_a:100/invalid;org_b:200/m"
    try:
        result = parse_org_rate_limits()
        assert "org_a" not in result
        assert result["org_b"] == (200, 60.0)
    finally:
        os.environ.pop("ECE_ORG_RATE_LIMITS", None)


def test_check_rate_limit_no_org() -> None:
    """No org_id → always allow."""
    allowed, code, retry = check_rate_limit(None, None)
    assert allowed is True
    assert code == "no_limit"


def test_check_rate_limit_unconfigured_org() -> None:
    """Org not in ECE_ORG_RATE_LIMITS → always allow."""
    os.environ.pop("ECE_ORG_RATE_LIMITS", None)
    allowed, code, retry = check_rate_limit(None, "org_unknown")
    assert allowed is True
    assert code == "no_limit"


def test_check_rate_limit_first_request() -> None:
    """First request to configured org → allow."""
    saved = os.environ.get("ECE_ORG_RATE_LIMITS")
    saved_uo = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_test:5/m"
    os.environ["ECE_USER_ORGS"] = "test_user:org_test"  # cut-037 R37.2 anchor
    try:
        allowed, code, retry = check_rate_limit("test_user", "org_test")
        assert allowed is True
        assert code == "ok"
        assert retry == 0.0
    finally:
        if saved is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved
        if saved_uo is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_uo


def test_check_rate_limit_exhaustion() -> None:
    """After N requests, bucket empty → 429 with retry_after."""
    saved = os.environ.get("ECE_ORG_RATE_LIMITS")
    saved_uo = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_test:3/m"
    os.environ["ECE_USER_ORGS"] = "test_user:org_test"  # cut-037 R37.2 anchor
    try:
        # 3 requests succeed
        for i in range(3):
            allowed, code, _ = check_rate_limit("test_user", "org_test")
            assert allowed is True, f"Request {i+1} should succeed"
        # 4th request fails
        allowed, code, retry = check_rate_limit("test_user", "org_test")
        assert allowed is False
        assert code == "rate_limited"
        assert retry > 0.0  # has retry-after seconds
    finally:
        if saved is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved
        if saved_uo is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_uo


def test_audit_rate_limit_429(
    client: TestClient, trace_id: str
) -> None:
    """/audit with exhausted rate limit → 429."""
    saved = os.environ.get("ECE_ORG_RATE_LIMITS")
    saved_uo = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_rl_test:2/m"
    os.environ["ECE_USER_ORGS"] = f"{USER_OWNER}:org_rl_test"  # cut-037 R37.2
    try:
        # First 2 requests succeed
        for _ in range(2):
            r = client.get(
                f"/api/v1/audit/context/{trace_id}",
                headers={
                    "X-User-Id": USER_OWNER,
                    "X-Org-Id": "org_rl_test",
                },
            )
            assert r.status_code == 200, r.text
        # 3rd request → 429
        r = client.get(
            f"/api/v1/audit/context/{trace_id}",
            headers={
                "X-User-Id": USER_OWNER,
                "X-Org-Id": "org_rl_test",
            },
        )
        assert r.status_code == 429, r.text
        body = r.json()
        assert body["detail"]["code"] == "rate_limited"
        assert "retry_after_seconds" in body["detail"]
        # Retry-After header
        assert "Retry-After" in r.headers
    finally:
        if saved is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved
        if saved_uo is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_uo
        reset_buckets()


def test_audit_rate_limit_per_org_isolation(
    client: TestClient, trace_id: str
) -> None:
    """R37.2: USER_OWNER (mapped to org_a) rotating X-Org-Id to org_b does
    NOT escape the org_a bucket.

    Pre-R37.2 premise was "different X-Org-Id values → independent buckets"
    (test sent 3 different X-Org-Id values and expected each to have its
    own quota). That premise is obsolete: X-Org-Id is now ignored for
    bucket selection (per directive "不再信裸 X-Org-Id").

    New assertion: USER_OWNER's bucket is anchored to ECE_USER_ORGS-mapped
    org (org_a). Rotating X-Org-Id to org_b can only succeed via a
    wildcard delegation token (which bypasses the multi-tenant org
    mismatch check); even then the rate-limit bucket stays org_a.
    """
    saved = os.environ.get("ECE_ORG_RATE_LIMITS")
    saved_uo = os.environ.get("ECE_USER_ORGS")
    saved_dot = os.environ.get("ECE_DELEGATION_ORG_TOKENS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_a:1/m"
    os.environ["ECE_USER_ORGS"] = f"{USER_OWNER}:org_a"
    # Wildcard token lets USER_OWNER send X-Org-Id=org_b without 403
    os.environ["ECE_DELEGATION_ORG_TOKENS"] = "wildcard:*"
    try:
        # org_a bucket exhausted after 1 request
        r = client.get(
            f"/api/v1/audit/context/{trace_id}",
            headers={
                "X-User-Id": USER_OWNER,
                "X-Org-Id": "org_a",
                "X-Delegation-Token": "wildcard",
            },
        )
        assert r.status_code == 200
        # 2nd request: rotate to org_b — bucket still org_a (mapped)
        r = client.get(
            f"/api/v1/audit/context/{trace_id}",
            headers={
                "X-User-Id": USER_OWNER,
                "X-Org-Id": "org_b",  # header rotation
                "X-Delegation-Token": "wildcard",  # bypasses org check
            },
        )
        assert r.status_code == 429, (
            f"X-Org-Id rotation must not escape org_a bucket; got {r.status_code}"
        )
    finally:
        if saved is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved
        if saved_uo is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_uo
        if saved_dot is None:
            os.environ.pop("ECE_DELEGATION_ORG_TOKENS", None)
        else:
            os.environ["ECE_DELEGATION_ORG_TOKENS"] = saved_dot
        reset_buckets()


def test_audit_rate_limit_unconfigured_org_allows_all(
    client: TestClient, trace_id: str
) -> None:
    """Org not in ECE_ORG_RATE_LIMITS → no rate limit (always allow)."""
    saved = os.environ.get("ECE_ORG_RATE_LIMITS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_a:1/m"
    try:
        # 5 requests to org_b (not in config) → all succeed
        for _ in range(5):
            r = client.get(
                f"/api/v1/audit/context/{trace_id}",
                headers={"X-User-Id": USER_OWNER, "X-Org-Id": "org_b"},
            )
            assert r.status_code == 200, r.text
    finally:
        if saved is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved


def test_debug_rate_limit_429(
    client: TestClient, trace_id: str
) -> None:
    """/debug with exhausted rate limit → 429."""
    saved_rl = os.environ.get("ECE_ORG_RATE_LIMITS")
    saved_mode = os.environ.get("ECE_DEPLOYMENT_MODE")
    saved_uo = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_ORG_RATE_LIMITS"] = "org_rl_debug:1/m"
    os.environ["ECE_DEPLOYMENT_MODE"] = "local"
    os.environ["ECE_USER_ORGS"] = f"{USER_OWNER}:org_rl_debug"  # cut-037 R37.2
    try:
        # 1st succeeds
        r = client.get(
            f"/debug/context/{trace_id}",
            headers={"X-User-Id": USER_OWNER, "X-Org-Id": "org_rl_debug"},
        )
        assert r.status_code == 200, r.text
        # 2nd → 429
        r = client.get(
            f"/debug/context/{trace_id}",
            headers={"X-User-Id": USER_OWNER, "X-Org-Id": "org_rl_debug"},
        )
        assert r.status_code == 429, r.text
    finally:
        if saved_rl is None:
            os.environ.pop("ECE_ORG_RATE_LIMITS", None)
        else:
            os.environ["ECE_ORG_RATE_LIMITS"] = saved_rl
        if saved_mode is None:
            os.environ.pop("ECE_DEPLOYMENT_MODE", None)
        else:
            os.environ["ECE_DEPLOYMENT_MODE"] = saved_mode
        if saved_uo is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_uo
        reset_buckets()
