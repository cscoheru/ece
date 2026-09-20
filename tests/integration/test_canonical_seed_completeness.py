"""R2 — canonical seed completeness guards.

Why this file exists
--------------------
R2 found that `make seed` produced entities but ZERO relationships: the
relationship seeding lived only in `scripts/seed_relationships.py`, a manual
step that neither `make seed` nor CI ever ran. Nothing in the suite noticed,
because the tests that needed relationships repaired the graph themselves via
`subprocess`. A green suite therefore never proved the canonical seed was
complete — it proved the tests could compensate for it.

These guards make the SEED ITSELF the thing under test.

G5  canonical seed produces the complete relationship fixture, and re-running it
    is idempotent. Compared on the FULL distribution (per relation and per PR),
    not on `count(*) == 1200` — a total alone cannot distinguish "the right 1200
    rows" from "1200 rows in the wrong places".
G6  the E4/E5 precondition actually DETECTS a missing fixture. Without this
    negative control the precondition would be an untested guard, which is the
    same "unverified assertion" pattern that produced the earlier fake greens.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text

from ece.db import get_engine
from ece.seed import (
    DEMO_RELATIONSHIP_SOURCE_SYSTEM,
    EXPECTED_RELS_PER_DEMO_PR,
    demo_relationship_fixture_status,
    run_seed,
)

DEMO_JSON = Path("data/dataset/demo.json")


@dataclass(frozen=True)
class _Snapshot:
    total: int
    per_relation: tuple[tuple[str, str, int], ...]
    per_pr: tuple[tuple[str, int], ...]

    @property
    def per_pr_map(self) -> dict[str, int]:
        return dict(self.per_pr)


def _demo_pr_display_ids(engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE entity_type = 'purchase_request' AND source_system = 'demo:demo'"
            )
        ).fetchall()
    return {r[0] for r in rows}


def _snapshot(engine) -> _Snapshot:
    """Whole-database relationship distribution, order-normalised."""
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM relationships")).scalar_one()
        per_relation = conn.execute(
            text(
                "SELECT source_system, relation, count(*) FROM relationships "
                "GROUP BY 1, 2 ORDER BY 1, 2"
            )
        ).fetchall()
        per_pr = conn.execute(
            text(
                """
                SELECT s.display_id, count(*)
                FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE s.entity_type = 'purchase_request'
                  AND s.source_system = 'demo:demo'
                GROUP BY s.display_id
                ORDER BY s.display_id
                """
            )
        ).fetchall()

    return _Snapshot(
        total=int(total),
        per_relation=tuple((r[0], r[1], int(r[2])) for r in per_relation),
        per_pr=tuple((r[0], int(r[1])) for r in per_pr),
    )


@pytest.fixture(scope="module", autouse=True)
def _require_demo_dataset() -> None:
    if not DEMO_JSON.exists():
        pytest.skip("demo.json not generated; run `make gen-dataset` first")


def test_g5_canonical_seed_restores_complete_relationship_fixture() -> None:
    """`run_seed()` must build the whole fixture, and rebuilding must not drift.

    Expected total is DERIVED (demo PRs x 6), never hardcoded — a hardcoded 1200
    would silently pass on a database whose PR set had changed.
    """
    engine = get_engine()
    demo_prs = _demo_pr_display_ids(engine)
    assert demo_prs, (
        "no `demo:demo` purchase requests found — the canonical seed did not run. "
        "Run `make seed` (which now seeds entities AND relationships)."
    )
    expected_total = len(demo_prs) * EXPECTED_RELS_PER_DEMO_PR

    # ── first canonical seed ────────────────────────────────────────────────
    run_seed()
    first = _snapshot(engine)

    assert set(first.per_pr_map) == demo_prs, (
        "some demo PRs have NO relationships after canonical seed: "
        f"{sorted(demo_prs - set(first.per_pr_map))[:10]}"
    )
    deviating = {k: v for k, v in first.per_pr_map.items() if v != EXPECTED_RELS_PER_DEMO_PR}
    assert not deviating, (
        f"canonical seed should give every demo PR exactly "
        f"{EXPECTED_RELS_PER_DEMO_PR} relationships; deviating: "
        f"{sorted(deviating.items())[:8]}"
    )

    demo_relations = sum(n for ss, _rel, n in first.per_relation if ss == DEMO_RELATIONSHIP_SOURCE_SYSTEM)
    assert demo_relations == expected_total, (
        f"'{DEMO_RELATIONSHIP_SOURCE_SYSTEM}' holds {demo_relations} rows, expected "
        f"{expected_total} ({len(demo_prs)} demo PRs x {EXPECTED_RELS_PER_DEMO_PR})"
    )

    # ── second canonical seed: idempotent, distribution unchanged ───────────
    run_seed()
    second = _snapshot(engine)

    assert second.total == first.total, (
        f"canonical seed is not idempotent: total relationships went "
        f"{first.total} -> {second.total}"
    )
    assert second.per_relation == first.per_relation, (
        "relationship distribution DRIFTED across a re-seed (per source_system x "
        f"relation).\n  before: {first.per_relation}\n  after:  {second.per_relation}"
    )
    assert second.per_pr == first.per_pr, (
        "per-PR relationship counts drifted across a re-seed — the fixture is "
        "accumulating or losing rows instead of being rebuilt canonically."
    )


def test_g6_precondition_detects_missing_fixture() -> None:
    """Negative control for the E4/E5 precondition (R2 / C.3).

    An untested guard is how the previous fake greens happened: assert that the
    precondition actually reports `complete=False` when the fixture is gone, then
    restore it. `finally` guarantees restoration even if the assertion fails.
    """
    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM relationships WHERE source_system = :s"),
                {"s": DEMO_RELATIONSHIP_SOURCE_SYSTEM},
            )

        status = demo_relationship_fixture_status(engine)
        assert status["total"] == 0, "fixture should be empty after the wipe"
        assert status["complete"] is False, (
            "the precondition failed to detect a MISSING relationship fixture — "
            "E4/E5 would then score an empty graph instead of refusing to run"
        )
    finally:
        run_seed()

    restored = demo_relationship_fixture_status(engine)
    assert restored["complete"] is True, (
        "canonical seed did not restore the fixture after the negative control: "
        f"{restored}"
    )
