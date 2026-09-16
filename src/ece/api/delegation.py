"""Multi-user PermissionScope delegation (v0.1 deployment cut-018b + cut-021 + cut-022 + cut-024).

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

Env format (v0.2 cut-022, per-RESOURCE):
    ECE_AUDIT_TOKEN_REQUEST_IDS = "audit_token:req_abc,req_xyz;..."

Each `token:req_abc,req_xyz` entry grants the bearer access to SPECIFIC
request_ids, regardless of ownership or org. Used by external auditors
given specific case IDs to investigate.

Env format (v0.2 cut-024, REVOCATION):
    ECE_REVOKED_TOKENS = "compromised_tok_1,leaked_tok_2"

Comma-separated list of tokens to revoke. Revoked tokens are treated
as no token — they grant no access (per-user, per-org, per-resource).
Owner access via X-User-Id still works. Used to invalidate compromised
tokens without env restart.
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


def parse_revoked_tokens() -> set[str]:
    """Parse ECE_REVOKED_TOKENS env into set of revoked token strings.

    Format: "compromised_tok_1,leaked_tok_2"
    Whitespace tolerant. Empty entries skipped.
    """
    raw = os.environ.get("ECE_REVOKED_TOKENS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def is_token_revoked(token: str | None) -> bool:
    """True if token is in ECE_REVOKED_TOKENS revocation list (cut-024).

    Revoked tokens are treated as no token at all — they grant NO access
    via per-user / per-org / per-resource paths. Owner access via
    X-User-Id still works (revocation only disables delegation grants).
    """
    if not token:
        return False
    return token in parse_revoked_tokens()


def parse_revoked_users() -> set[str]:
    """Parse ECE_REVOKED_USERS env into set of revoked user_refs (cut-028).

    Format: "fired_user,banned_user,terminated_user"
    Whitespace tolerant. Empty entries skipped.

    Different from ECE_REVOKED_TOKENS (cut-024): revoked user is denied
    ALL access, including owner access to their own traces. Used when
    firing an employee or terminating an account.
    """
    raw = os.environ.get("ECE_REVOKED_USERS", "")
    return {u.strip() for u in raw.split(",") if u.strip()}


def is_user_revoked(user_ref: str | None) -> bool:
    """True if user_ref is in ECE_REVOKED_USERS revocation list (cut-028).

    Revoked users are denied ALL access — even owner check on their own
    traces. This is intentionally stronger than cut-024 (token revocation)
    which preserves owner access.

    For graceful deactivation scenarios (employee leaving), use
    ECE_REVOKED_USERS. For token compromise, use ECE_REVOKED_TOKENS.
    """
    if not user_ref:
        return False
    return user_ref in parse_revoked_users()


def parse_request_id_delegation_tokens() -> dict[str, list[str]]:
    """Parse ECE_AUDIT_TOKEN_REQUEST_IDS env into {token: [request_ids]} dict.

    Format: "token1:req_abc,req_xyz;token2:req_def"
    Whitespace tolerant. Skips malformed entries (no colon).

    Per-resource scope (cut-022): token grants access to SPECIFIC
    request_ids only, regardless of who owns them or what org they're in.
    Used by external auditors given specific case IDs to investigate.
    """
    raw = os.environ.get("ECE_AUDIT_TOKEN_REQUEST_IDS", "")
    result: dict[str, list[str]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        token, ids_str = entry.split(":", 1)
        token = token.strip()
        if not token:
            continue
        ids = [i.strip() for i in ids_str.split(",") if i.strip()]
        if ids:
            result[token] = ids
    return result


def request_id_can_access(
    x_delegation_token: str | None,
    request_id: str | None,
    caller_user_ref: str | None = None,
) -> bool:
    """True if X-Delegation-Token grants access to this specific request_id.

    Per-resource scope (cut-022): independent of owner / per-user / per-org
    checks. Token bearer can access the listed request_ids regardless of
    ownership or org. Returns False if token absent, token has no
    per-resource entries, token is revoked (cut-024), or caller_user_ref
    is revoked (cut-037 R37.1).

    cut-037 R37.1: caller_user_ref in ECE_REVOKED_USERS → denied even
    with valid per-resource token. Closes P3a bypass (revoked user +
    per-resource token was returning 200 because this function short-
    circuited the `user_can_access` cut-028 check). Defense-in-depth: the
    invariant lives here, not at caller sites.
    """
    # cut-037 R37.1: revoked caller → deny before token check
    if is_user_revoked(caller_user_ref):
        return False
    if is_token_revoked(x_delegation_token):
        return False
    if not x_delegation_token or not request_id:
        return False
    rq_tokens = parse_request_id_delegation_tokens()
    if x_delegation_token not in rq_tokens:
        return False
    return request_id in rq_tokens[x_delegation_token]


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
    cut-024: revoked tokens are treated as no token (skipped entirely).
    """
    # cut-024: revoked tokens are treated as no token
    if is_token_revoked(x_delegation_token):
        x_delegation_token = None

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
    cut-024: revoked tokens grant nothing.
    cut-028: revoked users (ECE_REVOKED_USERS) are denied ALL access,
    including owner check on their own traces.
    """
    # cut-028: revoked user → no access at all (owner + delegation both blocked)
    if is_user_revoked(x_user_id) or is_user_revoked(trace_user_ref):
        return False
    if x_user_id == trace_user_ref:
        return True
    allowed = resolve_user_refs(x_user_id, x_delegation_token)
    return trace_user_ref in allowed
