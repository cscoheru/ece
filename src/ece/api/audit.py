"""Sprint 6 — /audit/context/{request_id} endpoint (per docs/API.md §8).

Returns trace (context_requests + context_items) for Debugger UI
consumption. Per ADR-004 PermissionScope: only owner can view own trace.

cut-018b extends to multi-user via X-Delegation-Token.
cut-019 extends to multi-tenant via X-Org-Id (when ECE_USER_ORGS configured).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.api.delegation import (
    request_id_can_access,
    resolve_user_refs,
    user_can_access,
)
from ece.api.org import check_org_access
from ece.api.rate_limit import check_rate_limit
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
    org_id: str | None = None


@router.get(
    "/context/{request_id}",
    response_model=AuditTraceResponse,
)
def get_context_audit(
    request_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_delegation_token: str | None = Header(None, alias="X-Delegation-Token"),
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
) -> AuditTraceResponse:
    """Get audit trace for a context_requests row.

    Per docs/API.md §8: returns request metadata + per-item trace.
    Per ADR-004: only the owner (user_ref) can view their own trace.

    cut-018b: extended via X-Delegation-Token (multi-user sharing).
    cut-019: extended via X-Org-Id (multi-tenant cross-org isolation).

    Raises:
        400: missing X-User-Id/X-Delegation-Token, or X-Org-Id in multi-tenant mode
        403: caller is not the owner, or cross-org access (multi-tenant mode)
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

    # Per cut-022 (per-resource scope): token grants specific request_id access
    # independently of ownership / org checks. If granted, skip owner and org checks.
    if not request_id_can_access(x_delegation_token, request_id):
        # Per ADR-004 (extended cut-018b): owner OR delegated user
        if not user_can_access(x_user_id, x_delegation_token, trace["user_ref"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "can only view own context traces",
                },
            )

        # Per cut-019 (multi-tenant): X-Org-Id must match trace.org_id
        # cut-021: token may grant cross-org access via ECE_DELEGATION_ORG_TOKENS
        org_allowed, org_error = check_org_access(
            x_org_id, trace["org_id"], x_delegation_token
        )
        if not org_allowed:
            if org_error == "org_id_required":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "bad_request",
                        "message": "X-Org-Id header required (multi-tenant mode)",
                    },
                )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "cross-org access denied",
                },
            )

    # Per cut-023 (org rate limit): check ECE_ORG_RATE_LIMITS for caller's org
    rate_allowed, rate_error, retry_after = check_rate_limit(x_org_id)
    if not rate_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": "org rate limit exceeded",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
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
        org_id=trace["org_id"],
    )
