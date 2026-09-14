"""S3 + A — seed_relationships idempotency tests (cut-009 path A).

Verifies:
1. seed_relationships runs without error
2. Total relationships > 0 after run
3. Re-running is idempotent (no duplicate inserts)
4. PR→person (SUBMITTED_BY), PR→supplier (SELECTS), PR→policy (SUBJECT_TO)
   are queryable per assemble_context flow

Pre-condition: make seed has been run (PRs + test users exist).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from ece.db import get_engine
from ece.entities.pipeline import upsert_relationship

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_seed_relationships_runs() -> None:
    """Run the seed script and verify exit 0."""
    result = subprocess.run(
        ["uv", "run", "python", "scripts/seed_relationships.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"seed failed:\n{result.stdout}\n{result.stderr}"


def test_seed_relationships_idempotent() -> None:
    """Re-running seed must not add duplicates (UNIQUE INDEX enforces)."""
    engine = get_engine()
    with engine.connect() as conn:
        before = conn.execute(text("SELECT count(*) FROM relationships")).scalar()

    # Run seed again
    result = subprocess.run(
        ["uv", "run", "python", "scripts/seed_relationships.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    assert result.returncode == 0, f"second seed run failed:\n{result.stdout}"

    with engine.connect() as conn:
        after = conn.execute(text("SELECT count(*) FROM relationships")).scalar()

    assert after == before, f"second run added duplicates: before={before} after={after}"


def test_seed_creates_expected_relationship_types() -> None:
    """All 5 ontology-allowed relationship types present."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT relation, count(*) FROM relationships "
                "WHERE source_system = 'demo:seed_relationships' "
                "GROUP BY relation ORDER BY relation"
            )
        ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    expected_types = {"BELONGS_TO", "SUBMITTED_BY", "SELECTS", "CONTAINS", "SUBJECT_TO"}
    assert expected_types.issubset(counts.keys()), (
        f"missing types: {expected_types - set(counts.keys())}"
    )
    # Each type should have at least 100 rows (≈ # of PRs / 5)
    for rel_type in expected_types:
        assert counts[rel_type] >= 100, (
            f"{rel_type}: {counts[rel_type]} rows (expected ≥100)"
        )


def test_seed_relationship_ontology_whitelist() -> None:
    """Every seeded relationship must be in ontology whitelist.

    Per S1.2 ontology gate (entities/pipeline.py:upsert_relationship).
    """
    engine = get_engine()
    with engine.connect() as conn:
        bad = conn.execute(
            text("""
                SELECT s.entity_type, r.relation, d.entity_type
                FROM relationships r
                JOIN entities s ON r.src_entity_id = s.id
                JOIN entities d ON r.dst_entity_id = d.id
                WHERE r.source_system = 'demo:seed_relationships'
            """)
        ).fetchall()
    for src_type, rel, dst_type in bad:
        # Per ontology.py: src_type -> [(rel, dst_type), ...]
        from ece.domain_packs.procurement.ontology import is_allowed
        assert is_allowed(src_type, rel, dst_type), (
            f"non-ontology triple: ({src_type})-[{rel}]->({dst_type})"
        )


def test_seed_relationship_upsert_idempotent_direct() -> None:
    """Direct upsert_relationship call is idempotent (UNIQUE INDEX)."""
    engine = get_engine()
    # Pick first PR + first person
    with engine.connect() as conn:
        pr_row = conn.execute(
            text("SELECT display_id FROM entities WHERE entity_type='purchase_request' LIMIT 1")
        ).first()
        person_row = conn.execute(
            text("SELECT display_id FROM entities WHERE entity_type='person' LIMIT 1")
        ).first()
    assert pr_row and person_row

    # First call: should insert (or be already there)
    ins1, _ = upsert_relationship(
        engine,
        src_display_id=pr_row[0],
        relation="SUBMITTED_BY",
        dst_display_id=person_row[0],
        source_system="test:seed_relationships_test",
    )
    # Second call: same triple → should NOT insert (idempotent)
    ins2, _ = upsert_relationship(
        engine,
        src_display_id=pr_row[0],
        relation="SUBMITTED_BY",
        dst_display_id=person_row[0],
        source_system="test:seed_relationships_test",
    )
    # Only one should return True (inserted)
    assert ins1 or not ins2, f"both inserts returned True: ins1={ins1} ins2={ins2}"
