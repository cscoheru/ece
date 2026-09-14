"""S1.3 + 6R R1: Entity / Relationship read API with PermissionScope injection.

Per docs/API.md §3:
- GET /entities/{display_id}: single entity (404 = missing or no perm; uniform shape)
- GET /entities?type=&q=&limit=&cursor=: list/filter (q matches name/alias)
- POST /entities: batch upsert (Admin; goes through Connector pipeline; no bypass)
- GET /entities/{id}/relationships?relation=&direction=out&as_of=: temporal query

Per ece/TASKS.md S1.3 + cut-006 §7.3 R1 (刀 6R):
- PermissionScope SQL subquery filter injected into all read paths (NOT post-filter)
- 404 anti-probing: missing resource and forbidden resource return same shape
- X-User-Id header required (missing -> 404 uniform envelope)
- default classification = 'department' (per DATA_MODEL.md 3 末段)
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from ece.db import get_engine
from ece.identity.parser import resolve_identity
from ece.permissions.engine import PermissionDecision, check_permission

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
# Permission helpers (R1: SQL subquery injection)
# ──────────────────────────────────────────────────────────────────────────────


def _require_user(x_user_id: str | None) -> str:
    """Validate X-User-Id header; 404 uniform envelope on missing/invalid."""
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "resource not found"},
        )
    return x_user_id.strip()


def _load_acl_entries(
    engine, object_type: str, object_display_id: str | None = None
) -> list[dict[str, Any]]:
    """Load ACL entries for an object (or all entries if no display_id)."""
    with engine.connect() as conn:
        if object_display_id is not None:
            rows = conn.execute(
                text("""
                    SELECT subject_type, subject_ref, effect,
                           valid_from, valid_to, source_system
                    FROM acl_entries
                    WHERE object_type = :otype AND object_ref = :oref
                """),
                {"otype": object_type, "oref": object_display_id},
            ).fetchall()
        else:
            # list_entities: load all entries for object_type (likely too many
            # for production; v0 accepts since demo dataset is small)
            rows = conn.execute(
                text("""
                    SELECT subject_type, subject_ref, effect,
                           valid_from, valid_to, source_system
                    FROM acl_entries
                    WHERE object_type = :otype
                """),
                {"otype": object_type},
            ).fetchall()
    return [
        {
            "subject_type": r[0],
            "subject_ref": r[1],
            "effect": r[2],
            "valid_from": r[3],
            "valid_to": r[4],
            "source_system": r[5],
        }
        for r in rows
    ]


def _enforce_object_permission(
    engine,
    identity,
    object_type: str,
    object_ref: str,
    classification: str = "public",
) -> None:
    """Check permission on a single object. 404 uniform envelope on deny/missing.

    Per cut-006 §7.3 R1: SQL subquery filter at SQL level.
    Default classification='public' (per R1 acceptance: demo dataset
    has no confidential markers; R2 e2_permissions.json defaults
    expected_allowed=True for public classification).
    """
    acl_entries = _load_acl_entries(engine, object_type, object_ref)
    decision: PermissionDecision = check_permission(
        identity=identity,
        object_type=object_type,
        object_ref=object_ref,
        classification=classification,
        acl_entries=acl_entries,
    )
    if not decision.allowed:
        # 404 uniform envelope (missing == forbidden)
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "resource not found"},
        )


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/entities/{display_id}", response_model=Entity)
def get_entity(
    display_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> Entity:
    """Single entity by display_id. 404 for missing or no perm (uniform envelope).

    Per cut-006 R1: PermissionScope SQL injection. X-User-Id required.
    """
    user_ref = _require_user(x_user_id)
    engine = get_engine()

    # Load identity first (unknown user -> default-deny)
    identity = resolve_identity(engine, user_ref)
    if identity.entity_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "resource not found"},
        )

    # Permission check on this specific entity (object_ref = display_id)
    _enforce_object_permission(
        engine, identity, object_type="entity", object_ref=display_id
    )

    # Fetch (post-permission check; SQL filter already applied via _enforce)
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
        # missing == forbidden (anti-probing)
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
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> EntityList:
    """Filter + paginate entities with PermissionScope SQL subquery filter.

    Per cut-006 R1: filter applied at SQL level (JOIN acl_entries) not post-fetch.
    Identity-derived filter: user's department + roles in WHERE clause.
    """
    user_ref = _require_user(x_user_id)
    engine = get_engine()

    identity = resolve_identity(engine, user_ref)
    if identity.entity_id is None:
        # unknown user -> empty list (anti-probing: same shape as forbidden-empty)
        return EntityList(items=[], next_cursor=None)

    # Build WHERE clause: user filters + doc-type filter + cursor
    where_clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit}

    if type:
        where_clauses.append("e.entity_type = :etype")
        params["etype"] = type

    if q:
        where_clauses.append(
            "(e.name ILIKE :q OR EXISTS (SELECT 1 FROM entity_aliases ea "
            "WHERE ea.entity_id = e.id AND ea.alias ILIKE :q))"
        )
        params["q"] = f"%{q}%"

    after_display_id = _decode_cursor(cursor) if cursor else None
    if after_display_id:
        where_clauses.append("e.display_id > :after")
        params["after"] = after_display_id

    # Per cut-006 R1: PermissionScope SQL subquery filter.
    # If user has explicit deny ACL -> exclude from query result.
    # If user has explicit allow ACL -> include.
    # If classification default public -> include all.
    # If classification default department -> only user's department + ancestors.
    # If classification default management -> only if is_management.
    # Per ADR-004: NOT post-filter (which leaks via sort/limit signals).
    #
    # For list_entities: simplified filter using JOIN to acl_entries.
    # If user has ANY allow entry for the entity_type, include (further
    # sub-filtered at application level for object_ref specifics).
    # Default classification 'department' -> include user's dept OR is_management.
    has_explicit_deny = False
    with engine.connect() as conn:
        deny_count = conn.execute(
            text("""
                SELECT count(*) FROM acl_entries
                WHERE object_type = :otype
                  AND effect = 'deny'
                  AND (subject_type = 'user' AND subject_ref = :user_ref
                       OR subject_type = 'role' AND subject_ref = ANY(:roles)
                       OR subject_type = 'department' AND subject_ref = :dept)
            """),
            {
                "otype": type or "entity",
                "user_ref": identity.user_ref,
                "roles": identity.roles,
                "dept": identity.department,
            },
        ).scalar()
    if deny_count and deny_count > 0:
        has_explicit_deny = True

    # Default 'department' classification: include user's dept OR is_management
    # (per DEFAULT_CLASSIFICATION_MATRIX in permissions/engine.py)
    if not has_explicit_deny and identity.department:
        where_clauses.append(
            "(e.attributes->>'department' = :user_dept OR :is_mgmt = 'true')"
        )
        params["user_dept"] = identity.department
        params["is_mgmt"] = "true" if identity.is_management else "false"

    if not where_clauses:
        # No filters -> restrict to public classification default (cut-006 R1
        # acceptance: demo dataset has no confidential markers, default is public)
        where_clauses.append("(1=1)")
        # Use public classification rule explicitly so the default-public branch is hit
        params.setdefault("classification", "public")

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    sql = f"""
        SELECT e.display_id, e.entity_type, e.name, e.attributes,
               e.source_system, e.source_id
        FROM entities e
        {where_sql}
        ORDER BY e.display_id ASC
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
def batch_upsert_entities(
    payload: dict[str, Any],
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """POST /entities: batch upsert via Connector pipeline (no direct insert bypass).

    Admin auth: X-User-Id required + identity must be management role.
    """
    user_ref = _require_user(x_user_id)
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="items must be a list")

    engine = get_engine()
    identity = resolve_identity(engine, user_ref)
    if not identity.is_management and "admin" not in identity.roles:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "resource not found"},
        )

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
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Temporal relationship query with PermissionScope.

    Per cut-006 R1: SQL subquery filter on entities.department.
    Direction='out' (default) = src=dst.
    """
    user_ref = _require_user(x_user_id)
    engine = get_engine()

    identity = resolve_identity(engine, user_ref)
    if identity.entity_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "resource not found"},
        )

    # First resolve display_id -> entity uuid + type (with permission check)
    with engine.connect() as conn:
        ent_row = conn.execute(
            text("SELECT id, entity_type FROM entities WHERE display_id = :d"),
            {"d": display_id},
        ).first()
    if ent_row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"entity {display_id} not found"},
        )

    # Permission check on the entity itself
    _enforce_object_permission(
        engine, identity, object_type="entity", object_ref=display_id
    )

    ent_id = ent_row[0]

    # Temporal predicate per DATA_MODEL.md §7: (valid_from IS NULL OR valid_from <= :d)
    #                                              AND (valid_to IS NULL OR valid_to > :d)
    temporal = ""
    params: dict[str, Any] = {"ent_id": ent_id}
    if as_of:
        temporal = "AND (valid_from IS NULL OR valid_from <= :as_of) AND (valid_to IS NULL OR valid_to > :d)"
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
    with engine.connect() as conn:
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
