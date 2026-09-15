"""Sprint 6 — Audit trace query helpers (per DATA_MODEL §5).

Functions to read context_requests + context_items tables for the
/audit/context/{request_id} endpoint and Debugger UI consumption.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def get_context_trace(
    engine: Engine, request_id: str
) -> dict[str, Any] | None:
    """Fetch context_request + context_items for a request_id.

    Returns dict with request metadata + items list, or None if not found.
    """
    with engine.connect() as conn:
        req_row = conn.execute(
            text("""
                SELECT request_id, user_ref, intent, status, counts,
                       latency_ms, created_at
                FROM context_requests WHERE request_id = :r
            """),
            {"r": request_id},
        ).first()
        if req_row is None:
            return None

        item_rows = conn.execute(
            text("""
                SELECT seq, item_kind, ref, decision, reason, source
                FROM context_items
                WHERE request_id = :r
                ORDER BY seq
            """),
            {"r": request_id},
        ).fetchall()

    counts = req_row[4] if isinstance(req_row[4], dict) else {}
    created_at: datetime | None = req_row[6]
    return {
        "request_id": str(req_row[0]),
        "user_ref": req_row[1],
        "intent": req_row[2],
        "status": req_row[3],
        "counts": counts,
        "latency_ms": req_row[5],
        "created_at": created_at.isoformat() if created_at else "",
        "items": [
            {
                "seq": r[0],
                "item_kind": r[1],
                "ref": r[2],
                "decision": r[3],
                "reason": r[4],
                "source": r[5] if isinstance(r[5], dict) else {},
            }
            for r in item_rows
        ],
    }
