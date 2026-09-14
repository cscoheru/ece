"""S3.2 step 5 — Relationship retrieval with temporal + optional relation filter.

Per ARCHITECTURE §3 step 5: Retrieve relevant relationships from
spec.relationships; BFS for hops (v0 single-hop); apply permission filter
at SQL level (not post-filter; per ADR-004).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine


def get_relationships(
    engine: Engine,
    src_display_ids: list[str],
    relations: list[str] | None = None,
    as_of: date | None = None,
    max_rows: int = 100,
) -> list[dict]:
    """Fetch relationships where src is in src_display_ids.

    Args:
        engine: SQLAlchemy Engine
        src_display_ids: filter src_entity by these display_ids
        relations: optional list of relation types to filter (None = all)
        as_of: optional temporal anchor (None = current)
        max_rows: limit (caller passes spec.limits.max_relationships)

    Returns:
        list of dicts with keys:
          from_display_id, relation, to_display_id,
          valid_from, valid_to, source_system, source_ref, confidence
    """
    if not src_display_ids:
        return []

    params: dict[str, object] = {"limit": max_rows}

    rel_filter = ""
    if relations:
        rel_filter = "AND r.relation = ANY(:relations)"
        params["relations"] = list(relations)

    temporal = ""
    if as_of:
        temporal = (
            "AND (r.valid_from IS NULL OR r.valid_from <= :as_of) "
            "AND (r.valid_to IS NULL OR r.valid_to > :as_of)"
        )
        params["as_of"] = as_of

    stmt = text(f"""
        SELECT s.display_id, r.relation, d.display_id,
               r.valid_from, r.valid_to,
               r.source_system, r.source_ref, r.confidence
        FROM relationships r
        JOIN entities s ON r.src_entity_id = s.id
        JOIN entities d ON r.dst_entity_id = d.id
        WHERE s.display_id IN :src_ids
        {rel_filter}
        {temporal}
        ORDER BY r.created_at DESC
        LIMIT :limit
    """).bindparams(bindparam("src_ids", expanding=True))

    params["src_ids"] = list(src_display_ids)

    with engine.connect() as conn:
        rows = conn.execute(stmt, params).fetchall()

    return [
        {
            "from_display_id": r[0],
            "relation": r[1],
            "to_display_id": r[2],
            "valid_from": r[3],
            "valid_to": r[4],
            "source_system": r[5] or "",
            "source_ref": r[6] or "",
            "confidence": float(r[7]) if r[7] is not None else 1.0,
        }
        for r in rows
    ]
