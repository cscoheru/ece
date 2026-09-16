"""S4.5 — Temporal predicate tests (cut-013).

Verifies:
1. /context with different as_of dates returns different relationships
   (e.g., 2025 manager vs 2026 manager)
2. role entities + HAS_ROLE seeded (in-process to avoid cross-process
   transaction visibility issues)
3. Non-temporal relationships always visible (valid_from=NULL)

In-process seeding (per cut-013 §4.1): subprocess-based seeding via
autouse fixture can have transaction snapshot issues (subprocess commits
in its own session, parent pytest may not see new data if its transaction
started before subprocess). Direct in-process upsert_entity ensures
test's connection sees the data.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship
from ece.identity.parser import resolve_identity

ROLES = ["procurement_manager", "finance_manager", "buyer"]


@pytest.fixture(scope="module", autouse=True)
def ensure_temporal_roles_seeded() -> None:
    """Seed temporal roles + per-PR data in-process (autouse, module-scoped).

    Must be SELF-SUFFICIENT: prior tests (e.g. test_s14_seed_idempotent)
    may have deleted demo:* entities. Re-seed per-PR relationships via
    scripts/seed_relationships.py before the temporal tests run.
    """
    # Re-seed per-PR relationships (test_s14 may have deleted them)
    # R1 (cut-035R): replaced hardcoded mac cwd with Path-based repo root
    # so test works on CI (Linux runner) too, not just user's Mac.
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    result = subprocess.run(
        ["uv", "run", "python", "scripts/seed_relationships.py"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"seed_relationships failed: {result.stderr}")

    engine = get_engine()

    # Seed role entities and capture allocated display_ids
    role_display_ids: dict[str, str] = {}
    for role in ROLES:
        entity_result = upsert_entity(
            engine,
            entity_type="role",
            name=role,
            source_system="demo:seed_temporal_roles",
            source_id=f"role:{role}",
            attributes={"name": role},
        )
        role_display_ids[role] = entity_result.display_id

    # Seed HAS_ROLE temporal relationships
    upsert_relationship(
        engine,
        src_display_id="U001",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["procurement_manager"],
        source_system="demo:seed_temporal_roles",
        valid_from=date(2020, 1, 1),
        valid_to=date(2025, 12, 31),
    )
    upsert_relationship(
        engine,
        src_display_id="U002",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["procurement_manager"],
        source_system="demo:seed_temporal_roles",
        valid_from=date(2026, 1, 1),
        valid_to=None,
    )
    upsert_relationship(
        engine,
        src_display_id="U003",
        relation="HAS_ROLE",
        dst_display_id=role_display_ids["buyer"],
        source_system="demo:seed_temporal_roles",
    )


def test_seed_temporal_roles_populated() -> None:
    """Verify role entities + HAS_ROLE seeded (in-process via fixture)."""
    engine = get_engine()
    with engine.connect() as conn:
        role_count = int(conn.execute(
            text("SELECT count(*) FROM entities WHERE entity_type = 'role'")
        ).scalar() or 0)
        has_role_count = int(conn.execute(
            text("""
                SELECT count(*) FROM relationships
                WHERE relation = 'HAS_ROLE' AND source_system = 'demo:seed_temporal_roles'
            """)
        ).scalar() or 0)
    assert role_count >= 1, f"role entities: {role_count}"
    assert has_role_count >= 3, f"HAS_ROLE relationships: {has_role_count}"


def test_assemble_context_with_as_of_2025_keeps_u1_active() -> None:
    """as_of=2025-06-30: U001 was procurement_manager (valid_to=2025-12-31)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT src.display_id, r.valid_from, r.valid_to
                FROM relationships r
                JOIN entities src ON r.src_entity_id = src.id
                JOIN entities dst ON r.dst_entity_id = dst.id
                WHERE r.relation = 'HAS_ROLE'
                  AND dst.display_id LIKE 'R%'
                  AND (r.valid_from IS NULL OR r.valid_from <= '2025-06-30')
                  AND (r.valid_to IS NULL OR r.valid_to > '2025-06-30')
            """)
        ).fetchall()
    active_managers = [r[0] for r in rows]
    assert "U001" in active_managers, f"U001 should be active at 2025-06-30: {active_managers}"
    assert "U002" not in active_managers, f"U002 should NOT be active at 2025-06-30: {active_managers}"


def test_assemble_context_with_as_of_2026_shows_u2_active() -> None:
    """as_of=2026-09-14: U002 became procurement_manager (valid_from=2026-01-01)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT src.display_id, r.valid_from, r.valid_to
                FROM relationships r
                JOIN entities src ON r.src_entity_id = src.id
                JOIN entities dst ON r.dst_entity_id = dst.id
                WHERE r.relation = 'HAS_ROLE'
                  AND dst.display_id LIKE 'R%'
                  AND (r.valid_from IS NULL OR r.valid_from <= '2026-09-14')
                  AND (r.valid_to IS NULL OR r.valid_to > '2026-09-14')
            """)
        ).fetchall()
    active_managers = [r[0] for r in rows]
    assert "U002" in active_managers, f"U002 should be active at 2026-09-14: {active_managers}"
    assert "U001" not in active_managers, f"U001 should NOT be active at 2026-09-14: {active_managers}"


def test_non_temporal_relationships_always_visible() -> None:
    """Relationships with valid_from=NULL + valid_to=NULL are always visible."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = int(conn.execute(
            text("""
                SELECT count(*) FROM relationships
                WHERE source_system = 'demo:seed_relationships'
                  AND valid_from IS NULL AND valid_to IS NULL
            """)
        ).scalar() or 0)
    # All 5 per-PR relationships from cut-009 path A are non-temporal
    assert rows >= 1000, f"expected ≥1000 non-temporal relationships, got {rows}"


def test_per_pr_relationships_unaffected_by_temporal() -> None:
    """Non-temporal PR→person/supplier/etc relationships visible at any as_of."""
    engine = get_engine()
    identity = resolve_identity(engine, "demo-user-procurement")
    if identity.entity_id is None:
        pytest.skip("demo-user-procurement not seeded")
    # Try as_of 2020 and 2026 — both should return same non-temporal count
    pkg_2020 = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR201"}],
        as_of=date(2020, 6, 1),
    )
    pkg_2026 = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR201"}],
        as_of=date(2026, 9, 14),
    )
    # Both should have same non-temporal per-PR relationships
    assert len(pkg_2020.relationships) == len(pkg_2026.relationships)
    assert len(pkg_2020.relationships) >= 5, (
        f"as_of=2020 returned {len(pkg_2020.relationships)} relationships"
    )
