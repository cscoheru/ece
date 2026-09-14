"""S1.1 — Ingestion pipeline.

Drives Connector lifecycle (connect → fetch → normalize) and writes to DB.
Tracks stats (created / skipped / errors) — written to ingestion_runs table.

Per ece/TASKS.md S1.1:
- Happy path + 脏数据 skip 计数
- 不中断整批
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from ece.connectors import Connector


@dataclass
class IngestionStats:
    """Per-run statistics, persisted as JSON in ingestion_runs.stats."""

    connector: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector": self.connector,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def run_ingestion(connector: Connector, engine, batch: str = "default") -> IngestionStats:
    """Drive connector + persist ingestion_runs row + stats.

    engine: SQLAlchemy Engine (e.g. create_engine("postgresql+psycopg://...")).
    batch: batch label stored in ingestion_runs.stats for grouping.
    """
    stats = IngestionStats(connector=connector.connector_type)

    # Connect
    try:
        connector.connect()
    except Exception as e:
        stats.errors.append({"phase": "connect", "error": str(e)})
        stats.finished_at = datetime.now(UTC)
        _persist_run(engine, batch, stats)
        return stats

    # Fetch + normalize
    try:
        raw_records = connector.fetch()
    except Exception as e:
        stats.errors.append({"phase": "fetch", "error": str(e)})
        stats.finished_at = datetime.now(UTC)
        _persist_run(engine, batch, stats)
        return stats

    normalized = []
    for idx, raw in enumerate(raw_records):
        try:
            norm = connector.normalize(raw)
        except Exception as e:
            stats.skipped += 1
            stats.errors.append({"phase": "normalize", "index": idx, "error": str(e)})
            continue
        if norm is None:
            stats.skipped += 1
            continue
        normalized.append(norm)

    # Sync — for now record the run; per-entity writes handled by S1.2 pipeline
    stats.created = len(normalized)
    stats.finished_at = datetime.now(UTC)
    _persist_run(engine, batch, stats)

    connector.close() if hasattr(connector, "close") else None
    return stats


def _persist_run(engine, batch: str, stats: IngestionStats) -> None:
    """Insert ingestion_runs row."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO ingestion_runs
                    (connector, status, stats, started_at, finished_at)
                VALUES (:connector, :status, :stats::jsonb, :started_at, :finished_at)
            """),
            {
                "connector": stats.connector,
                "status": "done" if not stats.errors else "done_with_errors",
                "stats": __import__("json").dumps(stats.to_dict()),
                "started_at": stats.started_at,
                "finished_at": stats.finished_at,
            },
        )
