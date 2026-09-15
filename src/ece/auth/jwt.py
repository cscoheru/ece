"""JWT bearer token authentication (cut-027 + cut-032).

cut-027: HS256 symmetric JWT (default). ECE_JWT_SECRET shared with IdP.
cut-032: RS256 asymmetric JWT. ECE_JWT_PUBLIC_KEY (PEM) for verification;
         IdP keeps private key. Supports multi-service deployment.

Env:
    ECE_JWT_SECRET       # HMAC secret (HS256 only); cut-027
    ECE_JWT_PUBLIC_KEY   # RSA public key PEM (RS256 only); cut-032
    ECE_JWT_ALGORITHM    # default HS256; set RS256 to use public key

PyJWT auto-detects: pass `secret` for HMAC algorithms (HS*), pass
`public_key` for asymmetric (RS*, ES*).

For backward compat (cut-027 deployments): if ECE_JWT_PUBLIC_KEY is
set, take precedence over ECE_JWT_SECRET when algorithm is RS*.
"""
from __future__ import annotations

import os
from typing import Any

_jwt_lib = None
try:
    import jwt as _jwt_lib  # type: ignore[attr-defined,assignment]
    _PYJWT_AVAILABLE = True
except ImportError:
    _PYJWT_AVAILABLE = False


def is_jwt_mode_enabled() -> bool:
    """True if ECE_JWT_SECRET or ECE_JWT_PUBLIC_KEY is configured."""
    return bool(
        os.environ.get("ECE_JWT_SECRET")
        or os.environ.get("ECE_JWT_PUBLIC_KEY")
    )


def _get_verification_key() -> str | None:
    """Pick verification key based on configured env + algorithm.

    Returns:
        - ECE_JWT_PUBLIC_KEY if set (RS256 mode, cut-032)
        - ECE_JWT_SECRET if set (HS256 mode, cut-027)
        - None if neither configured
    """
    public_key = os.environ.get("ECE_JWT_PUBLIC_KEY")
    if public_key:
        return public_key
    return os.environ.get("ECE_JWT_SECRET")


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    """Decode JWT and return claims dict, or None if invalid.

    Uses ECE_JWT_PUBLIC_KEY (RS256) or ECE_JWT_SECRET (HS256) per env.
    Returns None if:
    - No verification key configured (JWT mode disabled)
    - PyJWT not installed
    - Token signature invalid / expired / malformed
    """
    key = _get_verification_key()
    if not key or not _PYJWT_AVAILABLE:
        return None
    algorithm = os.environ.get("ECE_JWT_ALGORITHM", "HS256")
    try:
        claims = _jwt_lib.decode(token, key, algorithms=[algorithm])  # type: ignore[attr-defined]
        return claims
    except _jwt_lib.PyJWTError:  # type: ignore[attr-defined]
        return None


def extract_user_ref_from_jwt(authorization_header: str | None) -> str | None:
    """Extract user_ref from Authorization: Bearer <token> header.

    Returns None if header malformed, token invalid, or 'sub' claim missing.
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    claims = decode_jwt_token(token)
    if not claims:
        return None
    user_ref = claims.get("sub")
    if not isinstance(user_ref, str) or not user_ref:
        return None
    return user_ref


def resolve_caller_user_ref(
    authorization_header: str | None,
    x_user_id_header: str | None,
) -> str | None:
    """Resolve user_ref from Authorization header (preferred) or X-User-Id fallback.

    Order:
    1. Authorization: Bearer <jwt> → decode + extract 'sub' claim
    2. X-User-Id header (legacy / cut-027 back-compat)

    Returns None if neither yields a valid user_ref.
    Empty strings are treated as None.
    """
    if is_jwt_mode_enabled():
        user_ref = extract_user_ref_from_jwt(authorization_header)
        if user_ref:
            return user_ref
    # Fall back to X-User-Id (legacy); empty string → None
    if x_user_id_header:
        return x_user_id_header
    return None
