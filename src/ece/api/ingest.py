"""S1.1 -- POST /api/v1/ingest/runs + GET /api/v1/ingest/runs/{run_id}.

Per docs/API.md 7:
- POST /ingest/runs: {"connector": "csv:suppliers", "params": {}} -> {"run_id": ...}; 同步执行,v0 不做队列
- GET /ingest/runs/{run_id}: 状态与 stats (created/updated/skipped/errors)

v0 connector_type: csv:generic / json:generic / docs:folder
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ece.connectors.pipeline import run_ingestion
from ece.db import get_engine

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    """POST /ingest/runs request body."""

    connector: str = Field(..., description="Connector type, e.g. csv:suppliers / json:prs / docs:folder")
    params: dict[str, Any] = Field(default_factory=dict, description="Connector-specific params (path etc.)")
    batch: str = Field(default="default", description="Batch label for grouping runs in stats")


class IngestResponse(BaseModel):
    """POST /ingest/runs response."""

    run_id: int
    stats: dict[str, Any]


@router.post("/runs", response_model=IngestResponse)
def post_ingest_run(req: IngestRequest) -> IngestResponse:
    """Trigger an ingestion run synchronously.

    Per ece/TASKS.md S1.1: 同步执行,v0 不做队列;stats 写 ingestion_runs.
    """
    connector = _build_connector(req.connector, req.params)
    if connector is None:
        raise HTTPException(status_code=400, detail=f"unknown connector: {req.connector}")

    engine = get_engine()
    stats = run_ingestion(connector, engine, connector_type=req.connector, batch=req.batch)

    # Fetch the inserted row's id (sync; lastvalue or RETURNING)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM ingestion_runs WHERE (stats->>'connector') = :c ORDER BY started_at DESC LIMIT 1"),
            {"c": stats.connector},
        ).first()
    if row is None:
        raise HTTPException(status_code=500, detail="ingestion_runs row not found after insert")
    return IngestResponse(run_id=row[0], stats=stats.to_dict())


@router.get("/runs/{run_id}")
def get_ingest_run(run_id: int) -> dict[str, Any]:
    """GET /ingest/runs/{run_id} -- status + stats."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT connector, status, stats, started_at, finished_at FROM ingestion_runs WHERE id = :id"),
            {"id": run_id},
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="ingestion run not found")
    import json as _json
    stats_obj = row[2]
    if isinstance(stats_obj, str):
        stats_obj = _json.loads(stats_obj)
    return {
        "run_id": run_id,
        "connector": row[0],
        "status": row[1],
        "stats": stats_obj,
        "started_at": row[3].isoformat() if row[3] else None,
        "finished_at": row[4].isoformat() if row[4] else None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Connector registry (per connector_type -> factory)
# ──────────────────────────────────────────────────────────────────────────────

def _build_connector(connector_type: str, params: dict[str, Any]):
    """Build a Connector instance by type. params may include 'path'."""
    from pathlib import Path

    if connector_type.startswith("csv"):
        from ece.connectors.csv import CsvConnector
        path = Path(params.get("path", "data/sample/suppliers.csv"))
        return CsvConnector(path=path)

    if connector_type.startswith("json"):
        from ece.connectors.json import JsonConnector
        path = Path(params.get("path", "data/sample/purchase_requests.json"))
        return JsonConnector(path=path)

    if connector_type.startswith("docs"):
        from ece.connectors.docs import DocsConnector
        folder = Path(params.get("folder", "data/sample/docs/"))
        classification = params.get("classification", "department")
        return DocsConnector(folder=folder, classification=classification)

    return None  # unknown connector type -> 400
