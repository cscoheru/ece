"""S3.4 — POST /context endpoint.

Per docs/API.md §1 + ARCHITECTURE §3:
  POST /context assembles a Context Package for a given user + intent + root
  entities. Returns 200 with package body, 400 on missing user, 404 on
  unknown spec/intent (anti-probing: not_found envelope), 500 on internal.

Wired in main.py: `app.include_router(context_router)`.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.context.assembly import assemble_context
from ece.db import get_engine

router = APIRouter(prefix="/api/v1", tags=["context"])


class RootEntity(BaseModel):
    """Root entity reference: {type, id} where id is display_id."""

    type: str = Field(..., description="entity_type (e.g. 'purchase_request')")
    id: str = Field(..., description="display_id (e.g. 'PR001')")


class ContextRequest(BaseModel):
    """POST /context request body (per docs/API.md §1)."""

    user_id: str = Field(
        "",
        description="X-User-Id value (header preferred; body fallback for back-compat)",
    )
    intent: str = Field(..., description="spec intent name (e.g. evaluate_purchase_request)")
    entities: list[RootEntity] = Field(
        default_factory=list,
        description="Root entity refs to assemble context around",
    )
    as_of: date | None = Field(default=None, description="Temporal anchor (None=current)")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Reserved for future (e.g. include_denied)",
    )


@router.post("/context")
def post_context(
    req: ContextRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Assemble Context Package for the given user/intent/entities.

    Per ADR-004 anti-probing: missing resources and forbidden resources both
    return uniform envelope. Caller distinguishes via denied list + insufficient
    flag.

    Raises:
        400: missing X-User-Id (header) AND user_id (body)
        404: spec not found (unknown intent)
        500: internal error (DB failure, etc.)
    """
    user_ref = x_user_id or req.user_id
    if not user_ref or not user_ref.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "bad_request",
                "message": "X-User-Id header or user_id body required",
            },
        )

    engine = get_engine()
    try:
        pkg = assemble_context(
            engine=engine,
            user_ref=user_ref.strip(),
            intent=req.intent,
            entities=[e.model_dump() for e in req.entities],
            as_of=req.as_of,
        )
    except FileNotFoundError as e:
        # Anti-probing: unknown spec → uniform 404
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": str(e)},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "internal", "message": str(e)},
        ) from e

    return pkg.to_dict()
