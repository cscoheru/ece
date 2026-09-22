"""cut-042R2 R2-F2 — pack-owned deterministic relations materializer.

This module is the procurement-pack's materializer for SELECTS relations.
It is kept SEPARATE from `v0_rules.py` so the rule module remains a pure
function (per `tests/unit/test_v0_rule_and_decision.py::test_module_purity_no_sqlalchemy_no_engine`,
which forbids `sqlalchemy` / `Engine` in the rule module).

cut-042R2 R2-F2: rebuilds SELECTS relations whose source is the PR identified
by `root_source_id` so that the relation count equals `params["quote_count"]`.

Algorithm:
  1. If `quote_count` is absent from `params`, do nothing (preserves the
     fixture baseline for V0 spike regression tests; only the demo API
     path explicitly passes `quote_count`).
  2. DELETE all SELECTS rows for this PR scoped by the PR's own
     `source_system` (so the spike fixture (`SPIKE-*` suppliers) and the
     demo fixture (`SUP*` suppliers) are independent).
  3. Fetch suppliers from the SAME source_system (deterministic
     ORDER BY display_id).
  4. INSERT up to `min(quote_count, len(supplier_pool))` SELECTS relations,
     one per supplier in pool order. quote_count == 0 → zero inserts.

Clamps `quote_count` to the supplier pool size to avoid SQL duplicates
(multiple SELECTS to the same supplier violate the
`uq_relationships_triple` unique index).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

__all__ = ["materialize_quote_count"]


def materialize_quote_count(
    engine: Engine,
    root_source_id: str,
    params: dict[str, Any],
) -> None:
    """Pack-owned deterministic materializer for procurement pack's quote_count.

    Signature: ``(engine: Engine, root_source_id: str, params: dict) -> None``
    Matches the `RuleDescriptor.materialize_fn` contract declared in
    `ece.demo.registry`.
    """
    # cut-042R2 R2-F2: if quote_count is absent, this is a baseline
    # re-run (e.g. V0 spike regression tests via run_v0_loop with no params).
    # Skip the materialize so the fixture's pre-seeded SELECTS to
    # SPIKE-SUP-A stays intact.
    if "quote_count" not in params:
        return
    quote_count = max(0, int(params.get("quote_count") or 0))

    # Resolve the PR's source_system so we scope DELETE/INSERT to the
    # correct fixture (spike:v0-technical-fixture vs demo:demo).
    with engine.connect() as conn:
        pr_row = conn.execute(
            text("""
                SELECT source_system FROM entities
                WHERE source_id = :sid
            """),
            {"sid": root_source_id},
        ).first()
    if pr_row is None:
        return
    pr_source_system = pr_row[0]

    with engine.begin() as conn:
        # 1. DELETE existing SELECTS for this PR (scoped by source_system).
        conn.execute(
            text("""
                DELETE FROM relationships
                WHERE relation = 'SELECTS'
                  AND source_system = :sys
                  AND src_entity_id = (
                    SELECT id FROM entities
                    WHERE source_id = :sid AND source_system = :sys
                  )
            """),
            {"sid": root_source_id, "sys": pr_source_system},
        )

        if quote_count == 0:
            return

        # 2. Fetch supplier pool (deterministic order, SAME source_system
        #    as the PR — preserves fixture isolation).
        supplier_rows = conn.execute(
            text("""
                SELECT id, display_id FROM entities
                WHERE entity_type = 'supplier'
                  AND source_system = :sys
                ORDER BY display_id
            """),
            {"sys": pr_source_system},
        ).all()
        if not supplier_rows:
            return

        # 3. Resolve PR id.
        pr_row = conn.execute(
            text("""
                SELECT id FROM entities
                WHERE source_id = :sid AND source_system = :sys
            """),
            {"sid": root_source_id, "sys": pr_source_system},
        ).first()
        if pr_row is None:
            return

        pr_id = pr_row[0]

        # 4. INSERT up to min(quote_count, len(pool)) SELECTS relations, one
        #    per supplier in pool order. clamp avoids duplicate
        #    (src, relation, dst) tuples that would violate
        #    uq_relationships_triple.
        effective_count = min(quote_count, len(supplier_rows))
        for i in range(effective_count):
            supplier_id = supplier_rows[i][0]
            conn.execute(
                text("""
                    INSERT INTO relationships
                        (src_entity_id, relation, dst_entity_id,
                         source_system, source_ref, confidence)
                    VALUES (:src, 'SELECTS', :dst, :sys, '', 1.0)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "src": pr_id,
                    "dst": supplier_id,
                    "sys": pr_source_system,
                },
            )

