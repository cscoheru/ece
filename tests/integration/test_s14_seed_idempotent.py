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

    # Wipe the entities that seed_from_demo_json() ITSELF creates, so the first
    # run is guaranteed to create > 0 and the second run 0.
    #
    # The predicate is EXACTLY the source_system that function writes
    # (src/ece/seed.py:169 — `f"demo:{path.stem}"` == "demo:demo" for
    # data/dataset/demo.json).
    #
    # It used to be `LIKE 'demo:%'` minus a HAND-MAINTAINED exclusion list, which
    # meant every other `demo:*` seeder had to remember to exclude itself:
    #   * cut-035R added the 'demo:seed_temporal_roles' exclusion
    #   * cut-040R-2 P1'' found that 'demo:seed_departments' (created by
    #     scripts/seed_relationships.py) had been silently destroyed by every
    #     suite run and never restored — the same class of defect as RC-6
    # Targeting the exact source_system is self-maintaining: a new `demo:*`
    # seeder can no longer be clobbered by this test.
    #
    # First delete relationships referencing these entities (cut-009 added
    # 1206 relationships; FK constraint would otherwise block entity delete).
    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM relationships WHERE "
                "src_entity_id IN (SELECT id FROM entities WHERE "
                "source_system = 'demo:demo') "
                "OR dst_entity_id IN (SELECT id FROM entities WHERE "
                "source_system = 'demo:demo')"
            )
        )
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM entities WHERE source_system = 'demo:demo'"
            )
        )

    r1 = seed_from_demo_json(engine, demo)
    r2 = seed_from_demo_json(engine, demo)

    # cut-040R-2 Final Evidence Repair: restore the relationship fixture this
    # test just destroyed. The wipe above deletes every relationship touching a
    # `demo:demo` entity, but `seed_from_demo_json` only recreates ENTITIES.
    # Without this, E4/E5 — and the eval-asset guards — measure an EMPTY graph
    # after any pytest run. (test_s4_5_temporal already did this locally; the
    # coupling that forced it is now fixed at the source instead.)
    import subprocess as _sp
    _sp.run(
        ["uv", "run", "python", "scripts/seed_relationships.py"],
        capture_output=True, text=True, check=False,
    )

    cb1: dict[str, int] = r1["created_by_type"]  # type: ignore[assignment]
    cb2: dict[str, int] = r2["created_by_type"]  # type: ignore[assignment]
    total1 = sum(cb1.values())
    total2 = sum(cb2.values())
    assert total1 > 0, "first run should create > 0 entities"
    assert total2 == 0, f"second run should create 0; got {total2}"
