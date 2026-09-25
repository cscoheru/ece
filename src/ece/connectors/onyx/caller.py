"""OEI-008 — EngineCallerContext builders.

This module is the **boundary** between ECE's identity/auth code and the
ContentEnginePort. Keeping the conversion out of `port.py` means:

  - `port.py` stays free of any identity / JWT / DB imports.
  - Builders that need a DB lookup (e.g. resolving the full `Identity`
    from a `user_ref`) can import freely without polluting the Port.
  - Tests can target this module in isolation.

The two entry points used by the 4 call sites (`api/engine_status.py`,
`consulting/engine_merge.py`, `consulting/router.py:upload`,
`consulting/router.py:status`) are:

  - `caller_from_request_headers(authorization, x_user_id) -> EngineCallerContext`
      Cheap, DB-less: parses JWT (if available) or reads X-User-Id, returns
      a context with only `user_ref`/`source` populated. Suitable for the
      read-only surfaces (/library, /engine/status).

  - `caller_from_db_identity(engine, authorization, x_user_id) -> EngineCallerContext`
      Heavier: also resolves the full `Identity` (department / roles /
      is_management) via `ece.identity.parser.resolve_identity`. Used on
      the write path (`POST /consulting/documents`) so audit records
      include department + roles. Raises `EngineError("identity-required")`
      on anonymous so the caller can return 401/403 deterministically.

Anonymous endpoints (`/engine/status` without auth, `/library` GET) should
use `caller_from_request_headers` — they pass through with `source="anonymous"`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ece.auth.jwt import resolve_caller_user_ref
from ece.connectors.onyx.port import EngineCallerContext, EngineError

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine as _SAEngine


def caller_from_request_headers(
    authorization_header: str | None,
    x_user_id_header: str | None,
) -> EngineCallerContext:
    """Cheap caller resolution: header / JWT only, no DB.

    Returns `EngineCallerContext.anonymous()` when neither header nor JWT
    produces a user_ref. Read-only surfaces accept anonymous.
    """
    user_ref = resolve_caller_user_ref(authorization_header, x_user_id_header)
    if not user_ref:
        return EngineCallerContext.anonymous()
    # Decide source from which signal was the truth.
    # `resolve_caller_user_ref` prefers Authorization; we mirror that.
    if authorization_header and authorization_header.startswith("Bearer "):
        source = "jwt"
    else:
        source = "header"
    return EngineCallerContext(
        user_ref=user_ref,
        roles=(),
        department="",
        is_management=False,
        org_id=None,
        source=source,  # type: ignore[arg-type]
    )


def caller_from_db_identity(
    sql_engine: _SAEngine | None,
    authorization_header: str | None,
    x_user_id_header: str | None,
) -> EngineCallerContext:
    """Heavier caller resolution: JWT/header → DB lookup → full Identity.

    Required on the write path (`POST /consulting/documents`) so the
    audit record carries `department` + `roles` + `is_management`. Anonymous
    callers (`user_ref == None`) raise `EngineError("identity-required")`
    so the calling route can map it to a deterministic 401/403.

    If `sql_engine` is None (e.g. unit tests without a DB) we fall back
    to the header-only context — the test author is responsible for
    not silently bypassing the anonymous-forbidden rule.
    """
    base = caller_from_request_headers(authorization_header, x_user_id_header)
    if base.user_ref is None:
        raise EngineError("identity-required (upload endpoints require an authenticated caller)")
    if sql_engine is None:
        # No DB available — accept the header-only context but log a note.
        return base

    # Lazy import: the parser pulls in SQLAlchemy text + the entity table,
    # which is heavy for read-only call sites that won't need it.
    from ece.identity.parser import resolve_identity

    try:
        identity = resolve_identity(sql_engine, base.user_ref)
    except ValueError as exc:
        # `resolve_identity` raises if user_ref is empty; we already
        # checked that above, but be defensive.
        raise EngineError(
            f"identity-required (resolve_identity rejected {base.user_ref!r})"
        ) from exc
    return EngineCallerContext.from_identity(identity, source=base.source)  # type: ignore[arg-type]


__all__ = [
    "caller_from_request_headers",
    "caller_from_db_identity",
]
