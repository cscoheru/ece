"""cut-040R-2 Final Evidence Repair — evaluation-asset integrity guards.

Why this file exists
--------------------
E3/E4/E5 were measuring the wrong thing, invisibly:

* **E3** scored 15% because `e3_context.json` referenced `PR001…PR030`, which no
  longer exist — `_next_display_id` allocates `max+1`, so every
  `test_s14_seed_idempotent` wipe+replay shifts the whole `display_id` space
  upward. The dataset went stale and **nothing said so**.
* **E4** scored 100% **vacuously**: its bounds were `[0, 100]`, so a missing
  entity (0 relationships) was "inside the band".
* **E5** scored 0% because the relationship fixture had been destroyed, and its
  `expected_count` (5) never matched the implementation (6) — the mismatch
  survived unnoticed because the runner crashed from the day it was written.

These guards make each of those failure modes LOUD instead of silent.

Guards
------
G1  every `display_id` referenced by the E3/E4/E5 datasets exists  (stale-reference)
G2  the relationship fixture is canonical: exactly 6 relationships per PR,
    all from `demo:seed_relationships`, none from another `source_system`
    (pollution)
G3  temporal semantics: `valid_from = valid_to = NULL` means [-∞, +∞) and
    therefore matches at EVERY `as_of`  (contract regression)
G4  the E4/E5 datasets' expected counts agree with the fixture  (dataset↔fixture)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine

EVAL_DIR = Path("data/eval")

# Canonical fixture contract: scripts/seed_relationships.py creates SIX
# relationships per purchase request (its `rel_specs` list has six entries —
# the 6th being the deliberate "2nd submitter for variety").
EXPECTED_RELS_PER_PR = 6


def _load(name: str) -> list[dict]:
    p = EVAL_DIR / name
    if not p.exists():
        pytest.skip(f"{name} not generated; run make gen-eval-datasets")
    return json.loads(p.read_text(encoding="utf-8"))["cases"]


def _existing_display_ids() -> set[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT display_id FROM entities")).fetchall()
    return {r[0] for r in rows}


# ─────────────────────────────────────────────────────────────────────────────
# G1 — stale-reference guard
# ─────────────────────────────────────────────────────────────────────────────
def test_g1_e3_dataset_display_ids_all_exist() -> None:
    """Every `root.id` that an E3 case expects to RESOLVE must exist in `entities`.

    Cases with `expect == "insufficient_context"` are negative tests — they
    deliberately reference `PR_NONEXISTENT_*`, so they are exempt. Only the
    `expect == "ok"` cases can go stale.
    """
    cases = _load("e3_context.json")
    present = _existing_display_ids()
    missing: dict[str, list[str]] = {}
    for c in cases:
        if c.get("expect") != "ok":
            continue  # negative case: absent object is the point
        rid = (c.get("root") or {}).get("id")
        if rid and rid not in present:
            missing.setdefault(rid, []).append(c["id"])
    assert not missing, (
        "E3 dataset has STALE display_id references in `expect=ok` cases "
        "(they no longer exist in the DB). Root cause: `_next_display_id` "
        "allocates max+1, so a wipe+replay can shift the whole display_id space — "
        "regenerate with `make gen-eval-datasets` after seeding. "
        f"Missing: {sorted(missing)[:10]}"
        + (f" (+{len(missing) - 10} more)" if len(missing) > 10 else "")
        + f" [affected cases: {sorted(c for v in missing.values() for c in v)[:10]}]"
    )


def test_g1_e4_e5_dataset_display_ids_all_exist() -> None:
    """Every `from` in e4/e5 datasets must exist in `entities`."""
    present = _existing_display_ids()
    for name in ("e4_relationships.json", "e5_temporal.json"):
        missing = [c["id"] for c in _load(name) if c["from"] not in present]
        assert not missing, (
            f"{name} has STALE display_id references: {missing[:10]}"
            + (f" (+{len(missing) - 10} more)" if len(missing) > 10 else "")
        )


# ─────────────────────────────────────────────────────────────────────────────
# G2 — pollution guard
# ─────────────────────────────────────────────────────────────────────────────
def test_g2_relationship_fixture_is_canonical() -> None:
    """Every PR must have exactly the canonical 6 relationships, and no
    relationship may come from a `test:*` source_system."""
    engine = get_engine()
    with engine.connect() as conn:
        deviating = conn.execute(
            text(
                """
                SELECT s.display_id, count(*) AS n
                FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE s.entity_type = 'purchase_request'
                  AND s.source_system = 'demo:demo'
                GROUP BY s.display_id
                HAVING count(*) != :want
                ORDER BY s.display_id
                """
            ),
            {"want": EXPECTED_RELS_PER_PR},
        ).fetchall()
        polluted = conn.execute(
            text(
                "SELECT DISTINCT source_system FROM relationships "
                "WHERE source_system LIKE 'test:%'"
            )
        ).fetchall()

    assert not polluted, (
        "E5 pollution: relationships from a TEST source_system are present — "
        f"{[r[0] for r in polluted]}. A test is leaking rows; it must clean up in `finally`. "
        "E5 counts relationships per PR, so any leftover row invalidates it."
    )
    assert not deviating, (
        f"Relationship fixture is NOT canonical: {len(deviating)} PR(s) deviate from "
        f"{EXPECTED_RELS_PER_PR}. Sample: {[(r[0], r[1]) for r in deviating[:8]]}. "
        "Re-seed with `uv run python scripts/seed_relationships.py` (it is now "
        "delete-then-insert scoped to its own source_system)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# G3 — temporal semantics regression
# ─────────────────────────────────────────────────────────────────────────────
def test_g3_null_validity_means_always_valid() -> None:
    """DATA_MODEL.md: `valid_from NULL = -∞`, `valid_to NULL = +∞`, interval
    [from, to). So a relationship with both NULL is permanently valid and must
    be returned at EVERY `as_of`.

    Regression guard for `get_relationships`:
        (valid_from IS NULL OR valid_from <= :d) AND (valid_to IS NULL OR valid_to > :d)
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT s.display_id FROM relationships r "
                "JOIN entities s ON s.id = r.src_entity_id "
                "WHERE r.valid_from IS NULL AND r.valid_to IS NULL "
                "AND s.entity_type = 'purchase_request' "
                "ORDER BY s.display_id LIMIT 1"
            )
        ).first()
    if not row:
        pytest.skip("no NULL/NULL relationship in the fixture")
    pr = row[0]

    counts = []
    for as_of in ("1990-01-01", "2024-01-01", "2026-09-14", "2099-12-31"):
        pkg = assemble_context(
            engine=engine,
            user_ref="demo-user-procurement",
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": pr}],
            as_of=date.fromisoformat(as_of),
        ).to_dict()
        counts.append(len(pkg["relationships"]))

    assert len(set(counts)) == 1, (
        f"Temporal contract violated: a NULL/NULL (=[-∞,+∞)) relationship must be "
        f"visible at every as_of, but counts differ across dates: {counts} "
        f"(as_of 1990-01-01 / 2024-01-01 / 2026-09-14 / 2099-12-31) for {pr}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# G4 — dataset ↔ fixture agreement
# ─────────────────────────────────────────────────────────────────────────────
def test_g4_e5_expected_count_matches_fixture() -> None:
    """E5's `expected_count` must equal the canonical fixture count."""
    for c in _load("e5_temporal.json"):
        assert c["expected_count"] == EXPECTED_RELS_PER_PR, (
            f"{c['id']}: expected_count={c['expected_count']} but the canonical "
            f"fixture creates {EXPECTED_RELS_PER_PR} relationships per PR "
            "(scripts/seed_relationships.py rel_specs has six entries). "
            "Align the DATASET to the implementation — never the reverse."
        )


def test_g4_e4_bounds_are_not_vacuous() -> None:
    """E4 must not accept an empty graph: its lower bound has to be > 0."""
    for c in _load("e4_relationships.json"):
        lo = c.get("expected_count_min", 0)
        assert lo > 0, (
            f"{c['id']}: expected_count_min={lo} makes E4 pass VACUOUSLY — a missing "
            "entity yields 0 relationships, which is inside [0, max]. "
            "Bounds must reflect the canonical fixture."
        )
