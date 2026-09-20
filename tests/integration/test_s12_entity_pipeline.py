"""R4 S1.2: entity pipeline + ontology gate."""
from __future__ import annotations

import pytest

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship


def test_upsert_entity_then_upsert_again_returns_existing() -> None:
    engine = get_engine()
    source_id = "R4-entity-test-001"
    # clean previous (relationships first to avoid FK violation; cut-009 path A
    # adds 1206 relationships referencing demo entities including this one)
    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM relationships WHERE "
                "src_entity_id IN (SELECT id FROM entities WHERE source_id = :sid) "
                "OR dst_entity_id IN (SELECT id FROM entities WHERE source_id = :sid)"
            ),
            {"sid": source_id},
        )
        conn.execute(
            __import__("sqlalchemy").text("DELETE FROM entities WHERE source_id = :sid"),
            {"sid": source_id},
        )

    # cut-040R-2 S1: explicit display_id — see test_s24_e2_security for why an
    # auto-allocated id in a shared namespace breaks other fixtures' datasets.
    r1 = upsert_entity(
        engine, "supplier", "R4 Test Co", "r4test", source_id,
        display_id="R4-ENTITY-TEST-001",
    )
    assert r1.created is True

    r2 = upsert_entity(
        engine, "supplier", "R4 Test Co RENAMED", "r4test", source_id,
        display_id="R4-ENTITY-TEST-001",
    )
    assert r2.created is False  # idempotent: same source_id
    # upsert_entity with DO NOTHING keeps original name (no UPDATE)
    with engine.connect() as conn:
        row = conn.execute(
            __import__("sqlalchemy").text("SELECT name FROM entities WHERE source_id = :sid"),
            {"sid": source_id},
        ).first()
    assert row is not None and row[0] == "R4 Test Co"  # original name preserved


def test_ontology_gate_rejects_bad_triple() -> None:
    engine = get_engine()
    # Need an entity to test against; use the supplier from previous test
    with engine.begin() as conn:
        row = conn.execute(
            __import__("sqlalchemy").text("SELECT display_id FROM entities WHERE source_id = 'R4-entity-test-001'")
        ).first()
    if row is None:
        pytest.skip("prerequisite entity not present; run test_upsert_entity first")
    sup = row[0]

    # Reject: 'supplier' has no SELECTS relation (only purchase_request does)
    inserted, reason = upsert_relationship(
        engine,
        src_display_id=sup,
        relation="SELECTS",
        dst_display_id=sup,
        source_system="r4test",
    )
    assert inserted is False
    assert "ontology rejected" in reason.lower()
