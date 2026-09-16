"""cut-037 R37.3 — P3/P4 adversarial probes → formal regression tests.

Per cut-036 §10.4 + scripts/cline_review_probe_2026_09.py P3+P4:
- P3a: revoked alice + per-resource token only → 200 (BUG, was short-circuiting
       cut-028 invariant; cut-037 R37.1 closes)
- P3b: revoked alice + per-resource token + X-User-Id → 200 (same root cause)
- P4:  rate-limit org_a exhausts at 3rd, caller rotates X-Org-Id to org_b →
       still 200 (BUG; bucket was bound to raw header; cut-037 R37.2 closes)

Tests:
- /api/v1/audit/context/{rid} (audit path)
- /debug/context/{rid} (debug path)
- alice (mapped to org_a via ECE_USER_ORGS) → bucket bound to org_a
- unmapped user (charlie) → falls back to 'default' bucket
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.api.quota import reset_quotas
from ece.api.rate_limit import reset_buckets
from ece.db import get_engine
from ece.main import app

JWT_SECRET = "test_jwt_secret_for_cut_037_gate_at_least_32_bytes"  # noqa: S105


# ── R37.1 P3: revoked user + per-resource token → 403 ─────────────────────


@pytest.fixture
def revoked_trace_setup(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    """revoked alice + per-resource token configured; trace row seeded."""
    monkeypatch.setenv("ECE_REVOKED_USERS", "alice")
    # cut-036 strict JWT mode (so X-User-Id not used as fallback in P3 tests
    # that omit it; tests that DO pass X-User-Id will be 401 at auth gate
    # — handled below by overriding the env in specific tests)
    monkeypatch.setenv("ECE_JWT_SECRET", JWT_SECRET)
    monkeypatch.delenv("ECE_ALLOW_HEADER_AUTH", raising=False)
    monkeypatch.setenv("ECE_DEPLOYMENT_MODE", "local")

    client = TestClient(app)
    rid = str(uuid.uuid4())
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO context_requests"
                " (request_id, user_ref, intent, root_entities, counts, status, org_id)"
                " VALUES (:r, 'alice', 'probe', '[]'::jsonb, '{}'::jsonb, 'ok', 'org_a')"
            ),
            {"r": rid},
        )
    monkeypatch.setenv("ECE_AUDIT_TOKEN_REQUEST_IDS", f"audit_tok:{rid}")
    return client, rid


def _cleanup_trace(rid: str) -> None:
    """Remove seeded trace."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM context_requests WHERE request_id = :r"),
            {"r": rid},
        )


def test_audit_p3a_revoked_user_with_resource_token_returns_403(
    revoked_trace_setup: tuple[TestClient, str],
) -> None:
    """Probe P3a → regression: revoked user + audit_tok → 403.

    Was 200 (per-resource token short-circuited cut-028 check). With
    cut-037 R37.1 the cut-028 invariant lives in request_id_can_access
    (defense-in-depth) and refuses revoked callers regardless of token.
    """
    client, rid = revoked_trace_setup
    try:
        # Valid JWT for alice (so we get past auth, not 401)
        import time

        import jwt

        token = jwt.encode(
            {
                "sub": "alice",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        r = client.get(
            f"/api/v1/audit/context/{rid}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 403, (
            f"expected 403 (revoked user bypass); got {r.status_code}: {r.text}. "
            f"Cut-028 invariant must hold even when per-resource token grants access."
        )
        body = r.json()
        assert body["detail"]["code"] == "forbidden"
    finally:
        _cleanup_trace(rid)


def test_audit_p3b_revoked_user_with_resource_token_and_xuserid_returns_403(
    revoked_trace_setup: tuple[TestClient, str],
) -> None:
    """Probe P3b → regression: revoked user + X-User-Id + tok → 403.

    Same root cause as P3a: cut-028 must apply regardless of token path.
    """
    client, rid = revoked_trace_setup
    try:
        # Disable JWT mode for this variant so X-User-Id is accepted
        import os

        os.environ.pop("ECE_JWT_SECRET", None)
        try:
            r = client.get(
                f"/api/v1/audit/context/{rid}",
                headers={
                    "X-User-Id": "alice",
                    "X-Delegation-Token": "audit_tok",
                },
            )
            assert r.status_code == 403, (
                f"expected 403 (revoked + tok + X-User-Id); got {r.status_code}: {r.text}"
            )
        finally:
            os.environ["ECE_JWT_SECRET"] = JWT_SECRET
    finally:
        _cleanup_trace(rid)


def test_debug_p3_revoked_user_with_resource_token_returns_403(
    revoked_trace_setup: tuple[TestClient, str],
) -> None:
    """Probe P3 → /debug parallel: revoked + per-resource token → 403."""
    client, rid = revoked_trace_setup
    try:
        import time

        import jwt

        token = jwt.encode(
            {
                "sub": "alice",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            },
            JWT_SECRET,
            algorithm="HS256",
        )
        r = client.get(
            f"/debug/context/{rid}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Delegation-Token": "audit_tok",
            },
        )
        assert r.status_code == 403, (
            f"expected 403 (revoked + per-resource on /debug); got {r.status_code}: {r.text}"
        )
    finally:
        _cleanup_trace(rid)


# ── R37.2 P4: rate-limit bucket bound to authenticated identity ────────────


@pytest.fixture
def alice_mapped_to_org_a(monkeypatch: pytest.MonkeyPatch):
    """alice → org_a (via ECE_USER_ORGS); alice has wildcard org-delegation
    token so it can rotate X-Org-Id without tripping the multi-tenant
    org check (which would otherwise short-circuit before rate-limit).

    Setup:
    - ECE_USER_ORGS="alice:org_a;bob:org_b"
    - ECE_DELEGATION_ORG_TOKENS="alice_xorg:*"  # wildcard cross-org access
    - ECE_ORG_RATE_LIMITS="org_a:2/m"
    - Trace: org_id='org_a', user_ref='alice'
    - alice sends requests with X-Delegation-Token='alice_xorg' (wildcard
      allows rotating X-Org-Id without org_mismatch 403)
    """
    monkeypatch.setenv("ECE_USER_ORGS", "alice:org_a;bob:org_b")
    monkeypatch.setenv("ECE_DELEGATION_ORG_TOKENS", "alice_xorg:*")
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", "org_a:2/m")
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)  # legacy X-User-Id
    reset_buckets()
    reset_quotas()

    rid = str(uuid.uuid4())
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO context_requests"
                " (request_id, user_ref, intent, root_entities, counts, status, org_id)"
                " VALUES (:r, 'alice', 'probe', '[]'::jsonb, '{}'::jsonb, 'ok', 'org_a')"
            ),
            {"r": rid},
        )
    yield rid

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM context_requests WHERE request_id = :r"),
            {"r": rid},
        )


def _hit_audit_with_token(
    client: TestClient, rid: str, user: str, x_org_id: str | None = None,
) -> int:
    """Send one GET /audit/context/{rid} using wildcard delegation token.

    Token = 'alice_xorg' (wildcard '*' in ECE_DELEGATION_ORG_TOKENS)
    bypasses multi-tenant org check so we can reach rate-limit gate.
    """
    headers: dict[str, str] = {
        "X-User-Id": user,
        "X-Delegation-Token": "alice_xorg",
    }
    if x_org_id:
        headers["X-Org-Id"] = x_org_id
    r = client.get(
        f"/api/v1/audit/context/{rid}",
        headers=headers,
    )
    return r.status_code


def _hit_audit(
    client: TestClient, rid: str, user: str, x_org_id: str | None = None,
) -> int:
    """Send one GET /audit/context/{rid} request; return status code."""
    headers: dict[str, str] = {"X-User-Id": user}
    if x_org_id:
        headers["X-Org-Id"] = x_org_id
    r = client.get(
        f"/api/v1/audit/context/{rid}",
        headers=headers,
    )
    return r.status_code


def test_rate_limit_p4_alice_org_a_exhausted_returns_429(
    alice_mapped_to_org_a: str,
) -> None:
    """Probe P4 → regression: alice (mapped to org_a) 3rd request → 429.

    Bucket = org_a (from ECE_USER_ORGS), NOT from X-Org-Id. With cut-037
    R37.2 fix, alice's bucket is anchored to mapped org even when X-Org-Id
    header disagrees.
    """
    rid = alice_mapped_to_org_a
    client = TestClient(app)
    # org_a bucket limit = 2; first two requests consume it.
    assert _hit_audit_with_token(client, rid, "alice", "org_a") == 200
    assert _hit_audit_with_token(client, rid, "alice", "org_a") == 200
    r3 = _hit_audit_with_token(client, rid, "alice", "org_a")
    assert r3 == 429, f"expected 429 (bucket exhausted); got {r3}"


def test_rate_limit_p4_alice_rotates_header_to_org_b_still_429(
    alice_mapped_to_org_a: str,
) -> None:
    """Probe P4 → regression: alice rotates X-Org-Id to org_b → still 429.

    Closes P4 bucket rotation evasion (cut-037 R37.2). With wildcard
    delegation token bypassing the org check, alice's X-Org-Id rotation
    can no longer escape her rate-limit bucket.
    """
    rid = alice_mapped_to_org_a
    client = TestClient(app)
    # Exhaust org_a bucket (alice's mapped org)
    assert _hit_audit_with_token(client, rid, "alice", "org_a") == 200
    assert _hit_audit_with_token(client, rid, "alice", "org_a") == 200
    # Caller rotates X-Org-Id to org_b hoping to escape the bucket.
    r = _hit_audit_with_token(client, rid, "alice", "org_b")
    assert r == 429, (
        f"bucket rotation must fail; got {r}. "
        f"X-Org-Id header rotation bypasses rate limit — R37.2 not enforced."
    )


def test_rate_limit_unmapped_user_uses_default_bucket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R37.2: user not in ECE_USER_ORGS → 'default' bucket (regardless of X-Org-Id).

    With X-Org-Id completely ignored, the only way for an unmapped user
    to land on a configured bucket is the 'default' catch-all (which the
    operator may configure via ECE_ORG_RATE_LIMITS=default:N/m).
    """
    # Single-tenant: ECE_USER_ORGS unset → no per-user mapping
    monkeypatch.delenv("ECE_USER_ORGS", raising=False)
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", "default:2/m")
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)
    reset_buckets()
    reset_quotas()

    # Seed a trace owned by charlie (unmapped user)
    rid = str(uuid.uuid4())
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO context_requests"
                " (request_id, user_ref, intent, root_entities, counts, status, org_id)"
                " VALUES (:r, 'charlie', 'probe', '[]'::jsonb, '{}'::jsonb, 'ok', 'default')"
            ),
            {"r": rid},
        )

    try:
        client = TestClient(app)
        # unmapped user (charlie) — no ECE_USER_ORGS entry; X-Org-Id rotated
        # between requests. Bucket must stay 'default' for all of them.
        assert _hit_audit(client, rid, "charlie", "org_a") == 200  # bucket consumes
        assert _hit_audit(client, rid, "charlie", "org_b") == 200  # same bucket
        r = _hit_audit(client, rid, "charlie", "org_c")  # same bucket, exhausted
        assert r == 429, (
            f"unmapped user rotating X-Org-Id should stay on 'default' bucket; "
            f"got {r}. X-Org-Id rotation must not change bucket."
        )
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM context_requests WHERE request_id = :r"),
                {"r": rid},
            )
