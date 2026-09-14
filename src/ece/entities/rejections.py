"""S2.4 Ontology rejection log: persist rejected triples per cut-005 §7.4 gap (a)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def log_rejection(
    engine: Engine,
    src_display_id: str,
    relation: str,
    dst_display_id: str,
    reason: str,
) -> int:
    """Persist an ontology rejection to ontology_rejections table.

    Per cut-005 §7.4 gap (a): ontology 拒绝 now also writes a row so audit is possible.
    Returns the inserted rejection_id (serial).
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO ontology_rejections
                    (src_display_id, relation, dst_display_id, reason)
                VALUES (:src, :rel, :dst, :reason)
                RETURNING id
            """),
            {"src": src_display_id, "rel": relation, "dst": dst_display_id, "reason": reason},
        )
        return result.scalar_one()


def count_rejections(engine: Engine) -> int:
    """Total rejected triples (audit metric for E2)."""
    with engine.connect() as conn:
        row = conn.execute(text("SELECT count(*) FROM ontology_rejections")).first()
    return int(row[0]) if row else 0
