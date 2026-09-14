"""S2.1-S2.3 API surface: /permissions/check + /resolve + identity header extraction.

Per ece/TASKS.md S2.2 + S2.3:
- POST /permissions/check: takes (user_ref, object_type, object_ref, classification) -> decision
- POST /resolve: takes (mention, type_hint) -> candidates + resolved flag
- X-User-Id header required for all authenticated endpoints (per S2.4)

Per ADR-004 Permission Before Context Assembly: every authenticated read
goes through PermissionScope (not post-filter; SQL subquery).
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from ece.db import get_engine
from ece.entities.resolver import resolve_mention
from ece.identity.parser import resolve_identity
from ece.permissions.engine import PermissionDecision, check_permission

router = APIRouter(prefix="/api/v1", tags=["identity"])


# ──────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────────────────────


class PermissionCheckRequest(BaseModel):
    user_ref: str = Field(..., description="X-User-Id value")
    object_type: str = Field(..., description="entity | document | etc.")
    object_ref: str = Field(..., description="display_id or similar")
    classification: str = Field(default="department")


class PermissionCheckResponse(BaseModel):
    allowed: bool
    reason: str = ""
    matched_rule: str = ""


class ResolveRequest(BaseModel):
    mention: str = Field(..., description="free-text mention to resolve")
    type_hint: str | None = Field(None, description="optional entity_type filter")


class ResolveCandidate(BaseModel):
    entity: str
    name: str
    source_id: str
    method: str
    confidence: float


class ResolveResponse(BaseModel):
    mention: str
    candidates: list[ResolveCandidate]
    resolved: bool
    chosen: str | None = None
    method: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/permissions/check", response_model=PermissionCheckResponse)
def permissions_check(
    req: PermissionCheckRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> PermissionCheckResponse:
    """POST /permissions/check: verify a user can access an object.

    Accepts user_ref in body OR X-User-Id header (header preferred per ADR-004).
    """
    user_ref = req.user_ref or x_user_id
    if not user_ref:
        raise HTTPException(status_code=400, detail="user_ref or X-User-Id required")

    engine = get_engine()
    identity = resolve_identity(engine, user_ref)
    if identity.entity_id is None:
        # Unknown user -> default deny
        return PermissionCheckResponse(
            allowed=False,
            reason="unknown user (entity not found)",
            matched_rule="default-deny",
        )

    # Load ACL entries for object
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT subject_type, subject_ref, effect, valid_from, valid_to, source_system
                FROM acl_entries
                WHERE object_type = :otype AND object_ref = :oref
            """),
            {"otype": req.object_type, "oref": req.object_ref},
        ).fetchall()
        acl_entries = [
            {
                "subject_type": r[0],
                "subject_ref": r[1],
                "effect": r[2],
                "valid_from": r[3],
                "valid_to": r[4],
                "source_system": r[5],
            }
            for r in rows
        ]

    decision: PermissionDecision = check_permission(
        identity=identity,
        object_type=req.object_type,
        object_ref=req.object_ref,
        classification=req.classification,
        acl_entries=acl_entries,
    )
    return PermissionCheckResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        matched_rule=decision.matched_rule,
    )


@router.post("/resolve", response_model=ResolveResponse)
def resolve(
    req: ResolveRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> ResolveResponse:
    """POST /resolve: free-text mention -> entity candidates.

    Per cut-005 §7.4 ambiguity rule: if multiple candidates match, resolved=false
    (caller must disambiguate; never guess).
    """
    engine = get_engine()
    result = resolve_mention(engine, req.mention, type_hint=req.type_hint)
    return ResolveResponse(
        mention=result.mention,
        candidates=[
            ResolveCandidate(
                entity=c["entity"],
                name=c["name"],
                source_id=c["source_id"],
                method=c["method"].value if hasattr(c["method"], "value") else str(c["method"]),
                confidence=c["confidence"],
            )
            for c in result.candidates
        ],
        resolved=result.resolved,
        chosen=result.chosen,
        method=result.method.value if result.method else None,
    )
