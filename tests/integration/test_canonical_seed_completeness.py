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
G7  a rejected relationship FAILS the seed instead of becoming a footnote, so a
    short fixture can never be reported as a successful canonical seed.
G8  a triple already owned by another `source_system` is detected too. That
    insert is a silent ON CONFLICT no-op, so the row count — never the insert
    counters — is the only thing that sees it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import text

from ece import seed as seed_module
from ece.db import get_engine
from ece.seed import (
    DEMO_RELATIONSHIP_SOURCE_SYSTEM,
    EXPECTED_RELS_PER_DEMO_PR,
    demo_relationship_fixture_status,
    run_seed,
    seed_demo_relationships,
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


@pytest.fixture(scope="module", autouse=True)
def _canonical_environment() -> None:
    """Guarantee a canonical environment before any guard in this module.

    These guards make claims about the SEED, so the environment must not be able
    to fail them for an unrelated reason — an earlier test file (e.g.
    test_s14_seed_idempotent) legitimately wipes `demo:*` entities. Declared
    after `_require_demo_dataset` so the skip still wins if demo.json is absent.

    This is NOT the "tests repair the environment" anti-pattern R2 removed: that
    was the E4/E5 RUNNERS healing the graph mid-evaluation and then scoring it.
    Here the setup runs before the assertion, and the assertions still test the
    environment's state. A broken environment still fails loudly — `run_seed()`
    raises rather than returning a half-built fixture.
    """
    if not demo_relationship_fixture_status(get_engine())["complete"]:
        run_seed()


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


def test_g7_rejected_relationship_fails_the_canonical_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejected edge must FAIL the seed, not become a footnote (R2.1).

    Before R2.1 `rejected` only fed a list and `ok` stayed True, so `make seed`
    reported success on a fixture that was short — the same "green but
    incomplete" shape R2 exists to remove.

    The patch is scoped with `monkeypatch.context()` so it is undone BEFORE the
    restoration seed in `finally`, which must run against the real function.
    """
    engine = get_engine()
    real_upsert = seed_module.upsert_relationship
    state = {"reject_next": True}

    def _reject_the_next_edge(*args, **kwargs):
        if state["reject_next"]:
            state["reject_next"] = False
            return False, "ontology rejected: forced by test_g7"
        return real_upsert(*args, **kwargs)

    try:
        with monkeypatch.context() as mp:
            mp.setattr(seed_module, "upsert_relationship", _reject_the_next_edge)

            result = seed_demo_relationships(engine)
            assert result["ok"] is False, (
                "one rejected relationship must fail the canonical seed, not be "
                f"reported as success; got {result}"
            )
            assert result["rejected"], result
            assert "forced by test_g7" in str(result["error"]), result["error"]
            assert len(result["rejected"]) == 1, (
                "expected exactly ONE rejected edge — a single rejection must be "
                f"enough to fail the seed; got {result['rejected'][:3]}"
            )

            state["reject_next"] = True  # re-arm for the propagation check
            with pytest.raises(RuntimeError, match="relationship seeding failed"):
                run_seed()
    finally:
        run_seed()

    assert demo_relationship_fixture_status(engine)["complete"] is True, (
        "the fixture was not restored after the G7 negative control"
    )


def test_g8_foreign_owned_triple_is_not_mistaken_for_a_complete_fixture() -> None:
    """`inserted=True` does not mean a row was written (R2.1).

    `uq_relationships_triple` keys on (src, relation, dst, valid_from) WITHOUT
    `source_system`, and `upsert_relationship` reports success for an ON CONFLICT
    DO NOTHING that wrote nothing. So a foreign fixture squatting on one of our
    triples costs us a row while every insert counter still reads six-per-PR.

    The triple is DISCOVERED from the live fixture rather than hardcoded, so the
    guard stays honest if the fixture's PR-to-target pairing ever changes.
    """
    engine = get_engine()
    squatter = "test:g8_foreign_squatter"

    with engine.connect() as conn:
        triple = conn.execute(
            text(
                """
                SELECT r.src_entity_id, r.relation, r.dst_entity_id
                FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE r.source_system = :f
                  AND r.relation = 'BELONGS_TO'
                  AND s.entity_type = 'purchase_request'
                  AND s.source_system = 'demo:demo'
                ORDER BY s.display_id
                LIMIT 1
                """
            ),
            {"f": DEMO_RELATIONSHIP_SOURCE_SYSTEM},
        ).first()
    assert triple is not None, "no demo BELONGS_TO edge found — run the canonical seed first"
    src_id, relation, dst_id = triple

    try:
        with engine.begin() as conn:
            # Free the triple (precise predicate, own source_system only), then
            # let a FOREIGN source_system own it. Plain INSERT, no ON CONFLICT —
            # a conflict here would mean the test's own setup is wrong, and it
            # must say so loudly.
            conn.execute(
                text(
                    "DELETE FROM relationships WHERE source_system = :f "
                    "AND src_entity_id = :s AND relation = :r AND dst_entity_id = :d"
                ),
                {"f": DEMO_RELATIONSHIP_SOURCE_SYSTEM, "s": src_id, "r": relation, "d": dst_id},
            )
            conn.execute(
                text(
                    "INSERT INTO relationships (src_entity_id, relation, dst_entity_id, "
                    "source_system, source_ref, confidence) "
                    "VALUES (:s, :r, :d, :ss, '', 1.0)"
                ),
                {"s": src_id, "r": relation, "d": dst_id, "ss": squatter},
            )

        result = seed_demo_relationships(engine)
        assert result["ok"] is False, (
            "a foreign source_system owning one of our triples must fail the "
            f"canonical seed; got {result}"
        )
        assert not result["rejected"], (
            f"this case is a silent no-op, NOT an ontology rejection: {result}"
        )
        assert "fixture incomplete" in str(result["error"]), result["error"]
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM relationships WHERE source_system = :s"),
                {"s": squatter},
            )
        run_seed()

    assert demo_relationship_fixture_status(engine)["complete"] is True, (
        "the fixture was not restored after the G8 negative control"
    )
