"""R4 S1.1 integration: CSV connector with skip counts lands in ingestion_runs.stats."""
from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import text

from ece.connectors.csv import CsvConnector
from ece.connectors.pipeline import run_ingestion
from ece.db import get_engine


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_csv_connector_normalize_skips_blank_rows(tmp_path: Path) -> None:
    f = tmp_path / "suppliers.csv"
    _write_csv(f, [
        {"id": "T001", "name": "Acme", "entity_type": "supplier"},
        {"id": "", "name": "", "entity_type": ""},   # blank row -> skip
        {"id": "T002", "name": "Globex", "entity_type": "supplier"},
    ])
    c = CsvConnector(path=f)
    rows = c.fetch()
    normalized = [c.normalize(r) for r in rows]
    skipped = sum(1 for n in normalized if n is None)
    assert skipped == 1


def test_run_ingestion_actually_upserts_entities() -> None:
    """R2 acceptance: stats.created matches real entity insertions (not just fetched count).

    Use unique source_system per test run to avoid state pollution
    from prior runs (each invocation would otherwise hit ON CONFLICT and
    stats.created would be 0).

    cut-040R-2 P2 (E1 hermeticity): the unique source_system is required for the
    `created == 2` assertion, but the rows it creates MUST be removed again —
    each leftover run adds two duplicate-name suppliers (R4-Acme / R4-Globex),
    and the E1 resolver treats N equal-confidence candidates as ambiguous
    (`resolved=False`, "never guess"). Before this cleanup the suite degraded
    E1 monotonically: 98.5% → 95.4% after four executions.
    """
    import os
    import tempfile
    import uuid

    unique_source = f"csv:r4-test-{uuid.uuid4().hex[:8]}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.DictWriter(f, fieldnames=["id", "name", "entity_type"])
        writer.writeheader()
        writer.writerow({"id": "RT001", "name": "R4-Acme", "entity_type": "supplier"})
        writer.writerow({"id": "RT002", "name": "R4-Globex", "entity_type": "supplier"})
        tmp_path = f.name

    engine = get_engine()

    def _count() -> int:
        return (
            engine.connect()
            .execute(
                text("SELECT count(*) FROM entities WHERE source_system = :s"),
                {"s": unique_source},
            )
            .scalar()
            or 0
        )

    try:
        c = CsvConnector(path=Path(tmp_path))
        before = _count()

        stats = run_ingestion(c, engine, connector_type=unique_source)

        after = _count()
        assert stats.created == 2
        assert after - before == 2
        # R6: stats.connector must preserve the resource segment
        assert stats.connector == unique_source
    finally:
        # Remove exactly this run's rows (relationships and aliases first —
        # FK constraints would otherwise block the entity delete).
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM relationships WHERE "
                    "src_entity_id IN (SELECT id FROM entities WHERE source_system = :s) "
                    "OR dst_entity_id IN (SELECT id FROM entities WHERE source_system = :s)"
                ),
                {"s": unique_source},
            )
            conn.execute(
                text(
                    "DELETE FROM entity_aliases WHERE entity_id IN "
                    "(SELECT id FROM entities WHERE source_system = :s)"
                ),
                {"s": unique_source},
            )
            conn.execute(
                text("DELETE FROM entities WHERE source_system = :s"),
                {"s": unique_source},
            )
        os.unlink(tmp_path)
        # Self-check: the test must not leave anything behind.
        assert _count() == 0, (
            f"E1 hermeticity violation: {_count()} rows left under {unique_source}"
        )
