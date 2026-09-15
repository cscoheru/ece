"""Sprint 6 — /audit/context/{request_id} endpoint (per docs/API.md §8).

Returns trace (context_requests + context_items) for Debugger UI
consumption. Per ADR-004 PermissionScope: only owner can view own trace.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.api.delegation import resolve_user_refs, user_can_access
from ece.audit.trace import get_context_trace
from ece.db import get_engine

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


class AuditTraceItem(BaseModel):
    """One per-item trace entry (per DATA_MODEL §5 context_items)."""

    seq: int
    item_kind: str
    ref: str
    decision: str
    reason: str | None = None
    source: dict[str, Any] = Field(default_factory=dict)


class AuditTraceResponse(BaseModel):
    """Full trace response (per docs/API.md §8)."""

    request_id: str
    user_ref: str
    intent: str
    status: str
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[AuditTraceItem] = Field(default_factory=list)
    latency_ms: int | None = None
    created_at: str


@router.get(
    "/context/{request_id}",
    response_model=AuditTraceResponse,
)
def get_context_audit(
    request_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_delegation_token: str | None = Header(None, alias="X-Delegation-Token"),
) -> AuditTraceResponse:
    """Get audit trace for a context_requests row.

    Per docs/API.md §8: returns request metadata + per-item trace.
    Per ADR-004: only the owner (user_ref) can view their own trace.

    Raises:
        400: missing X-User-Id header
        403: caller is not the owner
        404: request_id not found
    """
    if not resolve_user_refs(x_user_id, x_delegation_token):
        raise HTTPException(
            status_code=400,
            detail={"code": "bad_request", "message": "X-User-Id header or valid X-Delegation-Token required"},
        )

    trace = get_context_trace(get_engine(), request_id)
    if trace is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": f"context request {request_id} not found",
            },
        )

    # Per ADR-004 (extended cut-018b): owner OR delegated user
    if not user_can_access(x_user_id, x_delegation_token, trace["user_ref"]):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": "can only view own context traces",
            },
        )

    return AuditTraceResponse(
        request_id=trace["request_id"],
        user_ref=trace["user_ref"],
        intent=trace["intent"],
        status=trace["status"],
        counts=trace["counts"],
        items=[AuditTraceItem(**item) for item in trace["items"]],
        latency_ms=trace["latency_ms"],
        created_at=trace["created_at"],
    )
