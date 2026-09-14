"""R4 S1.4: seed double-run creates=0 on second run (true idempotency)."""
from __future__ import annotations

import pytest

from ece.db import get_engine
from ece.seed import seed_from_demo_json


def test_seed_first_run_then_second_run_idempotent(tmp_path) -> None:
    """Two seed runs against demo.json: second run created counts must be 0."""
    engine = get_engine()
    demo = __import__("pathlib").Path("data/dataset/demo.json")
    if not demo.exists():
        pytest.skip("demo.json not generated; run make gen-dataset first")

    # Wipe all entities seeded by demo.json to make this test deterministic.
    # Safe because cut-005 R1 fix preserves demo.json md5.
    # First delete relationships referencing these entities (cut-009 added
    # 1206 relationships; FK constraint would otherwise block entity delete).
    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM relationships WHERE "
                "src_entity_id IN (SELECT id FROM entities WHERE source_system LIKE 'demo:%') "
                "OR dst_entity_id IN (SELECT id FROM entities WHERE source_system LIKE 'demo:%')"
            )
        )
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM entities WHERE source_system LIKE 'demo:%'"
            )
        )

    r1 = seed_from_demo_json(engine, demo)
    r2 = seed_from_demo_json(engine, demo)

    cb1: dict[str, int] = r1["created_by_type"]  # type: ignore[assignment]
    cb2: dict[str, int] = r2["created_by_type"]  # type: ignore[assignment]
    total1 = sum(cb1.values())
    total2 = sum(cb2.values())
    assert total1 > 0, "first run should create > 0 entities"
    assert total2 == 0, f"second run should create 0; got {total2}"
