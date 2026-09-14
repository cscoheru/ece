"""S1.2 -- Entity ingestion pipeline."""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.domain_packs.procurement import is_allowed

# entity_type -> display_id prefix mapping (per PRD 10)
_DISPLAY_ID_PREFIX = {
    "person": "U",
    "department": "D",
    "role": "R",
    "supplier": "SUP",
    "product": "PRD",
    "contract": "CON",
    "purchase_request": "PR",
    "purchase_order": "PO",
    "approval": "APR",
    "policy": "POL",
    "document": "DOC",
}


@dataclass
class EntityInsertResult:
    """Per-entity insert outcome."""

    entity_type: str
    display_id: str
    created: bool  # True = new row, False = existing upsert


def _normalize_name(name: str) -> str:
    """Normalize name: strip whitespace, drop company suffix. Used for exact/normalized match."""
    if not name:
        return ""
    s = re.sub(r"\s+", "", name)
    s = s.lower()
    for suffix in ("Co., Ltd.", "Inc.", "Corp.", "Group"):
        s = s.removesuffix(suffix)
    return s


def _next_display_id(engine: Engine, entity_type: str) -> str:
    """Allocate next display_id (e.g. SUP001 -> SUP002) per existing max + 1."""
    prefix = _DISPLAY_ID_PREFIX.get(entity_type, entity_type.upper()[:3])
    pattern = f"{prefix}%"

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = :etype AND display_id LIKE :pat
                ORDER BY display_id DESC LIMIT 1
            """),
            {"etype": entity_type, "pat": pattern},
        ).first()

    if row is None:
        return f"{prefix}001"
    last_id = row[0] or ""
    m = re.search(r"(\d+)$", last_id)
    next_num = (int(m.group(1)) + 1) if m else 1
    return f"{prefix}{next_num:03d}"


def upsert_entity(
    engine: Engine,
    entity_type: str,
    name: str,
    source_system: str,
    source_id: str,
    attributes: dict[str, Any] | None = None,
) -> EntityInsertResult:
    """Insert or upsert one entity. ON CONFLICT (etype, sys, sid) DO NOTHING."""
    if not name or not source_id:
        raise ValueError("entity name and source_id are required")

    with engine.begin() as conn:
        display_id = _next_display_id(engine, entity_type)
        normalized = _normalize_name(name)

        row = conn.execute(
            text("""
                INSERT INTO entities
                    (display_id, entity_type, name, normalized_name,
                     source_system, source_id, attributes)
                VALUES (:display_id, :etype, :name, :norm, :sys, :sid, :attrs::jsonb)
                ON CONFLICT (entity_type, source_system, source_id) DO NOTHING
                RETURNING display_id
            """),
            {
                "display_id": display_id,
                "etype": entity_type,
                "name": name,
                "norm": normalized,
                "sys": source_system,
                "sid": source_id,
                "attrs": __import__("json").dumps(attributes or {}),
            },
        ).first()

        if row is not None:
            return EntityInsertResult(
                entity_type=entity_type, display_id=row[0], created=True,
            )

        existing = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = :etype AND source_system = :sys AND source_id = :sid
            """),
            {"etype": entity_type, "sys": source_system, "sid": source_id},
        ).first()
        if existing is None:
            raise RuntimeError("upsert_entity: insert failed but no existing row found")
        return EntityInsertResult(
            entity_type=entity_type, display_id=existing[0], created=False,
        )


def upsert_relationship(
    engine: Engine,
    src_display_id: str,
    relation: str,
    dst_display_id: str,
    source_system: str,
    source_ref: str = "",
    confidence: float = 1.0,
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> tuple[bool, str]:
    """Insert one relationship; reject if (src_type, relation, dst_type) not in ontology.

    Returns: (inserted, reason)
      - inserted=True: row written
      - inserted=False: rejected (reason explains why)
    """
    with engine.begin() as conn:
        src_row = conn.execute(
            text("SELECT entity_type FROM entities WHERE display_id = :d"),
            {"d": src_display_id},
        ).first()
        dst_row = conn.execute(
            text("SELECT entity_type FROM entities WHERE display_id = :d"),
            {"d": dst_display_id},
        ).first()

        if src_row is None:
            return False, f"src entity not found: {src_display_id}"
        if dst_row is None:
            return False, f"dst entity not found: {dst_display_id}"

        src_type, dst_type = src_row[0], dst_row[0]

        if not is_allowed(src_type, relation, dst_type):
            return False, (
                f"ontology rejected: ({src_type})-[{relation}]->({dst_type}) "
                f"not in procurement/ontology.yaml"
            )

        ids = conn.execute(
            text("""
                SELECT id, display_id FROM entities
                WHERE display_id IN (:src, :dst)
            """),
            {"src": src_display_id, "dst": dst_display_id},
        ).fetchall()
        src_id = next(r[0] for r in ids if r[1] == src_display_id)
        dst_id = next(r[0] for r in ids if r[1] == dst_display_id)

        conn.execute(
            text("""
                INSERT INTO relationships
                    (src_entity_id, relation, dst_entity_id,
                     valid_from, valid_to, source_system, source_ref, confidence)
                VALUES (:src, :rel, :dst, :vf, :vt, :sys, :ref, :conf)
                ON CONFLICT DO NOTHING
            """),
            {
                "src": src_id,
                "rel": relation,
                "dst": dst_id,
                "vf": valid_from,
                "vt": valid_to,
                "sys": source_system,
                "ref": source_ref,
                "conf": confidence,
            },
        )

        return True, "ok"
