"""cut-036 R36.5 — P1/P2 adversarial probes → formal regression tests.

Per cut-035R2 §11.3 + scripts/cline_review_probe_2026_09.py P1+P2:
- P1: JWT mode ON + only X-User-Id → expect 401 (was 200 impersonation)
- P2: JWT mode ON + garbage Bearer + X-User-Id → expect 401

Tests both /api/v1/audit/context/{rid} and /debug/context/{rid}
endpoints (R36.3 enforces both routes).

P3/P4 (revoked-user + rate-limit org rotation) remain as in-repo probes
under scripts/cline_review_probe_2026_09.py — they verify cut-028 / cut-029
invariants and are not part of R36.5's formalize scope.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.db import get_engine
from ece.main import app

JWT_SECRET = "test_jwt_secret_for_cut_036_gate_at_least_32_bytes"  # noqa: S105


@pytest.fixture
def jwt_client_and_trace(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    """TestClient in strict JWT mode + seeded trace row for audit access."""
    # Strict default: JWT mode on + ECE_ALLOW_HEADER_AUTH unset → R36.1
    monkeypatch.setenv("ECE_JWT_SECRET", JWT_SECRET)
    monkeypatch.delenv("ECE_ALLOW_HEADER_AUTH", raising=False)
    # /debug requires local deployment mode
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
    return client, rid


def _cleanup_trace(rid: str) -> None:
    """Remove seeded trace so other tests aren't polluted."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM context_requests WHERE request_id = :r"), {"r": rid})


# ── /api/v1/audit/context/{rid} ────────────────────────────────────────────


def test_audit_p1_no_authorization_returns_401(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Probe P1 → regression: JWT mode + only X-User-Id → 401 (was 200 impersonation)."""
    client, rid = jwt_client_and_trace
    try:
        r = client.get(
            f"/api/v1/audit/context/{rid}",
            headers={"X-User-Id": "alice"},
        )
        assert r.status_code == 401, f"expected 401; got {r.status_code}: {r.text}"
        body = r.json()
        assert body["detail"]["code"] == "unauthorized"
        assert r.headers.get("www-authenticate", "").lower().startswith("bearer")
    finally:
        _cleanup_trace(rid)


def test_audit_p2_invalid_bearer_returns_401(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Probe P2 → regression: JWT mode + garbage Bearer + X-User-Id → 401."""
    client, rid = jwt_client_and_trace
    try:
        r = client.get(
            f"/api/v1/audit/context/{rid}",
            headers={
                "Authorization": "Bearer garbage.token.here",
                "X-User-Id": "alice",
            },
        )
        assert r.status_code == 401, f"expected 401; got {r.status_code}: {r.text}"
        body = r.json()
        assert body["detail"]["code"] == "unauthorized"
    finally:
        _cleanup_trace(rid)


def test_audit_p2_expired_bearer_returns_401(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Regression: valid-shape but expired Bearer → 401."""
    import time

    import jwt

    client, rid = jwt_client_and_trace
    try:
        expired_token = jwt.encode(
            {"sub": "alice", "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600},
            JWT_SECRET,
            algorithm="HS256",
        )
        r = client.get(
            f"/api/v1/audit/context/{rid}",
            headers={
                "Authorization": f"Bearer {expired_token}",
                "X-User-Id": "alice",
            },
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "unauthorized"
    finally:
        _cleanup_trace(rid)


def test_audit_valid_bearer_returns_200(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Positive control: valid Bearer in JWT mode → 200 (does not over-block)."""
    import time

    import jwt

    client, rid = jwt_client_and_trace
    try:
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
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, f"expected 200 with valid Bearer; got {r.status_code}"
    finally:
        _cleanup_trace(rid)


# ── /debug/context/{rid} (R36.3 symmetric coverage) ───────────────────────


def test_debug_p1_no_authorization_returns_401(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Probe P1 → /debug parallel: JWT mode + only X-User-Id → 401."""
    client, rid = jwt_client_and_trace
    try:
        r = client.get(
            f"/debug/context/{rid}",
            headers={"X-User-Id": "alice"},
        )
        assert r.status_code == 401, f"expected 401; got {r.status_code}: {r.text}"
        body = r.json()
        assert body["detail"]["code"] == "unauthorized"
    finally:
        _cleanup_trace(rid)


def test_debug_p2_invalid_bearer_returns_401(jwt_client_and_trace: tuple[TestClient, str]) -> None:
    """Probe P2 → /debug parallel: JWT mode + garbage Bearer → 401."""
    client, rid = jwt_client_and_trace
    try:
        r = client.get(
            f"/debug/context/{rid}",
            headers={
                "Authorization": "Bearer garbage.token.here",
                "X-User-Id": "alice",
            },
        )
        assert r.status_code == 401, f"expected 401; got {r.status_code}: {r.text}"
        body = r.json()
        assert body["detail"]["code"] == "unauthorized"
    finally:
        _cleanup_trace(rid)


# ── ECE_ALLOW_HEADER_AUTH opt-in (R36.2) ──────────────────────────────────


def test_audit_with_allow_header_auth_falls_back(jwt_client_and_trace: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """R36.2: ECE_ALLOW_HEADER_AUTH=1 → X-User-Id works as opt-in fallback."""
    client, rid = jwt_client_and_trace
    monkeypatch.setenv("ECE_ALLOW_HEADER_AUTH", "1")
    try:
        r = client.get(
            f"/api/v1/audit/context/{rid}",
            headers={"X-User-Id": "alice"},
        )
        assert r.status_code == 200, f"opt-in should allow X-User-Id; got {r.status_code}"
    finally:
        _cleanup_trace(rid)
