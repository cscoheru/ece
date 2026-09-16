"""Sprint 13 v0.2 — JWT bearer token auth tests (cut-027 + cut-036).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: replace X-User-Id
header with standard Authorization: Bearer <jwt> header. JWT decoded
using HMAC-SHA256 symmetric secret.

Env:
    ECE_JWT_SECRET       # required for JWT validation
    ECE_JWT_ALGORITHM    # default HS256

When ECE_JWT_SECRET is unset, falls back to X-User-Id header (v0.1
back-compat). When ECE_JWT_SECRET IS set, cut-036 R36.1 mandates strict
mode by default: missing/invalid Authorization → None (caller raises
401). X-User-Id fallback only with ECE_ALLOW_HEADER_AUTH=1 opt-in (R36.2).
"""
import time

import jwt
import pytest

from ece.auth.jwt import (
    decode_jwt_token,
    extract_user_ref_from_jwt,
    is_header_auth_fallback_allowed,
    is_jwt_mode_enabled,
    resolve_caller_user_ref,
)

JWT_SECRET = "test_jwt_secret_for_cut_027_at_least_32_bytes_long"  # noqa: S105
JWT_ALGORITHM = "HS256"


def _make_token(user_ref: str, secret: str = JWT_SECRET, exp_offset: int = 3600) -> str:
    """Helper: mint a valid JWT with user_ref as 'sub'."""
    payload = {
        "sub": user_ref,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ECE_JWT_ALGORITHM", JWT_ALGORITHM)
    # cut-036 R36.2 default strict: ECE_ALLOW_HEADER_AUTH unset (Mode C)
    # Tests that exercise the opt-in path set this explicitly.
    monkeypatch.delenv("ECE_ALLOW_HEADER_AUTH", raising=False)


def test_is_jwt_mode_enabled_when_secret_set() -> None:
    """is_jwt_mode_enabled True iff ECE_JWT_SECRET set."""
    assert is_jwt_mode_enabled() is True


def test_is_jwt_mode_disabled_when_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_jwt_mode_enabled False when ECE_JWT_SECRET unset."""
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)
    assert is_jwt_mode_enabled() is False


def test_decode_jwt_token_valid() -> None:
    """Valid token returns claims dict."""
    token = _make_token("alice")
    claims = decode_jwt_token(token)
    assert claims is not None
    assert claims["sub"] == "alice"


def test_decode_jwt_token_invalid_signature() -> None:
    """Token signed with wrong secret → None."""
    token = _make_token("alice", secret="wrong_secret")
    claims = decode_jwt_token(token)
    assert claims is None


def test_decode_jwt_token_expired() -> None:
    """Expired token (exp in past) → None."""
    token = _make_token("alice", exp_offset=-10)  # already expired
    claims = decode_jwt_token(token)
    assert claims is None


def test_decode_jwt_token_malformed() -> None:
    """Malformed token → None."""
    assert decode_jwt_token("not.a.jwt") is None
    assert decode_jwt_token("garbage") is None
    assert decode_jwt_token("") is None


def test_extract_user_ref_from_authorization_header() -> None:
    """Authorization: Bearer <token> → user_ref from 'sub'."""
    token = _make_token("alice")
    header = f"Bearer {token}"
    assert extract_user_ref_from_jwt(header) == "alice"


def test_extract_user_ref_case_insensitive_bearer() -> None:
    """'bearer' (lowercase) is accepted per RFC 6750."""
    token = _make_token("alice")
    header = f"bearer {token}"
    assert extract_user_ref_from_jwt(header) == "alice"


def test_extract_user_ref_invalid_header_format() -> None:
    """Headers without Bearer scheme → None."""
    assert extract_user_ref_from_jwt(None) is None
    assert extract_user_ref_from_jwt("") is None
    assert extract_user_ref_from_jwt("alice") is None
    assert extract_user_ref_from_jwt("Basic xyz") is None


def test_extract_user_ref_missing_sub_claim() -> None:
    """Token without 'sub' claim → None."""
    payload = {"iat": int(time.time()), "exp": int(time.time()) + 3600}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert extract_user_ref_from_jwt(f"Bearer {token}") is None


def test_resolve_caller_user_ref_jwt_preferred() -> None:
    """JWT mode active: Authorization header takes precedence."""
    token = _make_token("alice_jwt")
    user_ref = resolve_caller_user_ref(
        authorization_header=f"Bearer {token}",
        x_user_id_header="alice_xuser",
    )
    assert user_ref == "alice_jwt"


def test_resolve_caller_user_ref_fallback_to_xuser(monkeypatch: pytest.MonkeyPatch) -> None:
    """JWT mode disabled: X-User-Id used as fallback."""
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)
    user_ref = resolve_caller_user_ref(
        authorization_header="Bearer invalid.jwt.here",
        x_user_id_header="alice_legacy",
    )
    assert user_ref == "alice_legacy"


def test_resolve_caller_user_ref_no_auth() -> None:
    """Neither Authorization nor X-User-Id → None."""
    assert resolve_caller_user_ref(None, None) is None
    assert resolve_caller_user_ref("", "") is None


def test_resolve_caller_user_ref_invalid_jwt_no_fallback() -> None:
    """cut-036 R36.1: JWT mode ON + invalid JWT + X-User-Id → None (no fallback).

    Closes the silent impersonation vector that existed pre-cut-036
    (b2dfeee P0-1 live-probe: X-User-Id impersonation when JWT mode is on
    but caller omits Authorization or sends garbage).
    """
    # JWT mode enabled (autouse fixture), JWT is invalid, ECE_ALLOW_HEADER_AUTH unset
    user_ref = resolve_caller_user_ref(
        authorization_header="Bearer invalid.jwt.here",
        x_user_id_header="alice_xuser",
    )
    assert user_ref is None  # was: == "alice_xuser" (pre-cut-036 bug-as-spec)


def test_resolve_caller_no_auth_header_jwt_mode_returns_none() -> None:
    """cut-036 R36.1: JWT mode ON + no Authorization header → None."""
    user_ref = resolve_caller_user_ref(
        authorization_header=None,
        x_user_id_header="alice_xuser",
    )
    assert user_ref is None


def test_resolve_caller_x_user_id_only_jwt_mode_returns_none() -> None:
    """cut-036 R36.1: JWT mode ON + empty Authorization + X-User-Id only → None."""
    user_ref = resolve_caller_user_ref(
        authorization_header="",
        x_user_id_header="alice_xuser",
    )
    assert user_ref is None


def test_resolve_caller_with_allow_header_auth_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """cut-036 R36.2: JWT mode ON + ECE_ALLOW_HEADER_AUTH=1 + X-User-Id → user_ref."""
    monkeypatch.setenv("ECE_ALLOW_HEADER_AUTH", "1")
    assert is_header_auth_fallback_allowed() is True
    user_ref = resolve_caller_user_ref(
        authorization_header="Bearer invalid.jwt.here",
        x_user_id_header="alice_xuser",
    )
    assert user_ref == "alice_xuser"


def test_resolve_caller_jwt_takes_precedence_over_opt_in_xuser(monkeypatch: pytest.MonkeyPatch) -> None:
    """cut-036 R36.2: JWT mode ON + opt-in + both present → JWT sub wins."""
    monkeypatch.setenv("ECE_ALLOW_HEADER_AUTH", "1")
    token = _make_token("alice_jwt")
    user_ref = resolve_caller_user_ref(
        authorization_header=f"Bearer {token}",
        x_user_id_header="alice_xuser",
    )
    assert user_ref == "alice_jwt"


def test_is_header_auth_fallback_default_off() -> None:
    """cut-036 R36.2: ECE_ALLOW_HEADER_AUTH unset → fallback NOT allowed (strict)."""
    # autouse fixture deletes ECE_ALLOW_HEADER_AUTH
    assert is_header_auth_fallback_allowed() is False


def test_jwt_round_trip_with_real_token() -> None:
    """End-to-end: mint token, pass via Authorization, extract user_ref."""
    token = _make_token("alice@company.com")
    header = f"Bearer {token}"
    assert extract_user_ref_from_jwt(header) == "alice@company.com"
