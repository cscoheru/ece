"""Seed demo relationships (cut-009 path A — unlocks E4/E5 evaluation).

For each PR in demo seed, create 5 basic relationships:
- BELONGS_TO department  (procurement/finance/sales/D01)
- SUBMITTED_BY person
- SELECTS supplier
- CONTAINS product
- SUBJECT_TO policy

Idempotent thanks to UNIQUE INDEX uq_relationships_triple
(on src_entity_id, relation, dst_entity_id, COALESCE(valid_from, '0001-01-01'))
from migration 0002. Re-runs skip existing triples via ON CONFLICT DO NOTHING.

Also seeds 4 department entities (extracted from demo person attributes;
no separate department entities exist in current demo seed).

Run after `make seed`:
    uv run python scripts/seed_relationships.py

Per DATA_MODEL.md §2 + ontology whitelist (ece/domain_packs/procurement/ontology.py).
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship

# Departments inferred from demo person attributes (seed.py)
DEPARTMENTS = ["procurement", "finance", "sales", "D01"]


def _fetch_display_ids(engine, entity_type: str) -> list[str]:
    """Fetch all display_ids for a given entity_type, sorted."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE entity_type = :t ORDER BY display_id"
            ),
            {"t": entity_type},
        ).fetchall()
    return [r[0] for r in rows]


def _seed_departments(engine) -> list[str]:
    """Seed 4 department entities (no separate dept entities in demo)."""
    for dept in DEPARTMENTS:
        upsert_entity(
            engine,
            entity_type="department",
            name=dept.capitalize() if dept != "D01" else "D01 Department",
            source_system="demo:seed_departments",
            source_id=f"dept:{dept}",
            attributes={"name": dept},
        )
    return _fetch_display_ids(engine, "department")


def main() -> int:
    engine = get_engine()

    # 1. Seed departments first (needed for BELONGS_TO)
    print("Seeding 4 department entities...")
    dept_ids = _seed_departments(engine)
    if not dept_ids:
        print("ERROR: failed to seed departments", file=sys.stderr)
        return 1

    # 2. Fetch PR + target entity display_ids
    pr_ids = _fetch_display_ids(engine, "purchase_request")
    if not pr_ids:
        print("ERROR: no PRs found; run `make seed` first", file=sys.stderr)
        return 1

    people_ids = _fetch_display_ids(engine, "person")
    supplier_ids = _fetch_display_ids(engine, "supplier")
    product_ids = _fetch_display_ids(engine, "product")
    policy_ids = _fetch_display_ids(engine, "policy")

    if not (people_ids and supplier_ids and product_ids and policy_ids):
        print(
            "ERROR: missing entity types (need person/supplier/product/policy)",
            file=sys.stderr,
        )
        return 1

    # 3. For each PR, create 6 relationships (cyclic selection for variety)
    #
    # NOTE (cut-040R-2 Final Evidence Repair): this list has SIX entries, not
    # five — the 6th is the deliberate "2nd submitter for variety" added in
    # cut-009. The old comment said "5", and that stale count propagated into
    # `gen_eval_datasets.py` (E5 `expected_count`) and its docstring. The
    # implemented contract is 6 non-temporal relationships per PR.
    #
    # The fixture is made CANONICAL below (delete-then-insert scoped to this
    # script's own source_system): repeated runs, or runs interleaved with other
    # tests that mutate the person/supplier lists, used to leave 7-8 rows behind
    # and silently invalidate E5's expected count.
    counters: dict[str, int] = {
        "BELONGS_TO": 0,
        "SUBMITTED_BY": 0,
        "SELECTS": 0,
        "CONTAINS": 0,
        "SUBJECT_TO": 0,
    }

    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM relationships WHERE source_system = :s"),
            {"s": "demo:seed_relationships"},
        ).rowcount
    if deleted:
        print(f"  Removed {deleted} prior 'demo:seed_relationships' rows (canonical reseed)")

    for i, pr_id in enumerate(pr_ids):
        rel_specs = [
            ("BELONGS_TO", dept_ids[i % len(dept_ids)]),
            ("SUBMITTED_BY", people_ids[i % len(people_ids)]),
            ("SELECTS", supplier_ids[i % len(supplier_ids)]),
            ("CONTAINS", product_ids[i % len(product_ids)]),
            ("SUBMITTED_BY", people_ids[(i + 1) % len(people_ids)]),  # 2nd submitter for variety
            ("SUBJECT_TO", policy_ids[i % len(policy_ids)]),
        ]
        # Dedupe rel_specs in case of cyclic collisions
        seen_targets: set[tuple[str, str]] = set()
        for rel_type, target in rel_specs:
            key = (rel_type, target)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            inserted, reason = upsert_relationship(
                engine,
                src_display_id=pr_id,
                relation=rel_type,
                dst_display_id=target,
                source_system="demo:seed_relationships",
            )
            if inserted:
                counters[rel_type] += 1

    # 4. Report
    print(f"\nSeeded relationships from {len(pr_ids)} PRs:")
    for rel, count in counters.items():
        print(f"  {rel}: {count} new insertions")

    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM relationships")).scalar()
    print(f"Total relationships in DB: {total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
