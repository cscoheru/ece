"""Multi-user PermissionScope delegation (v0.1 deployment cut-018b + cut-021).

Allow manager / team-lead / shared-service to view another user's trace
via `X-Delegation-Token` header (instead of impersonating via X-User-Id).

Env format (v0.1, per-USER):
    ECE_DELEGATION_TOKENS = "secret_token_1:user_ref_1,user_ref_2;..."

Each `token:user1,user2` entry grants the bearer access to user1 AND user2
traces. v0.1 supports 1:1 or 1:N mapping.

Env format (v0.2 cut-021, per-ORG):
    ECE_DELEGATION_ORG_TOKENS = "manager_token:org_a,org_b;admin:*"

Each `token:org_a,org_b` entry grants the bearer access to ALL users whose
user_ref maps to those orgs (per ECE_USER_ORGS env). Enables cross-org read
for managers / auditors without per-user token lists. Wildcard "*" grants
cross-ALL-orgs access (audit role).
"""
from __future__ import annotations

import os

from ece.api.org import parse_user_orgs


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


def parse_org_delegation_tokens() -> dict[str, list[str]]:
    """Parse ECE_DELEGATION_ORG_TOKENS env into {token: [org_ids]} dict.

    Format: "token1:org_a,org_b;token2:org_c"
    Whitespace tolerant. Skips malformed entries (no colon).
    Wildcard "*" in org list grants cross-ALL-orgs access (audit role).

    Used by cut-021 cross-org delegation: token bearer gains read
    access to every user_ref whose org_id (per ECE_USER_ORGS) is in
    the token's org list.
    """
    raw = os.environ.get("ECE_DELEGATION_ORG_TOKENS", "")
    result: dict[str, list[str]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        token, orgs_str = entry.split(":", 1)
        token = token.strip()
        if not token:
            continue
        orgs = [o.strip() for o in orgs_str.split(",") if o.strip()]
        if orgs:
            result[token] = orgs
    return result


def _user_refs_in_orgs(org_ids: list[str]) -> list[str]:
    """Return all user_refs whose ECE_USER_ORGS mapping is in org_ids.

    If org_ids contains "*", returns all mapped user_refs (wildcard
    cross-org access, audit role).
    """
    user_orgs = parse_user_orgs()
    if "*" in org_ids:
        return list(user_orgs.keys())
    return [u for u, org in user_orgs.items() if org in org_ids]


def resolve_user_refs(
    x_user_id: str | None,
    x_delegation_token: str | None,
) -> list[str]:
    """Resolve the user_refs this request can access.

    Returns list of user_refs (possibly empty). Order:
    1. If X-Delegation-Token matches ECE_DELEGATION_TOKENS, add its user_refs
    2. If X-Delegation-Token matches ECE_DELEGATION_ORG_TOKENS, add all
       user_refs mapped to its orgs (per ECE_USER_ORGS) — cut-021
    3. If X-User-Id is set, add it (self access)
    4. Empty (caller should 400)

    For v0.1: union of (1) and (3). For v0.2 cut-021: union of (1), (2), (3).
    """
    user_refs: list[str] = []

    # Per-USER delegation tokens (cut-018b)
    if x_delegation_token:
        tokens = parse_delegation_tokens()
        if x_delegation_token in tokens:
            user_refs.extend(tokens[x_delegation_token])

    # Per-ORG delegation tokens (cut-021)
    if x_delegation_token:
        org_tokens = parse_org_delegation_tokens()
        if x_delegation_token in org_tokens:
            for user_ref in _user_refs_in_orgs(org_tokens[x_delegation_token]):
                if user_ref not in user_refs:
                    user_refs.append(user_ref)

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
    view if trace_user_ref is in their allowed list (per-user or per-org).
    """
    if x_user_id == trace_user_ref:
        return True
    allowed = resolve_user_refs(x_user_id, x_delegation_token)
    return trace_user_ref in allowed
