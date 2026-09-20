"""cut-040R-2 R40R2.1 (RC-6): seed state integrity after a wipe + replay.

The bug this guards against: `_seed_entity_departments()` used to be called
only from `run_seed()`, NOT from `seed_from_demo_json()`. Any test that wipes
the demo-seeded entities and replays `seed_from_demo_json()` (e.g.
`test_s14_seed_idempotent`) therefore destroyed
`entities.attributes.department` and never restored it. E2 then measured a
scrubbed DB — the department-based permission cases silently reverted to their
pre-fix behaviour.

(That wipe predicate was later narrowed to `source_system = 'demo:demo'`; see
test_s14's comment — the previous `LIKE 'demo:%'` sweep also destroyed
`demo:seed_departments`.)

The invariant: after a wipe + replay, the seeded entities must carry their
`attributes.department` again. Without the R40R2.1 fix this test fails with a
non-zero NULL count.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from ece.db import get_engine
from ece.seed import _DATASET_TO_ENTITY, seed_from_demo_json

# Entity types whose seed path must inject attributes.department
# (mirrors the map in src/ece/seed.py::_seed_entity_departments).
_DEPT_ENTITY_TYPES = ("contract", "purchase_request", "supplier", "policy", "product")


def _entity_counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT entity_type, count(*)
                FROM entities
                WHERE entity_type = ANY(:types)
                GROUP BY entity_type
                """
            ),
            {"types": list(_DEPT_ENTITY_TYPES)},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def _null_dept_counts(engine) -> dict[str, int]:
    """Per-type count of entities whose attributes.department is missing."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT entity_type, count(*)
                FROM entities
                WHERE entity_type = ANY(:types)
                  AND (attributes IS NULL OR attributes->>'department' IS NULL)
                GROUP BY entity_type
                """
            ),
            {"types": list(_DEPT_ENTITY_TYPES)},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def test_seed_replay_after_wipe_restores_departments() -> None:
    """R40R2.1: wipe demo:% entities, replay seed, assert department restored."""
    engine = get_engine()
    demo = Path("data/dataset/demo.json")
    if not demo.exists():
        pytest.skip("demo.json not generated; run make gen-dataset first")

    # Same predicate as tests/integration/test_s14_seed_idempotent.py so this
    # test reproduces exactly the state that used to clobber the department
    # attributes: wipe precisely what seed_from_demo_json() creates
    # (`source_system = 'demo:demo'`), not a `LIKE 'demo:%'` sweep.
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM relationships WHERE "
                "src_entity_id IN (SELECT id FROM entities WHERE "
                "source_system = 'demo:demo') "
                "OR dst_entity_id IN (SELECT id FROM entities WHERE "
                "source_system = 'demo:demo')"
            )
        )
        conn.execute(
            text("DELETE FROM entities WHERE source_system = 'demo:demo'")
        )

    # Precondition: the wipe really did remove the demo-seeded entities. Other
    # suites create entities under different source_system tags (e.g.
    # R5_TEST_SUPPLIER) and are deliberately left alone. A wipe leaves the
    # demo rows gone entirely, so the RC-6 damage only becomes observable after
    # the replay recreates them.
    with engine.connect() as conn:
        remaining_demo = conn.execute(
            text("SELECT count(*) FROM entities WHERE source_system = 'demo:demo'")
        ).scalar()
    assert remaining_demo == 0, (
        f"precondition failed: wipe left {remaining_demo} demo:demo entities behind"
    )

    seed_from_demo_json(engine, demo)

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

    restored = _entity_counts(engine)
    assert sum(restored.values()) > 0, (
        "seed replay created no entities — the invariant cannot be evaluated"
    )

    nulls = _null_dept_counts(engine)
    assert sum(nulls.values()) == 0, (
        "R40R2.1 REGRESSION: seed_from_demo_json did not restore "
        f"attributes.department after the wipe; NULL counts per type = {nulls}"
    )


def test_seed_from_demo_json_is_the_only_required_entrypoint() -> None:
    """R40R2.1: department injection must live inside seed_from_demo_json.

    If this ever moves back into run_seed(), the previous test will fail — this
    one makes the dependency explicit at the API level.
    """
    engine = get_engine()
    demo = Path("data/dataset/demo.json")
    if not demo.exists():
        pytest.skip("demo.json not generated; run make gen-dataset first")

    result = seed_from_demo_json(engine, demo)

    assert "attributes_department_updated" in result, (
        "seed_from_demo_json must report attributes_department_updated — the "
        "department injection has to be part of this function's contract, not a "
        "separate step callers must remember (R40R2.1)"
    )
    assert isinstance(result["attributes_department_updated"], int)
    # sanity: the map covers the entity types the E2 suite depends on
    assert set(_DEPT_ENTITY_TYPES) <= set(_DATASET_TO_ENTITY.values()) | {"policy", "product"}
