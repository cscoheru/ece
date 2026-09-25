"""OEI-010 — persistent memory API (write + compliance surface).

Three endpoints, all `/api/v1/memory`:

    POST   /api/v1/memory                 create (idempotent)
    GET    /api/v1/memory                 list what the caller may see
    DELETE /api/v1/memory/{memory_id}     soft-delete one
    DELETE /api/v1/memory?scope=user|org  soft-delete the caller's own set

Two independent gates on every write
------------------------------------
1. **Subject gate** (this module). The principal comes from the *credential*
   (`Authorization: Bearer <jwt>` per cut-027/cut-036, else `X-User-Id`); it is
   never taken from the body. The body's `owner_ref` is then **checked against
   the credential** — a mismatch is REJECTED, never silently rewritten. That is
   the ADR-004 rule this cut inherits from OEI-009:
   "subject comes from the credential, never from the caller".
2. **Authorization gate** (`check_permission`). The write is judged against a
   *scope object* — `object_type='memory_scope'`, `object_ref` = `user:<ref>`
   or `org:<ref>`, `classification='restricted'` (-> default deny). Only an
   explicit `effect='allow'` ACL row passes. **Policy is data**: to change who
   may write org memory, change ACL rows, not this file
   (see `onyx-lab/OEI-010/workspace/design-memory-policy.md` §4).

Both are required. Gate 1 alone would let any org member write anyone's
user-level memory by naming them; gate 2 alone would let an `org_admin` write
another person's user-level memory (the role row is on the *org* scope object,
so in practice both fire, but the two questions — "is this your own scope?" and
"are you allowed to write this scope?" — stay separate by construction).

Visibility of a created memory
------------------------------
The create transaction also inserts the ACL row that makes the memory legible:
`(subject_type='user'|'org', subject_ref=<owner_ref>, object_type='memory',
object_ref='memory:<id>', effect='allow')`. Nothing else can make it visible —
`classification` is `restricted` (default deny), so "no ACL row" means "nobody
can read it", not "everybody can".

Deletion is SOFT (`deleted_at`). Compliance requires 可追溯: `context_items`
rows already reference `memory:<id>`, and a physical delete would leave those
traces pointing at nothing.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from ece.auth.jwt import (
    is_header_auth_fallback_allowed,
    is_jwt_mode_enabled,
    resolve_caller_user_ref,
)
from ece.context.memory import ACL_OBJECT_TYPE, object_ref_for
from ece.db import get_engine
from ece.identity.parser import resolve_identity
from ece.permissions.engine import check_permission

router = APIRouter(prefix="/api/v1", tags=["memory"])

#: `object_type` of the ACL rows that decide "may this caller write this scope".
WRITE_SCOPE_OBJECT_TYPE = "memory_scope"

#: `source` stamped on every API-created memory (vs. a future seed/import path).
SOURCE_EXPLICIT_API = "explicit:api"

#: `classification` for every memory in this cut. `restricted` -> default-deny
#: in `DEFAULT_CLASSIFICATION_MATRIX`, which is what makes visibility depend
#: entirely on the explicit ACL row written alongside the memory.
MEMORY_CLASSIFICATION = "restricted"

#: `source_system` tag on ACL rows this module writes (its own audit trail, and
#: the precise predicate for any future scoped cleanup — never a LIKE sweep).
ACL_SOURCE_CREATE = "memory:create"


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────


class MemoryCreateRequest(BaseModel):
    """POST body (TASK §5 步骤 4.2).

    No `classification` field, deliberately: the classification vocabulary is
    not a caller choice in this cut — every memory is `restricted` and
    visibility comes from the ACL row. Exposing it would let a caller author a
    `public` memory, i.e. self-authorize.
    """

    scope: Literal["user", "org"]
    owner_ref: str = Field(
        ..., min_length=1, description="user scope -> user_ref; org scope -> org_id"
    )
    statement: str = Field(..., min_length=1, description="the remembered text")
    confidence: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = Field(
        default=None, description="NULL/omitted = never expires"
    )
    source_ref: str | None = Field(default=None, description="optional external ref")


class MemoryOut(BaseModel):
    """Serialised memory row (the compliance view, not the injected shape)."""

    id: int
    ref: str
    scope: str
    owner_ref: str
    statement: str
    classification: str
    source: str
    source_ref: str | None = None
    confidence: float | None = None
    created_at: str
    updated_at: str
    expires_at: str | None = None
    deleted_at: str | None = None


class MemoryCreateResponse(BaseModel):
    """`created=false` means "this exact memory already existed, here it is"."""

    created: bool
    memory: MemoryOut


class MemoryListResponse(BaseModel):
    memories: list[MemoryOut]
    include_inactive: bool
    count: int


class MemoryDeleteResponse(BaseModel):
    deleted: list[int]
    deleted_count: int
    scope: str
    already_deleted: list[int] = Field(default_factory=list)


class SingleMemoryDeleteResponse(BaseModel):
    memory: MemoryOut
    already_deleted: bool


_ROW_COLUMNS = (
    "id, scope, owner_ref, statement, classification, source, source_ref, "
    "confidence, created_at, updated_at, expires_at, deleted_at"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_caller(
    authorization: str | None, x_user_id: str | None, x_delegation_token: str | None = None
) -> str:
    """Principal from the credential only (never from the body).

    Mirrors `api/audit.py`: JWT mode on + no valid token -> 401 (strict), so the
    legacy header cannot be used to impersonate once JWT is configured.
    """
    resolved = resolve_caller_user_ref(authorization, x_user_id)
    if resolved:
        return resolved
    if is_jwt_mode_enabled() and not is_header_auth_fallback_allowed():
        raise HTTPException(
            status_code=401,
            detail={
                "code": "unauthorized",
                "message": "JWT Bearer token required",
            },
            headers={"WWW-Authenticate": 'Bearer realm="ece"'},
        )
    raise HTTPException(
        status_code=400,
        detail={
            "code": "bad_request",
            "message": "X-User-Id header or Authorization: Bearer <jwt> required",
        },
    )


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def _row_to_out(row: Any) -> MemoryOut:
    columns = [c.strip() for c in _ROW_COLUMNS.split(",")]
    data = dict(zip(columns, row, strict=True))
    confidence = data.get("confidence")
    return MemoryOut(
        id=int(data["id"]),
        ref=object_ref_for(data["id"]),
        scope=str(data["scope"]),
        owner_ref=str(data["owner_ref"]),
        statement=str(data["statement"]),
        classification=str(data["classification"]),
        source=str(data["source"]),
        source_ref=data.get("source_ref"),
        confidence=float(confidence) if confidence is not None else None,
        created_at=_iso(data.get("created_at")) or "",
        updated_at=_iso(data.get("updated_at")) or "",
        expires_at=_iso(data.get("expires_at")),
        deleted_at=_iso(data.get("deleted_at")),
    )


def _load_scope_acl(engine: Any, object_ref: str) -> list[dict[str, Any]]:
    """ACL rows for one `memory_scope` object, with real `valid_from`/`valid_to`.

    Uses the same loader shape as `api/identity.py` (the object type is a real
    query predicate, unlike `assembly._load_acl_for`'s hardcoded `'entity'`),
    so the OEI-009 time-box stays live on this path too.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT subject_type, subject_ref, effect,
                       valid_from, valid_to, source_system
                FROM acl_entries
                WHERE object_type = :otype AND object_ref = :oref
            """),
            {"otype": WRITE_SCOPE_OBJECT_TYPE, "oref": object_ref},
        ).fetchall()
    return [
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


def _scope_object_ref(scope: str, owner_ref: str) -> str:
    """The write-permission object for a scope: `user:<ref>` / `org:<ref>`."""
    return f"{scope}:{owner_ref}"


def _authorize_write(identity: Any, scope: str, owner_ref: str, engine: Any) -> None:
    """Gate 2. Raises 403 unless an explicit allow row covers this scope object."""
    object_ref = _scope_object_ref(scope, owner_ref)
    decision = check_permission(
        identity=identity,
        object_type=WRITE_SCOPE_OBJECT_TYPE,
        object_ref=object_ref,
        classification=MEMORY_CLASSIFICATION,
        acl_entries=_load_scope_acl(engine, object_ref),
        engine=engine,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "permission_denied",
                "message": f"not authorized to write {scope} memory for {owner_ref!r}",
                # The matched rule is safe to expose (it is our own policy
                # vocabulary), and it makes the 403 actionable for an operator.
                "matched_rule": decision.matched_rule,
            },
        )


def _check_owner_matches_credential(
    identity: Any, scope: str, owner_ref: str
) -> None:
    """Gate 1. The body may not name a principal the credential does not own.

    A mismatch is REJECTED (403), never silently rewritten to the caller — a
    silent rewrite would hide a caller bug and, worse, make "who asked for
    this" unrecoverable from the request alone.
    """
    if scope == "user":
        if owner_ref != identity.user_ref:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "permission_denied",
                    "message": (
                        "owner_ref for a user-scope memory must equal the "
                        "authenticated caller"
                    ),
                },
            )
        return

    # scope == "org"
    if not identity.org_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "permission_denied",
                "message": (
                    "caller has no org (entities.attributes.org_id is unset) — "
                    "cannot write org-scope memory"
                ),
            },
        )
    if owner_ref != identity.org_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "permission_denied",
                "message": (
                    "owner_ref for an org-scope memory must equal the caller's "
                    "own org"
                ),
            },
        )


def _normalize_expires_at(value: datetime | None) -> datetime | None:
    """Naive input is read as UTC.

    `expires_at` is a `timestamptz`; letting a naive value fall through to the
    server session zone would make the same request expire at different
    instants depending on where the process runs.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# ─────────────────────────────────────────────────────────────────────────────
# POST — create (idempotent)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/memory", response_model=MemoryCreateResponse)
def post_memory(
    req: MemoryCreateRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> MemoryCreateResponse:
    """Create a memory. Idempotent on `(scope, owner_ref, statement)`.

    Raises:
        400: no credential resolvable
        401: JWT mode on and no valid Bearer token
        403: owner_ref does not match the credential, or the caller has no write
             permission on the scope object
    """
    user_ref = _resolve_caller(authorization, x_user_id)
    engine = get_engine()
    identity = resolve_identity(engine, user_ref)

    # Gate 1 then gate 2: cheapest/most-specific first, so a body that lies
    # about the principal is rejected before any policy lookup happens.
    _check_owner_matches_credential(identity, req.scope, req.owner_ref)
    _authorize_write(identity, req.scope, req.owner_ref, engine)

    expires_at = _normalize_expires_at(req.expires_at)

    with engine.begin() as conn:
        inserted = conn.execute(
            text(f"""
                INSERT INTO memories
                    (scope, owner_ref, statement, classification, source,
                     source_ref, confidence, expires_at)
                VALUES
                    (:scope, :owner_ref, :statement, :classification, :source,
                     :source_ref, :confidence, :expires_at)
                ON CONFLICT ON CONSTRAINT uq_memories_scope_owner_ref_statement
                DO NOTHING
                RETURNING {_ROW_COLUMNS}
            """),
            {
                "scope": req.scope,
                "owner_ref": req.owner_ref,
                "statement": req.statement,
                "classification": MEMORY_CLASSIFICATION,
                "source": SOURCE_EXPLICIT_API,
                "source_ref": req.source_ref,
                "confidence": req.confidence,
                "expires_at": expires_at,
            },
        ).first()

        created = inserted is not None
        if created:
            memory_id = int(inserted[0])
            row = inserted
            # The ACL row that makes it legible — same transaction, so a memory
            # can never exist in a state where its visibility is undefined.
            conn.execute(
                text("""
                    INSERT INTO acl_entries
                        (subject_type, subject_ref, object_type, object_ref,
                         effect, source_system, note)
                    VALUES
                        (:subject_type, :subject_ref, :object_type, :object_ref,
                         'allow', :source_system, :note)
                """),
                {
                    "subject_type": req.scope,
                    "subject_ref": req.owner_ref,
                    "object_type": ACL_OBJECT_TYPE,
                    "object_ref": object_ref_for(memory_id),
                    "source_system": ACL_SOURCE_CREATE,
                    "note": f"{req.scope}-scope memory auto-grant on create",
                },
            )
        else:
            # Existing row: return it unchanged (idempotent create, TASK §5
            # 步骤 4.3). We do NOT refresh updated_at — "already exists" must be
            # a no-op, otherwise the flag would be the only difference and the
            # row would still mutate.
            row = conn.execute(
                text(f"""
                    SELECT {_ROW_COLUMNS} FROM memories
                    WHERE scope = :scope AND owner_ref = :owner_ref
                      AND statement = :statement
                """),
                {
                    "scope": req.scope,
                    "owner_ref": req.owner_ref,
                    "statement": req.statement,
                },
            ).first()

    if row is None:
        # Unreachable: either we inserted, or the conflicting row must be
        # readable. Fail loudly rather than returning a half-built response.
        raise HTTPException(
            status_code=500,
            detail={"code": "internal", "message": "memory row vanished mid-request"},
        )

    return MemoryCreateResponse(created=created, memory=_row_to_out(row))


# ─────────────────────────────────────────────────────────────────────────────
# GET — list
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/memory", response_model=MemoryListResponse)
def list_memory(
    include_inactive: bool = Query(
        False,
        description="also return the caller's own soft-deleted / expired memories",
    ),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> MemoryListResponse:
    """List memories the caller may see (same authorization as injection).

    Default: live, unexpired, in the caller's own scope — user rows they own
    plus org rows owned by their org — each individually authorized.
    `include_inactive=true` widens *only* the activity guard, so the caller can
    see their own tombstoned rows; authorization is unchanged, so this can never
    surface someone else's memory.
    """
    user_ref = _resolve_caller(authorization, x_user_id)
    engine = get_engine()
    identity = resolve_identity(engine, user_ref)

    activity_guard = "" if include_inactive else """
          AND deleted_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
    """

    stmt = text(f"""
        SELECT {_ROW_COLUMNS}
        FROM memories
        WHERE (
                (scope = 'user' AND owner_ref = :user_ref)
             OR (CAST(:org_id AS text) IS NOT NULL
                 AND scope = 'org' AND owner_ref = :org_id)
              )
        {activity_guard}
        ORDER BY (scope = 'org') DESC, created_at DESC, id DESC
    """)
    with engine.connect() as conn:
        raw = conn.execute(
            stmt, {"user_ref": user_ref, "org_id": identity.org_id}
        ).fetchall()

    # Per-row authorization, reusing the exact loader the read step uses so the
    # list and the injection can never disagree about visibility.
    from ece.context.memory import load_acl_for_memory  # noqa: PLC0415

    columns = [c.strip() for c in _ROW_COLUMNS.split(",")]
    candidates = [dict(zip(columns, r, strict=True)) for r in raw]
    acl_by_ref = load_acl_for_memory(
        engine, [object_ref_for(row["id"]) for row in candidates]
    )

    visible: list[MemoryOut] = []
    for row in candidates:
        decision = check_permission(
            identity=identity,
            object_type=ACL_OBJECT_TYPE,
            object_ref=object_ref_for(row["id"]),
            classification=str(row["classification"] or MEMORY_CLASSIFICATION),
            acl_entries=list(acl_by_ref.get(object_ref_for(row["id"]), [])),
            now=datetime.now(tz=UTC),
        )
        if decision.allowed:
            visible.append(
                _row_to_out(tuple(row[c] for c in columns))
            )

    return MemoryListResponse(
        memories=visible, include_inactive=include_inactive, count=len(visible)
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE — compliance surface
# ─────────────────────────────────────────────────────────────────────────────


@router.delete("/memory/{memory_id}", response_model=SingleMemoryDeleteResponse)
def delete_memory(
    memory_id: int,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> SingleMemoryDeleteResponse:
    """Soft-delete one memory. Idempotent.

    Deletion rights (TASK §5 步骤 7.2):
      - `user` scope -> the owner (nobody else, not even `org_admin`).
      - `org`  scope -> requires the §3.3 write permission on the org scope
        object (candidate A: `org_admin`).

    Raises: 400 (no credential) / 401 (JWT strict) / 403 (not entitled) /
            404 (no such memory).
    """
    user_ref = _resolve_caller(authorization, x_user_id)
    engine = get_engine()
    identity = resolve_identity(engine, user_ref)

    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {_ROW_COLUMNS} FROM memories WHERE id = :id"),
            {"id": memory_id},
        ).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"memory {memory_id} not found"},
        )

    columns = [c.strip() for c in _ROW_COLUMNS.split(",")]
    data = dict(zip(columns, row, strict=True))

    if data["scope"] == "user":
        if data["owner_ref"] != identity.user_ref:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "permission_denied",
                    "message": "can only delete own user-scope memories",
                },
            )
    else:
        _authorize_write(identity, "org", str(data["owner_ref"]), engine)

    already_deleted = data.get("deleted_at") is not None
    if not already_deleted:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE memories
                    SET deleted_at = now(), updated_at = now()
                    WHERE id = :id AND deleted_at IS NULL
                """),
                {"id": memory_id},
            )
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {_ROW_COLUMNS} FROM memories WHERE id = :id"),
                {"id": memory_id},
            ).first()

    return SingleMemoryDeleteResponse(
        memory=_row_to_out(row), already_deleted=already_deleted
    )


@router.delete("/memory", response_model=MemoryDeleteResponse)
def delete_memory_bulk(
    scope: Literal["user", "org"] = Query(
        ..., description="which of the caller's own scopes to purge"
    ),
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> MemoryDeleteResponse:
    """Soft-delete the caller's whole memory set for one scope.

    `scope=user` -> the caller's own user-scope rows (ownership rule).
    `scope=org`  -> the caller's org's org-scope rows, which requires the org
                    write permission; a caller without it gets 403 (the
                    negative case A9 asks for).

    Raises: 400 (no credential) / 401 (JWT strict) / 403 (org without write
            permission, or no org at all).
    """
    user_ref = _resolve_caller(authorization, x_user_id)
    engine = get_engine()
    identity = resolve_identity(engine, user_ref)

    if scope == "user":
        owner_ref = identity.user_ref
    else:
        if not identity.org_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "permission_denied",
                    "message": "caller has no org — cannot purge org-scope memory",
                },
            )
        owner_ref = identity.org_id
        _authorize_write(identity, "org", owner_ref, engine)

    with engine.begin() as conn:
        live = conn.execute(
            text("""
                SELECT id FROM memories
                WHERE scope = :scope AND owner_ref = :owner_ref
                  AND deleted_at IS NULL
                ORDER BY id
            """),
            {"scope": scope, "owner_ref": owner_ref},
        ).fetchall()
        ids = [int(r[0]) for r in live]
        if ids:
            conn.execute(
                text("""
                    UPDATE memories
                    SET deleted_at = now(), updated_at = now()
                    WHERE id = ANY(:ids)
                """),
                {"ids": ids},
            )

    return MemoryDeleteResponse(
        deleted=ids, deleted_count=len(ids), scope=scope, already_deleted=[]
    )
