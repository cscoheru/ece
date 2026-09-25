"""KC-001 — FastAPI router for the Consulting Knowledge Copilot.

Three read-only endpoints (KC-001):
  GET /api/v1/consulting/library        — filtered + searched + paginated
  GET /api/v1/consulting/facets         — full-corpus facet catalog
  GET /api/v1/consulting/objects/{id}   — single object detail (404 if absent)

OEI-006 adds engine-recall on top of the static catalog (no change here).

OEI-007 adds two write-path endpoints (additive):
  POST /api/v1/consulting/documents              — multipart upload → engine
  GET  /api/v1/consulting/documents/{id}         — poll indexing status

OEI-008 adds identity threading + the upload `project_id` plumbing stub.
OEI-009 makes the upload `project_id` a real form field (default 1 for
backward compat), generates the *controlled* engine filename on the
write side (`ece-<docref>-<slug>.<ext>`), registers every successful
upload in `engine_documents`, and threads the resolved `Identity`
through to the per-result permission filter on the read side.

The static catalog is the source of truth for facet vocabulary (TASK §2.2);
uploaded documents are routed to the engine with consulting metadata derived
deterministically from filename + title (caller can override per field).

The router deliberately raises HTTP 404 (not 422) on a missing object id
because the SPA uses the status code to render the "not found" empty
state — distinct from "your filter excluded everything", which renders
the regular empty state with status 200 and ``total=0``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.engine import Engine

from ece.connectors.onyx.port import EngineCallerContext, EngineError
from ece.connectors.onyx.selector import get_content_engine
from ece.consulting.engine_merge import merge_engine
from ece.consulting.metadata import (
    check_aggregate_size,
    check_extension,
    check_single_size,
    resolve_metadata,
    suggest_metadata,
)
from ece.consulting.models import (
    DocumentStatusResponse,
    FacetsResponse,
    KnowledgeObject,
    LibraryResponse,
    UploadedDocument,
    UploadResponse,
)
from ece.consulting.registry import (
    compute_controlled_filename,
    register as register_engine_doc,
)
from ece.consulting.service import default_catalog
from ece.db import get_engine as get_sql_engine
from ece.identity.parser import Identity, resolve_identity

router = APIRouter(
    prefix="/api/v1/consulting",
    tags=["consulting"],
)


@router.get("/library", response_model=LibraryResponse)
async def get_library(
    q: str | None = Query(default=None, description="Keyword search over title/summary/methods/problem_types/deliverables."),  # noqa: B008
    type: str | None = Query(default=None, description="Exact type filter."),  # noqa: B008
    practice: list[str] = Query(default_factory=list, description="Any-match practice filter."),  # noqa: B008
    engagement_phase: list[str] = Query(default_factory=list, description="Any-match phase filter."),  # noqa: B008
    client_industry: list[str] = Query(default_factory=list, description="Any-match industry filter."),  # noqa: B008
    problem_type: list[str] = Query(default_factory=list, description="Any-match problem-type filter."),  # noqa: B008
    source_origin: str | None = Query(default=None, description="Exact source_origin filter."),  # noqa: B008
    review_state: str | None = Query(default=None, description="Exact review_state filter."),  # noqa: B008
    sort: str = Query(default="relevance", description="Sort key: relevance (default) or title."),  # noqa: B008
    limit: int = Query(default=24, ge=1, le=100),  # noqa: B008
    offset: int = Query(default=0, ge=0),  # noqa: B008
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> LibraryResponse:
    static = default_catalog().search(
        q=q,
        type=type,
        practice=practice,
        engagement_phase=engagement_phase,
        client_industry=client_industry,
        problem_type=problem_type,
        source_origin=source_origin,
        review_state=review_state,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    # OEI-008: build caller for audit. Read-only anonymous surface — no 401.
    from ece.connectors.onyx.caller import caller_from_request_headers

    caller = caller_from_request_headers(authorization, x_user_id)

    # OEI-009: resolve the principal for the per-result permission filter.
    # Identity comes from credentials only — NEVER from a request body
    # parameter (TASK §1.3 事实 B). Anonymous callers get Identity.anonymous()
    # which the filter then narrows to public-only.
    sql_engine: Engine = get_sql_engine()
    if caller.user_ref:
        identity: Identity | None = resolve_identity(sql_engine, caller.user_ref)
    else:
        identity = Identity.anonymous()

    # OEI-006: the static response is computed FIRST and is never mutated — the
    # engine merge only ever adds the two new fields on top. `model_copy(update=)`
    # (rather than rebuilding the response) is what structurally guarantees the
    # static fields stay byte-identical for existing consumers.
    engine_items, engine_status = await merge_engine(
        q, caller=caller, sql_engine=sql_engine, identity=identity
    )
    return static.model_copy(
        update={"engine_items": engine_items, "engine_status": engine_status}
    )


@router.get("/facets", response_model=FacetsResponse)
def get_facets() -> FacetsResponse:
    return default_catalog().facets()


@router.get("/objects/{object_id}", response_model=KnowledgeObject)
def get_object(object_id: str) -> KnowledgeObject:
    obj = default_catalog().get(object_id)
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail=f"object_id={object_id!r} not found in consulting catalog",
        )
    return obj


# ---------------------------------------------------------------------------
# OEI-007 — upload + status endpoints
# ---------------------------------------------------------------------------


# Default project id for uploads that don't specify one. Existing behaviour
# (before OEI-009) hardcoded this to 1 (the demo project). We keep the
# default for backward compat; tests pass an explicit `project_id` form
# field to direct test uploads to a scratch project (TASK §0 step 0.3).
_DEFAULT_UPLOAD_PROJECT_ID = 1


def _read_upload(file: UploadFile) -> bytes:
    """Read an UploadFile's body in one shot. Caller is responsible for size check."""
    # UploadFile.read() loads the entire file into memory — fine for our limits.
    return file.file.read()


def get_upload_caller(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> EngineCallerContext:
    """FastAPI dependency — resolve the caller for the auth-required write path.

    Pulled out of `upload_documents` (OEI-008 R1) so it can be replaced through
    `app.dependency_overrides[get_upload_caller]`. That is what keeps
    `tests/unit/test_consulting_documents.py` DB-free: those 32 tests inject a
    stub caller instead of letting `caller_from_db_identity` reach for Postgres.

    Anonymous callers raise 403 here, i.e. the dependency — not the endpoint
    body — is the enforcement point.
    """
    from ece.connectors.onyx.caller import caller_from_db_identity
    from ece.db import get_engine

    try:
        return caller_from_db_identity(get_engine(), authorization, x_user_id)
    except EngineError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_documents(
    file: list[UploadFile] = File(..., description="One or more files to ingest."),  # noqa: B008
    title: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    type: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    engagement_phase: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    client_industry: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    problem_types: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    methods: Annotated[list[str] | None, Form()] = None,  # noqa: B008
    project_id: Annotated[int | None, Form()] = None,  # noqa: B008
    caller: EngineCallerContext = Depends(get_upload_caller),  # noqa: B008
) -> UploadResponse:
    """Upload one or more files to the engine for indexing.

    - Each file is independently validated (whitelist + size), independently
      uploaded, and gets its own row in `documents[]`. One bad file does NOT
      block the others.
    - Title and metadata fields are aligned to `file` by index when provided;
      mismatched lengths are tolerated (missing → None).
    - Caller metadata OVERRIDES suggestion (TASK §4 step 3), but values outside
      the seed vocabulary are dropped (with `_dropped` hint in the response).
    - **OEI-009**: `project_id` is now a form field (default 1). Tests pass a
      scratch project id here to avoid polluting the demo project (TASK §0.3).
    - **OEI-009**: the *engine filename* is generated server-side as
      `ece-<docref>-<slug>.<ext>` — see `consulting/registry.py`. The caller's
      original filename is preserved as `original_filename` in the registry
      row, but the engine sees the controlled name. This is what makes the
      read-side `(engine_name, title)` lookup reliable.
    - On upload success, a row is INSERTed into `engine_documents`. The
      registry row is *the* authorization source — without it, the read-side
      filter fail-closes that result (Step 2.2 / A5).

    HTTP status: 200 even if every file is rejected (reasons in `documents[i]`).
    A 4xx only fires for *request-level* errors (no files, total oversize,
    missing or wrong project_id).
    """
    if not file:
        raise HTTPException(
            status_code=422, detail="at least one `file` part is required"
        )

    target_project_id = project_id if project_id is not None else _DEFAULT_UPLOAD_PROJECT_ID
    if target_project_id <= 0:
        raise HTTPException(
            status_code=422,
            detail=f"project_id must be a positive integer, got {project_id!r}",
        )

    # Align optional form arrays to the file list (index-by-index).
    n = len(file)
    titles = (title or []) + [None] * (n - len(title or []))
    types_caller = (type or []) + [None] * (n - len(type or []))
    phases_caller = (engagement_phase or []) + [None] * (n - len(engagement_phase or []))
    industries_caller = (client_industry or []) + [None] * (n - len(client_industry or []))
    probs_caller = (problem_types or []) + [None] * (n - len(problem_types or []))
    methods_caller = (methods or []) + [None] * (n - len(methods or []))

    # Read bytes first (cheap, before any per-file rejection so the size
    # reporting is exact). Empty files and oversize files are handled per-file
    # so multi-file uploads can partial-succeed.
    raw: list[bytes] = []
    for f in file:
        raw.append(_read_upload(f))

    # Aggregate-size guard is request-level (no point continuing if the whole
    # batch is over the limit). Per-file empty/oversize is rejected further down.
    try:
        check_aggregate_size(sum(len(b) for b in raw))
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    engine = get_content_engine()
    sql_engine: Engine = get_sql_engine()
    # OEI-008 §A5: caller is resolved by `get_upload_caller` (FastAPI dependency)
    # and forwarded to the engine for audit. Anonymous callers are refused at
    # dependency resolution (403), not here. Tests override the dependency with
    # a stub so they don't need a real DB.

    results: list[UploadedDocument] = []
    vocab_dropped_any = False

    for i, f in enumerate(file):
        original_name = f.filename or f"file-{i}"
        # Whitelist: per-file rejection (the SPA wants partial success on multi-upload).
        try:
            check_extension(original_name)
        except ValueError as exc:
            results.append(
                UploadedDocument(
                    name=original_name,
                    accepted=False,
                    reason=str(exc),
                    suggested_metadata=suggest_metadata(original_name, titles[i]),
                )
            )
            continue

        # Per-file size: 0-byte + single-file-oversize → per-file rejection.
        body = raw[i]
        try:
            check_single_size(len(body))
        except ValueError as exc:
            results.append(
                UploadedDocument(
                    name=original_name,
                    accepted=False,
                    reason=str(exc),
                    suggested_metadata=suggest_metadata(original_name, titles[i]),
                )
            )
            continue

        # OEI-009: derive the controlled engine filename server-side. The
        # caller's original name is *only* kept in `original_filename` /
        # `name` (response) / `title` (suggested metadata). The engine sees
        # the controlled name, so the read-side `(engine_name, title)`
        # lookup is reliable.
        try:
            controlled_filename = compute_controlled_filename(
                caller.user_ref, original_name
            )
        except ValueError as exc:
            results.append(
                UploadedDocument(
                    name=original_name,
                    accepted=False,
                    reason=f"filename rejected: {exc}",
                    suggested_metadata=suggest_metadata(original_name, titles[i]),
                )
            )
            continue

        suggested = suggest_metadata(original_name, titles[i])
        caller_meta = {
            "type": types_caller[i],
            "engagement_phase": phases_caller[i],
            "client_industry": industries_caller[i],
            "problem_types": probs_caller[i],
            "methods": methods_caller[i],
        }
        merged = resolve_metadata(caller_meta, suggested)
        if merged.get("_dropped"):
            vocab_dropped_any = True

        try:
            status_record = await engine.upload_document(
                filename=controlled_filename,  # OEI-009: controlled name, not original
                content=body,
                project_id=target_project_id,
                title=titles[i] or controlled_filename,
                metadata=merged,
                caller=caller,
            )
        except EngineError as exc:
            results.append(
                UploadedDocument(
                    name=original_name,
                    accepted=False,
                    reason=f"engine rejected: {exc}",
                    suggested_metadata=suggested,
                )
            )
            continue

        # OEI-009 — register the row in `engine_documents`. Default
        # classification is `public` (per Step 1.4 / A3: 3 demo docs are
        # public; new uploads inherit public until an admin reclassifies).
        # Identity comes from the credentials — `caller.user_ref` is
        # guaranteed non-None because the `get_upload_caller` dependency
        # rejects anonymous callers with 403.
        try:
            registry_id = register_engine_doc(
                sql_engine,
                engine_name=engine.engine_name,
                engine_project_id=target_project_id,
                engine_filename=controlled_filename,
                original_filename=original_name,
                engine_document_id=status_record.document_id,
                title=titles[i],
                classification="public",
                uploaded_by=caller.user_ref or "unknown",
                department=caller.department or "",
                org_id=caller.org_id,
            )
        except Exception as exc:  # noqa: BLE001 — registration failure is per-file
            # We don't fail the upload (the engine accepted it) but we
            # surface the registration failure to the response so the SPA
            # can warn the user. Without a registry row, the read-side
            # filter will fail-closed on this doc — that's the safest
            # default; we just have to be explicit about it.
            results.append(
                UploadedDocument(
                    name=original_name,
                    accepted=True,
                    document_id=status_record.document_id,
                    status=status_record.status,
                    chunk_count=status_record.chunk_count,
                    suggested_metadata=suggested,
                )
            )
            results[-1].reason = f"engine accepted but registry insert failed: {exc}"
            # Continue — the next file may still register fine.
            continue

        results.append(
            UploadedDocument(
                name=original_name,
                accepted=True,
                document_id=status_record.document_id,
                status=status_record.status,
                chunk_count=status_record.chunk_count,
                suggested_metadata=suggested,
            )
        )

    return UploadResponse(
        documents=results,
        static_catalog_size=len(default_catalog().objects),
        metadata_vocabulary_check="dropped" if vocab_dropped_any else "ok",
    )


@router.get("/documents/{document_id}", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: str,
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> DocumentStatusResponse:
    """Poll the indexing status of a document uploaded via POST /documents.

    The engine-side id is the value returned in `documents[i].document_id`.
    Translates the engine's `PROCESSING / COMPLETED / FAILED` lifecycle into
    the same vocabulary the upload response used.

    OEI-008 — read-only anonymous surface: we resolve the caller via
    `caller_from_request_headers` and forward it to the engine for audit.
    No 401 here — anyone can poll status for any document they have the id
    for (the id itself is the bearer). The audit row records who asked.

    Errors:
      404 — engine reports "not found" for this id (id unknown / expired)
      502 — engine unreachable (proxies the underlying EngineError)
    """
    from ece.connectors.onyx.caller import caller_from_request_headers
    caller = caller_from_request_headers(authorization, x_user_id)

    engine = get_content_engine()
    try:
        rec = await engine.document_status(document_id, caller=caller)
    except EngineError as exc:
        msg = str(exc)
        # "not found" is the only engine error that maps to 404; everything else
        # is "engine is unhealthy" and deserves a 502 so the SPA can show a banner.
        if "not found" in msg:
            raise HTTPException(
                status_code=404,
                detail=f"document_id={document_id!r} not found",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"engine status unavailable: {msg}",
        ) from exc

    return DocumentStatusResponse(
        document_id=rec.document_id,
        name=rec.name,
        status=rec.status,
        chunk_count=rec.chunk_count,
        project_id=rec.project_id,
        failure_reason=rec.failure_reason,
    )


__all__ = ["router"]