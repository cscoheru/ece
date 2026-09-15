"""Sprint 18 v0.2 — RS256 asymmetric JWT tests (cut-032).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: support RS256
asymmetric JWT (IdP keeps private key; ECE verifies with public key).
Useful for multi-service deployment where ECE doesn't share secret
with identity provider.

Env:
    ECE_JWT_PUBLIC_KEY  # RSA public key PEM (RS256 mode)
    ECE_JWT_ALGORITHM   # set RS256 to use public key

When ECE_JWT_PUBLIC_KEY is set, takes precedence over ECE_JWT_SECRET.
"""
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ece.auth.jwt import (
    decode_jwt_token,
    extract_user_ref_from_jwt,
    is_jwt_mode_enabled,
    resolve_caller_user_ref,
)


@pytest.fixture(scope="module")
def rsa_keys() -> tuple[str, str]:
    """Generate RSA keypair (public + private PEM)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return public_pem, private_pem


def _make_rs256_token(user_ref: str, private_pem: str) -> str:
    payload = {
        "sub": user_ref,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, private_pem, algorithm="RS256")


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch, rsa_keys: tuple[str, str]) -> None:
    public_pem, _ = rsa_keys
    monkeypatch.setenv("ECE_JWT_PUBLIC_KEY", public_pem)
    monkeypatch.setenv("ECE_JWT_ALGORITHM", "RS256")
    # Ensure ECE_JWT_SECRET is NOT set so public key is used
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)


def test_is_jwt_mode_enabled_when_public_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_jwt_mode_enabled True if ECE_JWT_PUBLIC_KEY set."""
    assert is_jwt_mode_enabled() is True


def test_is_jwt_mode_enabled_when_only_secret_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_jwt_mode_enabled True if ECE_JWT_SECRET set (cut-027 back-compat)."""
    monkeypatch.delenv("ECE_JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("ECE_JWT_SECRET", "any_secret_at_least_32_bytes_long_xxxxx")  # noqa: S105
    assert is_jwt_mode_enabled() is True


def test_decode_rs256_valid(rsa_keys: tuple[str, str]) -> None:
    """Valid RS256 token with matching public key returns claims."""
    _, private_pem = rsa_keys
    token = _make_rs256_token("alice", private_pem)
    claims = decode_jwt_token(token)
    assert claims is not None
    assert claims["sub"] == "alice"


def test_decode_rs256_wrong_public_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RS256 token signed with different key → None."""
    # Generate a different RSA key
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public_pem = (
        other_private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    # Update env to use other_public_pem; then sign with a third key (mismatch)
    monkeypatch.setenv("ECE_JWT_PUBLIC_KEY", other_public_pem)
    third_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    third_private_pem = third_private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    token_signed_with_third = _make_rs256_token("alice", third_private_pem)
    claims = decode_jwt_token(token_signed_with_third)
    assert claims is None


def test_decode_rs256_expired(rsa_keys: tuple[str, str]) -> None:
    """Expired RS256 token → None."""
    _, private_pem = rsa_keys
    payload = {
        "sub": "alice",
        "iat": int(time.time()) - 100,
        "exp": int(time.time()) - 10,  # already expired
    }
    token = jwt.encode(payload, private_pem, algorithm="RS256")
    claims = decode_jwt_token(token)
    assert claims is None


def test_extract_user_ref_rs256(rsa_keys: tuple[str, str]) -> None:
    """Extract user_ref from valid RS256 token via Authorization header."""
    _, private_pem = rsa_keys
    token = _make_rs256_token("alice@company.com", private_pem)
    header = f"Bearer {token}"
    assert extract_user_ref_from_jwt(header) == "alice@company.com"


def test_resolve_caller_user_ref_rs256_preferred(rsa_keys: tuple[str, str]) -> None:
    """RS256 mode active: Authorization JWT takes precedence."""
    _, private_pem = rsa_keys
    token = _make_rs256_token("alice_jwt", private_pem)
    user_ref = resolve_caller_user_ref(
        authorization_header=f"Bearer {token}",
        x_user_id_header="alice_xuser",
    )
    assert user_ref == "alice_jwt"


def test_jwt_secret_takes_precedence_over_public_key_when_both_set(
    monkeypatch: pytest.MonkeyPatch, rsa_keys: tuple[str, str]
) -> None:
    """When both ECE_JWT_PUBLIC_KEY and ECE_JWT_SECRET are set, public key wins (cut-032 design)."""
    # Public key is set in autouse fixture
    # Set secret too
    secret = "secret_at_least_32_bytes_long_for_test"  # noqa: S105
    monkeypatch.setenv("ECE_JWT_SECRET", secret)
    # Public key takes precedence per _get_verification_key()
    public_pem, _ = rsa_keys
    from ece.auth.jwt import _get_verification_key

    assert _get_verification_key() == public_pem


def test_no_jwt_mode_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without any JWT env, mode disabled."""
    monkeypatch.delenv("ECE_JWT_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("ECE_JWT_SECRET", raising=False)
    monkeypatch.delenv("ECE_JWT_ALGORITHM", raising=False)
    assert is_jwt_mode_enabled() is False
