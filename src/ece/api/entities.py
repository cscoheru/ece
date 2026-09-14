"""S1.3 -- Entity / Relationship read API.

Per docs/API.md §3:
- GET /entities/{display_id}: single entity (404 = missing or no perm; uniform shape)
- GET /entities?type=&q=&limit=&cursor=: list/filter (q matches name/alias)
- POST /entities: batch upsert (Admin; goes through Connector pipeline; no bypass)
- GET /entities/{id}/relationships?relation=&direction=out&as_of=: temporal query

Per ece/TASKS.md S1.3:
- Strict API.md field contract
- 404 anti-probing: missing resource and (future) forbidden resource return same shape
- Pagination params as per docs
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from ece.db import get_engine

router = APIRouter(prefix="/api/v1", tags=["entities"])


# ──────────────────────────────────────────────────────────────────────────────
# Response models
# ──────────────────────────────────────────────────────────────────────────────


class Entity(BaseModel):
    """GET /entities/{display_id} response."""

    ref: str = Field(..., description="display_id (e.g. SUP001)")
    type: str = Field(..., description="entity_type")
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    src: dict[str, Any] = Field(..., description="provenance {system, record_id}")


class EntityList(BaseModel):
    """GET /entities response."""

    items: list[Entity]
    next_cursor: str | None = Field(None, description="opaque cursor for next page; null when no more")


class Relationship(BaseModel):
    """GET /entities/{id}/relationships response item."""

    from_: str = Field(..., alias="from", description="src display_id")
    rel: str
    to: str
    valid: list[str | None] = Field(..., description="[valid_from, valid_to]; null = -inf/+inf")
    src: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# Cursor helpers (opaque base64 of last display_id seen)
# ──────────────────────────────────────────────────────────────────────────────


def _encode_cursor(last_display_id: str) -> str:
    return base64.urlsafe_b64encode(last_display_id.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/entities/{display_id}", response_model=Entity)
def get_entity(display_id: str) -> Entity:
    """Single entity by display_id. 404 for missing (uniform shape; perm-equivalent)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT display_id, entity_type, name, attributes,
                       source_system, source_id
                FROM entities WHERE display_id = :d
            """),
            {"d": display_id},
        ).first()

    if row is None:
        # 404 anti-probing: shape identical to forbidden case (future perm check).
        # For now, just 404 with same envelope.
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"entity {display_id} not found"},
        )

    return Entity(
        ref=row[0],
        type=row[1],
        name=row[2],
        attributes=row[3] if isinstance(row[3], dict) else {},
        src={"system": row[4], "record_id": row[5]},
    )


@router.get("/entities", response_model=EntityList)
def list_entities(
    type: str | None = Query(None, description="filter by entity_type"),
    q: str | None = Query(None, description="substring match on name or alias"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None, description="opaque cursor from previous page"),
) -> EntityList:
    """Filter + paginate entities. Pagination by display_id ASC."""
    engine = get_engine()
    after_display_id = _decode_cursor(cursor) if cursor else None

    where_clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if type:
        where_clauses.append("entity_type = :etype")
        params["etype"] = type
    if q:
        where_clauses.append(
            "(name ILIKE :q OR EXISTS (SELECT 1 FROM entity_aliases ea "
            "WHERE ea.entity_id = e.id AND ea.alias ILIKE :q))"
        )
        params["q"] = f"%{q}%"
    if after_display_id:
        where_clauses.append("display_id > :after")
        params["after"] = after_display_id

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sql = f"""
        SELECT display_id, entity_type, name, attributes, source_system, source_id
        FROM entities e
        {where_sql}
        ORDER BY display_id ASC
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    items = [
        Entity(
            ref=r[0],
            type=r[1],
            name=r[2],
            attributes=r[3] if isinstance(r[3], dict) else {},
            src={"system": r[4], "record_id": r[5]},
        )
        for r in rows
    ]
    next_cursor = _encode_cursor(rows[-1][0]) if len(rows) == limit else None

    return EntityList(items=items, next_cursor=next_cursor)


@router.post("/entities")
def batch_upsert_entities(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /entities: batch upsert via Connector pipeline (no direct insert bypass).

    For S1.3 we accept the payload but route through upsert_entity for each row.
    Admin auth is enforced at the API gateway (future S2 permission).
    """
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="items must be a list")

    engine = get_engine()
    created = 0
    updated = 0
    errors: list[dict[str, object]] = []

    from ece.entities.pipeline import upsert_entity

    for idx, row in enumerate(rows):
        try:
            result = upsert_entity(
                engine,
                entity_type=row["type"],
                name=row["name"],
                source_system=row.get("source_system", "admin:api"),
                source_id=row["source_id"],
                attributes=row.get("attributes", {}),
            )
            if result.created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            errors.append({"index": idx, "source_id": row.get("source_id", ""), "error": str(e)})

    return {"created": created, "updated": updated, "errors": errors}


@router.get("/entities/{display_id}/relationships")
def list_relationships(
    display_id: str,
    relation: str | None = Query(None, description="filter by relation type"),
    direction: str = Query("out", description="out (default) | in | both"),
    as_of: str | None = Query(None, description="ISO date for temporal filter (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Temporal relationship query. direction='out' (default) = src=dst."""
    engine = get_engine()
    with engine.connect() as conn:
        # First resolve display_id -> entity uuid + type
        ent_row = conn.execute(
            text("SELECT id, entity_type FROM entities WHERE display_id = :d"),
            {"d": display_id},
        ).first()
        if ent_row is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": f"entity {display_id} not found"},
            )
        ent_id = ent_row[0]

        # Temporal predicate per DATA_MODEL.md §7: (valid_from IS NULL OR valid_from <= :d)
        #                                              AND (valid_to IS NULL OR valid_to > :d)
        temporal = ""
        params = {"ent_id": ent_id}
        if as_of:
            temporal = "AND (valid_from IS NULL OR valid_from <= :as_of) AND (valid_to IS NULL OR valid_to > :as_of)"
            params["as_of"] = as_of
        if relation:
            temporal += " AND relation = :rel"
            params["rel"] = relation

        if direction == "out":
            where = f"src_entity_id = :ent_id {temporal}"
        elif direction == "in":
            where = f"dst_entity_id = :ent_id {temporal}"
        else:  # both
            where = f"(src_entity_id = :ent_id OR dst_entity_id = :ent_id) {temporal}"

        sql = f"""
            SELECT s.display_id, r.relation, d.display_id,
                   r.valid_from, r.valid_to, r.source_system, r.source_ref
            FROM relationships r
            JOIN entities s ON r.src_entity_id = s.id
            JOIN entities d ON r.dst_entity_id = d.id
            WHERE {where}
            ORDER BY r.created_at DESC
        """
        rows = conn.execute(text(sql), params).fetchall()

    rels = [
        Relationship(
            **{"from": r[0], "rel": r[1], "to": r[2],
              "valid": [r[3].isoformat() if r[3] else None,
                        r[4].isoformat() if r[4] else None],
              "src": {"system": r[5], "record_id": r[6] or ""}}
        )
        for r in rows
    ]
    # pydantic v2 alias: dump by_alias to serialize 'from' as 'from' not 'from_'
    return {"items": [r.model_dump(by_alias=True) for r in rels]}
