"""Seed temporal role entities + HAS_ROLE relationships (cut-013).

Per PRD §48 + 2025/2026 procurement manager change scenario:
- U001 (Demo Procurement Manager) was procurement_manager until 2025-12-31
- U002 (Demo Finance Manager) became procurement_manager from 2026-01-01

Enables E5 temporal predicate testing (as_of in 2025 vs 2026 sees different
active manager relationships).

Idempotent: re-runnable; UNIQUE INDEX on (src_entity_id, relation,
dst_entity_id, COALESCE(valid_from, '0001-01-01')) ensures no duplicates.

Note: role display_ids are auto-allocated by upsert_entity (R001, R002, R003
typically) — capture result.display_id to use in subsequent upsert_relationship.

Run after `make seed`:
    uv run python scripts/seed_temporal_roles.py
"""
from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import text

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship
# cut-043R R5-B3 — inverted resolver requires the pack side-effect to fire.
import ece.domain_packs.procurement  # noqa: F401

# Roles to seed (extracted from demo person attributes + PRD §48)
ROLES = ["procurement_manager", "finance_manager", "buyer"]


def main() -> int:
    engine = get_engine()

    # 1. Seed role entities and capture allocated display_ids
    # (upsert_entity auto-allocates display_id like R001, R002, ...)
    role_display_ids: dict[str, str] = {}
    for role in ROLES:
        result = upsert_entity(
            engine,
            entity_type="role",
            name=role,
            source_system="demo:seed_temporal_roles",
            source_id=f"role:{role}",
            attributes={"name": role},
        )
        role_display_ids[role] = result.display_id
    print(f"Seeded {len(ROLES)} role entities; display_ids={role_display_ids}")

    # 2. Seed HAS_ROLE temporal relationships (using allocated display_ids)
    # U001 was procurement_manager until 2025-12-31
    inserted_u1, reason_u1 = upsert_relationship(
        engine,
        src_display_id="U001",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["procurement_manager"],
        source_system="demo:seed_temporal_roles",
        valid_from=date(2020, 1, 1),
        valid_to=date(2025, 12, 31),
    )
    print(f"U001 HAS_ROLE procurement_manager (2020-01-01 to 2025-12-31): {reason_u1}")

    # U002 took over from 2026-01-01 (current, valid_to=NULL)
    inserted_u2, reason_u2 = upsert_relationship(
        engine,
        src_display_id="U002",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["procurement_manager"],
        source_system="demo:seed_temporal_roles",
        valid_from=date(2026, 1, 1),
        valid_to=None,
    )
    print(f"U002 HAS_ROLE procurement_manager (2026-01-01 to NULL/current): {reason_u2}")

    # U003 (Demo Engineering Manager) was buyer (no time constraint)
    inserted_u3, reason_u3 = upsert_relationship(
        engine,
        src_display_id="U003",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["buyer"],
        source_system="demo:seed_temporal_roles",
    )
    print(f"U003 HAS_ROLE buyer (no time constraint): {reason_u3}")

    # Verify
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM relationships WHERE source_system = 'demo:seed_temporal_roles'")
        ).scalar()
    print(f"Total temporal relationships in DB: {total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
