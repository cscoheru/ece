"""JWT bearer token authentication (cut-027 — v0.2 hardening).

Replaces X-User-Id header with standard Authorization: Bearer <jwt>
header. JWT contains 'sub' claim with user_ref. Decoded server-side
using HMAC-SHA256 (HS256) symmetric secret.

Env:
    ECE_JWT_SECRET       # HMAC-SHA256 secret (required for JWT validation)
    ECE_JWT_ALGORITHM    # default HS256

Back-compat: when ECE_JWT_SECRET is unset, falls back to X-User-Id
header (deprecated, cut-027). When both are present, JWT takes
precedence.

Claims:
    sub: user_ref (subject)
    exp: expiration timestamp (unix seconds)
    iat: issued-at timestamp (unix seconds)

Use case: SSO-friendly authentication. Clients obtain JWT from their
identity provider (e.g. company SSO), pass via Authorization header.
ECE validates signature and extracts user_ref from 'sub' claim.

For v0.2: symmetric (HS256). v0.3+ may add RS256 (asymmetric) for
multi-service deployment where ECE doesn't share secret with IdP.
"""
from __future__ import annotations

import os
from typing import Any

_jwt_lib = None
try:
    import jwt as _jwt_lib  # type: ignore[assignment]
    _PYJWT_AVAILABLE = True
except ImportError:
    _PYJWT_AVAILABLE = False


def is_jwt_mode_enabled() -> bool:
    """True if ECE_JWT_SECRET is configured.

When False, X-User-Id header is used (v0.1 back-compat).
"""
    return bool(os.environ.get("ECE_JWT_SECRET"))


def decode_jwt_token(token: str) -> dict[str, Any] | None:
    """Decode JWT and return claims dict, or None if invalid.

    Uses ECE_JWT_SECRET (HMAC) + ECE_JWT_ALGORITHM (default HS256).

    Returns None if:
    - ECE_JWT_SECRET not configured (JWT mode disabled)
    - PyJWT not installed (cut-027 should add it)
    - Token signature invalid / expired / malformed
    """
    secret = os.environ.get("ECE_JWT_SECRET")
    if not secret or not _PYJWT_AVAILABLE:
        return None
    algorithm = os.environ.get("ECE_JWT_ALGORITHM", "HS256")
    try:
        # decode validates signature, expiration (exp), and audience/issuer if configured
        claims = _jwt_lib.decode(token, secret, algorithms=[algorithm])  # type: ignore[attr-defined]
        return claims
    except _jwt_lib.PyJWTError:  # type: ignore[attr-defined]
        return None


def extract_user_ref_from_jwt(authorization_header: str | None) -> str | None:
    """Extract user_ref from Authorization: Bearer <token> header.

    Returns None if:
    - Header is None or malformed (not Bearer scheme)
    - Token is invalid (signature / expiry / etc.)
    - 'sub' claim missing from claims

    Returns user_ref string from 'sub' claim if valid.
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
