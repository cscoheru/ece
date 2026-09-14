"""S3.2 step 7 — Structured data retrieval (per-spec.kind SQL).

Per ARCHITECTURE §3 step 7:
  Retrieve structured data: SQL query → row-level permissions

Cut-011: per-kind handlers for 'historical_purchase' and 'approval_history'.
v0 demo lacks purchase_record/approval entities, so returns [] (correct
behavior — no rows for kind). v1 may add more kinds (committees, contracts).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.context.spec import ContextSpec
from ece.identity.parser import Identity
from ece.permissions.engine import check_permission


def get_structured_data(
    engine: Engine,
    spec: ContextSpec,
    identity: Identity,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Per-spec.kind SQL queries for structured_data.

    Handlers:
    - 'historical_purchase' → entities WHERE entity_type='purchase_record'
    - 'approval_history' → entities WHERE entity_type='approval'

    Returns list of {kind, ref, attrs, src} rows. Empty list for unseeded
    kinds (v0 demo).
    """
    if not spec.requires.structured_data:
        return []

    items: list[dict[str, Any]] = []

    for kind in spec.requires.structured_data:
        handler = _KIND_HANDLERS.get(kind)
        if handler is None:
            # Unknown kind — skip (not raise; v0 may have kinds in spec before
            # handlers are written; fail-soft per ADR-004)
            continue

        rows = handler(engine, identity)
        items.extend(rows)

    return items


def _purchase_records(engine: Engine, identity: Identity) -> list[dict[str, Any]]:
    """historical_purchase: entities WHERE entity_type='purchase_record'.

    Returns list of {kind: 'historical_purchase', ref, attrs, src} (capped at
    100 per call; spec.limits.max_rows not applied here — caller truncates).
    """
    sql = """
        SELECT display_id, attributes, source_system, source_id
        FROM entities
        WHERE entity_type = 'purchase_record'
        LIMIT 100
    """
    return _rows_to_items(engine, identity, sql, kind="historical_purchase")


def _approval_history(engine: Engine, identity: Identity) -> list[dict[str, Any]]:
    """approval_history: entities WHERE entity_type='approval'."""
    sql = """
        SELECT display_id, attributes, source_system, source_id
        FROM entities
        WHERE entity_type = 'approval'
        LIMIT 100
    """
    return _rows_to_items(engine, identity, sql, kind="approval_history")


def _rows_to_items(
    engine: Engine, identity: Identity, sql: str, kind: str
) -> list[dict[str, Any]]:
    """Execute SQL + permission filter per row → structured_data item."""
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        display_id, attrs, source_system, source_id = r
        # Permission check on the row (per ADR-004)
        decision = check_permission(
            identity=identity,
            object_type="entity",
            object_ref=display_id,
            classification="department",
            acl_entries=[],
        )
        if not decision.allowed:
            continue
        items.append({
            "kind": kind,
            "ref": display_id,
            "attrs": attrs if isinstance(attrs, dict) else {},
            "src": {
                "system": source_system or "",
                "record_id": source_id or "",
            },
        })
    return items


_KIND_HANDLERS: dict[str, Any] = {
    "historical_purchase": _purchase_records,
    "approval_history": _approval_history,
}
