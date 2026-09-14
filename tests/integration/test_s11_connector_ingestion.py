"""R4 S1.1 integration: CSV connector with skip counts lands in ingestion_runs.stats."""
from __future__ import annotations

import csv
from pathlib import Path

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

    try:
        c = CsvConnector(path=Path(tmp_path))
        engine = get_engine()
        before_raw = engine.connect().execute(
            __import__("sqlalchemy").text(
                "SELECT count(*) FROM entities WHERE source_system = :s"
            ),
            {"s": unique_source},
        ).scalar()
        before = before_raw or 0

        stats = run_ingestion(c, engine, connector_type=unique_source)

        after_raw = engine.connect().execute(
            __import__("sqlalchemy").text(
                "SELECT count(*) FROM entities WHERE source_system = :s"
            ),
            {"s": unique_source},
        ).scalar()
        after = after_raw or 0
        assert stats.created == 2
        assert after - before == 2
        # R6: stats.connector must preserve the resource segment
        assert stats.connector == unique_source
    finally:
        os.unlink(tmp_path)
