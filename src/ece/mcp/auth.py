"""MCP tool call permission enforcement (per ADR-004).

Every MCP tool call MUST go through check_user_permission — never bypass
the Permission Engine. This is the MCP-layer equivalent of API PermissionScope.

Per docs/ARCHITECTURE §5 + ECE/CLAUDE.md iron rule 1: "Permission Before
Intelligence" — permission filter happens BEFORE any data access.
"""
from __future__ import annotations

from sqlalchemy import text

from ece.db import get_engine
from ece.identity.parser import resolve_identity
from ece.permissions.engine import check_permission


def check_user_permission(
    user_ref: str,
    object_type: str,
    object_ref: str,
    classification: str = "public",
) -> bool:
    """Check if user_ref has access to (object_type, object_ref).

    Returns True if allowed, False if denied (or unknown user → default deny).

    Anti-probing: missing/forbidden resources both return False (uniform).
    Caller decides whether to return {error: forbidden} or {error: not_found}
    based on object existence lookup.
    """
    engine = get_engine()
    identity = resolve_identity(engine, user_ref)
    if identity.entity_id is None:
        return False  # unknown user → default deny

    # Inline ACL load (per-object_type: supports both 'entity' and 'document')
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT subject_type, subject_ref, effect
                FROM acl_entries
                WHERE object_type = :otype AND object_ref = :oref
            """),
            {"otype": object_type, "oref": object_ref},
        ).fetchall()
    acl_entries = [
        {
            "subject_type": r[0],
            "subject_ref": r[1],
            "effect": r[2],
            "valid_from": None,
            "valid_to": None,
            "source_system": "test",
        }
        for r in rows
    ]

    decision = check_permission(
        identity=identity,
        object_type=object_type,
        object_ref=object_ref,
        classification=classification,
        acl_entries=acl_entries,
    )
    return decision.allowed


def object_exists(object_type: str, object_ref: str) -> bool:
    """Check if object (entity/document) exists in DB.

    Used by tools to distinguish 'not_found' vs 'forbidden' (anti-probing).
    """
    engine = get_engine()
    with engine.connect() as conn:
        if object_type in ("entity", "document"):
            row = conn.execute(
                text("SELECT 1 FROM entities WHERE display_id = :d"),
                {"d": object_ref},
            ).first()
            return row is not None
    return False
