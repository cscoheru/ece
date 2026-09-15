"""Multi-user PermissionScope delegation (v0.1 deployment cut-018b).

Allow manager / team-lead / shared-service to view another user's trace
via `X-Delegation-Token` header (instead of impersonating via X-User-Id).

Env format (v0.1 simple):
    ECE_DELEGATION_TOKENS = "secret_token_1:user_ref_1,user_ref_2;secret_token_2:user_ref_3"

Each `token:user1,user2` entry grants the bearer access to user1 AND user2
traces. v0.1 supports 1:1 or 1:N mapping; v0.2 may add per-resource scoping.

For v0.1 simplicity: bearer of valid token can read all listed users' traces
(no row-level filtering yet; cut-019+ for fine-grained scope).
"""
from __future__ import annotations

import os


def parse_delegation_tokens() -> dict[str, list[str]]:
    """Parse ECE_DELEGATION_TOKENS env into {token: [user_refs]} dict.

    Format: "token1:user1,user2;token2:user3"
    Whitespace tolerant. Skips malformed entries (no colon).
    """
    raw = os.environ.get("ECE_DELEGATION_TOKENS", "")
    result: dict[str, list[str]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        token, user_refs_str = entry.split(":", 1)
        token = token.strip()
        if not token:
            continue
        user_refs = [u.strip() for u in user_refs_str.split(",") if u.strip()]
        if user_refs:
            result[token] = user_refs
    return result


def resolve_user_refs(
    x_user_id: str | None,
    x_delegation_token: str | None,
) -> list[str]:
    """Resolve the user_refs this request can access.

    Returns list of user_refs (possibly empty). Order:
    1. If X-Delegation-Token is set and valid, return its associated user_refs
    2. If X-User-Id is set, return [X-User-Id]
    3. Empty (caller should 400)

    For v0.1: union of (1) and (2) when both are present (e.g., manager +
    self check). For simplicity in cut-018b, prefer delegation token
    when present (admin/manager use case), else fall back to X-User-Id.
    """
    user_refs: list[str] = []

    # Delegation token path (admin/manager/shared service)
    if x_delegation_token:
        tokens = parse_delegation_tokens()
        if x_delegation_token in tokens:
            user_refs.extend(tokens[x_delegation_token])

    # Self access path (always include the bearer)
    if x_user_id and x_user_id not in user_refs:
        user_refs.append(x_user_id)

    return user_refs


def user_can_access(
    x_user_id: str | None,
    x_delegation_token: str | None,
    trace_user_ref: str,
) -> bool:
    """True if request can access a trace with given trace_user_ref.

    Per ADR-004: only owner can view. With delegation, token-bearer can
    view if trace_user_ref is in their allowed list.
    """
    if x_user_id == trace_user_ref:
        return True
    allowed = resolve_user_refs(x_user_id, x_delegation_token)
    return trace_user_ref in allowed
