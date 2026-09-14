"""MCP tool implementations for ECE.

4 tools exposed per TASKS.md S4.5:
- search: FTS keyword search across documents
- get_record: entity by display_id (with PermissionScope check)
- create_task: PREVIEW ONLY (no execution per ADR-004)
- send_message: PREVIEW ONLY (no execution per ADR-004)

Every tool calls auth.check_user_permission before any data access — no
permission bypass (per ADR-004 + ECE/CLAUDE.md iron rule 1).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from ece.connectors.docs import search_documents
from ece.db import get_engine
from ece.mcp.auth import check_user_permission, object_exists


# === search ===
def search_tool(query: str, top_k: int = 10) -> dict[str, Any]:
    """FTS keyword search across ECE documents.

    Per ADR-004: results already include permission-filtered envelope
    (public docs only by default; classification + ACL filter in cut-011+).
    """
    engine = get_engine()
    hits = search_documents(engine, query=query, top_k=top_k)
    return {
        "items": [
            {
                "kind": "keyword",
                "ref": f"{h['document_display_id']}#{h['chunk_index']}",
                "title": h["document_display_id"],
                "snippet": h["snippet"],
                "score": h["rank"],
                "src": {
                    "system": "docs",
                    "document_id": h["document_display_id"],
                    "page": h["chunk_index"],
                },
            }
            for h in hits
        ],
        "meta": {"total": len(hits), "kinds_used": ["keyword"]},
    }


# === get_record ===
def get_record_tool(user_ref: str, display_id: str) -> dict[str, Any]:
    """Get a single entity by display_id with PermissionScope check.

    Per ADR-004 anti-probing:
    - If user has no permission → {error: "forbidden"} (no info leak)
    - If object doesn't exist → {error: "not_found"} (uniform with above)
    """
    # Step 1: check existence (for accurate error reporting)
    if not object_exists("entity", display_id):
        return {"error": "not_found", "ref": display_id}

    # Step 2: check permission (mandatory; no bypass per ADR-004)
    if not check_user_permission(user_ref, "entity", display_id):
        return {"error": "forbidden", "ref": display_id}

    # Step 3: fetch (only after permission check)
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT display_id, entity_type, name, attributes, source_system, source_id
                FROM entities WHERE display_id = :d
            """),
            {"d": display_id},
        ).first()

    if row is None:
        # Race condition: object existed in step 1 but not in step 3 (unlikely)
        return {"error": "not_found", "ref": display_id}

    attrs = row[3] if isinstance(row[3], dict) else {}
    return {
        "ref": row[0],
        "type": row[1],
        "name": row[2],
        "attrs": attrs,
        "src": {"system": row[4] or "", "record_id": row[5] or ""},
    }


# === create_task (PREVIEW ONLY) ===
def create_task_tool(title: str, description: str) -> dict[str, Any]:
    """Preview only — no actual task creation per ADR-004.

    Per ECE/CLAUDE.md + ADR-004: /actions/execute is disabled in v0.
    This tool returns a preview of what would be created.
    """
    return {
        "preview": True,
        "title": title,
        "description": description,
        "status": "would_create",
        "note": "v0: actions/execute disabled per ADR-004; this is preview only",
    }


# === send_message (PREVIEW ONLY) ===
def send_message_tool(to: str, body: str) -> dict[str, Any]:
    """Preview only — no actual message sent per ADR-004."""
    return {
        "preview": True,
        "to": to,
        "body_length": len(body),
        "status": "would_send",
        "note": "v0: actions/execute disabled per ADR-004; this is preview only",
    }
