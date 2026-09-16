"""JWT bearer token authentication (cut-027 + cut-032 + cut-036).

cut-027: HS256 symmetric JWT (default). ECE_JWT_SECRET shared with IdP.
cut-032: RS256 asymmetric JWT. ECE_JWT_PUBLIC_KEY (PEM) for verification;
         IdP keeps private key. Supports multi-service deployment.
cut-036: JWT mode is now STRICT by default — missing or invalid
         Authorization → None (caller raises 401). X-User-Id fallback only
         with ECE_ALLOW_HEADER_AUTH=1 explicit opt-in. Closes the silent
         fallback that let X-User-Id impersonate any user when JWT mode
         was enabled (b2dfeee P0-1 live-probe: 200 impersonation).

Env:
    ECE_JWT_SECRET       # HMAC secret (HS256 only); cut-027
    ECE_JWT_PUBLIC_KEY   # RSA public key PEM (RS256 only); cut-032
    ECE_JWT_ALGORITHM    # default HS256; set RS256 to use public key
    ECE_ALLOW_HEADER_AUTH # cut-036 R36.2 — "1" enables X-User-Id fallback
                         # when JWT mode is on. Default off (strict 401).

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


def is_header_auth_fallback_allowed() -> bool:
    """cut-036 R36.2: True iff ECE_ALLOW_HEADER_AUTH="1" (explicit opt-in).

    Allows legacy X-User-Id fallback when JWT mode is enabled. STRICT default
    is OFF (returns False), so any caller that did not opt in gets 401 on
    missing/invalid Authorization.
    """
    return os.environ.get("ECE_ALLOW_HEADER_AUTH") == "1"


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
    """Resolve user_ref per cut-036 R36.1+R36.2.

    Mode A — JWT disabled (no ECE_JWT_SECRET / ECE_JWT_PUBLIC_KEY):
        return X-User-Id (legacy v0.1 path).

    Mode B — JWT enabled + ECE_ALLOW_HEADER_AUTH=1 opt-in:
        Authorization Bearer → JWT sub; missing/invalid → fall back to X-User-Id
        (allows opt-in for legacy clients; security warning in API.md).

    Mode C — JWT enabled + ECE_ALLOW_HEADER_AUTH unset (default, R36.1 strict):
        Authorization Bearer → JWT sub; missing/invalid/empty → None
        (caller must raise 401; closes b2dfeee P0-1 impersonation vector).

    Returns None if no valid user_ref can be resolved. Empty strings are
    treated as None throughout.
    """
    # Mode A — JWT mode disabled: legacy X-User-Id passthrough
    if not is_jwt_mode_enabled():
        return x_user_id_header or None

    # Mode B + C: JWT mode on — Authorization header is the primary signal
    user_ref = extract_user_ref_from_jwt(authorization_header)
    if user_ref:
        return user_ref

    # Mode B — explicit opt-in allows X-User-Id fallback (NOT recommended)
    if is_header_auth_fallback_allowed():
        return x_user_id_header or None

    # Mode C — R36.1 strict default: missing/invalid Authorization → None
    return None
