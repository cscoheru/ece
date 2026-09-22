"""S1.2 -- Entity ingestion pipeline."""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# cut-043 — ontology check is now per-source-system (km:* → knowledge, spike:* → procurement).
# Falls back to procurement when no pack registered for the prefix.
from ece.entities.ontology_resolver import is_allowed_for_system

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
    """Allocate next display_id (e.g. SUP1001 -> SUP1002) per existing max + 1.

    Per cut-007 §4.2 bug fix: pre-existing implementation used
    `ORDER BY display_id DESC LIMIT 1` which is TEXT ordering.
    In text compare 'SUP999' > 'SUP1000' (because '9' > '1'),
    so max(text) returns 'SUP999' and max+1 = 'SUP1000' — but demo
    seed already has 'SUP1000' (source_id='supplier:45' from
    demo:demo), causing UNIQUE display_id conflict.

    Fix: iterate ALL matching display_ids, parse numeric suffix,
    find max numerically. After fix, demo's SUP1000 is detected
    and next becomes SUP1001.

    Tradeoff: O(N) scan per upsert. Acceptable for v0 (synthetic
    demo data, <100 suppliers). For larger datasets, consider a
    SQL-side CAST(SUBSTRING(...) AS INTEGER) MAX.
    """
    prefix = _DISPLAY_ID_PREFIX.get(entity_type, entity_type.upper()[:3])
    pattern = f"{prefix}%"

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = :etype AND display_id LIKE :pat
            """),
            {"etype": entity_type, "pat": pattern},
        ).fetchall()

    max_num = 0
    for (display_id,) in rows:
        if not display_id:
            continue
        m = re.search(r"(\d+)$", display_id)
        if m:
            n = int(m.group(1))
            if n > max_num:
                max_num = n

    return f"{prefix}{max_num + 1:03d}"


def upsert_entity(
    engine: Engine,
    entity_type: str,
    name: str,
    source_system: str,
    source_id: str,
    attributes: dict[str, Any] | None = None,
    display_id: str | None = None,
) -> EntityInsertResult:
    """Insert or upsert one entity. ON CONFLICT (etype, sys, sid) DO NOTHING.

    `display_id` (cut-040R-2 S1): optional EXPLICIT display_id. When omitted the
    behaviour is unchanged (`_next_display_id` = global max+1 per entity_type).
    A fixture that supplies its own id — e.g. "SPIKE-PR-001" — stays OUT of the
    shared numeric namespace, so it cannot raise the ceiling that `demo:demo`
    replays allocate from. Before this, a surviving foreign purchase_request
    shifted the whole demo display_id space on the next wipe+replay and silently
    invalidated the frozen E3/E4/E5 datasets.

    The caller is responsible for the value being unique (there is a UNIQUE
    index on `entities.display_id`).
    """
    if not name or not source_id:
        raise ValueError("entity name and source_id are required")

    with engine.begin() as conn:
        resolved_display_id = display_id or _next_display_id(engine, entity_type)
        normalized = _normalize_name(name)

        row = conn.execute(
            text("""
                INSERT INTO entities
                    (display_id, entity_type, name, normalized_name,
                     source_system, source_id, attributes)
                VALUES (:display_id, :etype, :name, :norm, :sys, :sid, CAST(:attrs AS jsonb))
                ON CONFLICT (entity_type, source_system, source_id) DO NOTHING
                RETURNING display_id
            """),
            {
                "display_id": resolved_display_id,
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
    valid_from: str | date | None = None,
    valid_to: str | date | None = None,
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

        if not is_allowed_for_system(src_type, relation, dst_type, source_system):
            return False, (
                f"ontology rejected: ({src_type})-[{relation}]->({dst_type}) "
                f"not in {source_system.split(':', 1)[0]} ontology"
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
