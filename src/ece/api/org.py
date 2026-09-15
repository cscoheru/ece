"""Multi-tenant org scoping (cut-019 — v0.2 cross-org isolation).

ECE_USER_ORGS env configures user_ref → org_id mapping. When configured,
context_requests rows record the user's org_id (via record_package) and
/audit + /debug endpoints enforce cross-org isolation: the X-Org-Id
header on the call must match both the caller's user_ref's mapped org
AND the trace's recorded org_id.

Env format: "user1:org_a;user2:org_a;user3:org_b" — semicolon-separated
entries, each mapping user_ref → org_id.

Single-tenant (v0.1 default): ECE_USER_ORGS unset → org checks skipped.
Multi-tenant (v0.2 cut-019): ECE_USER_ORGS set → org checks enforced.
Cross-org override: still requires X-Delegation-Token (manager scope).

Per CLAUDE.md §3: design follows v0.1 cut-018b delegation pattern;
no new dependency, env-driven only.
"""
from __future__ import annotations

import os


def parse_user_orgs() -> dict[str, str]:
    """Parse ECE_USER_ORGS env into {user_ref: org_id} dict.

    Format: "user1:org_a;user2:org_a;user3:org_b"
    Whitespace tolerant. Skips malformed entries (no colon or empty parts).
    """
    raw = os.environ.get("ECE_USER_ORGS", "")
    result: dict[str, str] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        user_ref, org_id = entry.split(":", 1)
        user_ref = user_ref.strip()
        org_id = org_id.strip()
        if not user_ref or not org_id:
            continue
        result[user_ref] = org_id
    return result


def get_user_org(user_ref: str | None) -> str | None:
    """Look up org_id for user_ref from ECE_USER_ORGS.

    Returns None if user_ref is None/empty, user not in config, or env
    not set.
    """
    if not user_ref:
        return None
    return parse_user_orgs().get(user_ref)


def is_multi_tenant_mode() -> bool:
    """True if ECE_USER_ORGS is configured (any entries).

    When False, /audit and /debug skip org checks (v0.1 single-tenant
    behavior). When True, X-Org-Id is required and must match the
    trace's recorded org_id.
    """
    return bool(parse_user_orgs())


def check_org_access(
    x_org_id: str | None,
    trace_org_id: str | None,
) -> tuple[bool, str]:
    """Check whether requester can access a trace given org headers.

    Returns (allowed, error_code):
    - error_code 'multi_tenant_disabled': org checks skipped (always allow)
    - error_code 'legacy_trace': legacy row with org_id=NULL (allow)
    - error_code 'org_id_required': X-Org-Id header missing
    - error_code 'org_mismatch': X-Org-Id != trace.org_id (cross-org blocked)
    - error_code 'ok': access allowed
    """
    if not is_multi_tenant_mode():
        return True, "ok"
    if trace_org_id is None:
        # Legacy row recorded before cut-019; no multi-tenant enforcement
        # for it (back-compat with v0.1 cuts recorded before this was set).
        return True, "ok"
    if not x_org_id:
        return False, "org_id_required"
    if x_org_id != trace_org_id:
        return False, "org_mismatch"
    return True, "ok"
