"""KC-001 — Consulting Knowledge Copilot data models.

Pydantic v2 models for the file-backed consulting catalog. Schema mirrors
the YAML definition in `docs/demo-platform/CONSULTING_CONTEXT_KERNEL_PRD_V2.md`
§4 plus the JSON contract in `docs/demo-platform/CONSULTING_CONTEXT_KERNEL_KC001_TASK.md` §4.

Type enums are deliberately restricted via ``Literal[...]`` so the seed bundle
cannot silently introduce new categories without explicit schema migration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Allowed enum values — keep in sync with Task §4 (Type / Source / Confidence / Review)
# ---------------------------------------------------------------------------

TypeT = Literal[
    "case",
    "methodology",
    "proposal_play",
    "deliverable_template",
    "risk_check",
    "industry_note",
]

SourceOriginT = Literal[
    "founder_case",
    "methodology_note",
    "synthetic_variant",
    "licensed_public",
]

ConfidenceT = Literal["high", "medium", "synthetic"]

ReviewStateT = Literal["approved", "draft"]


# ---------------------------------------------------------------------------
# Core entity: a single knowledge object (case / methodology / play / ...)
# ---------------------------------------------------------------------------


class KnowledgeObject(BaseModel):
    """A single knowledge object in the consulting library.

    Mirrors PRD §4 + Task §4.1 field contract. All list-valued fields are
    stored as JSON arrays (empty list when absent — never None) so SPA
    rendering code can rely on `.length > 0` checks.
    """

    id: str
    type: TypeT
    title: str
    summary: str

    practice: list[str] = Field(default_factory=list)
    engagement_phase: list[str] = Field(default_factory=list)
    client_industry: list[str] = Field(default_factory=list)
    problem_types: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)

    source_origin: SourceOriginT
    confidence: ConfidenceT
    review_state: ReviewStateT


# ---------------------------------------------------------------------------
# API response wrappers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Content-engine merge (OEI-006) — additive only
# ---------------------------------------------------------------------------

# `engine_status` vocabulary (OEI-006 §4 step 2). Chosen so that "the engine
# said no results" (`ok` + empty list) is never confused with "we never asked"
# (`skipped`) or "we could not ask" (`unavailable`):
#
#   ok          — the live engine was queried and answered (results may be empty)
#   unavailable — the engine was selected but is unreachable / errored
#   disabled    — no live engine is selected (ECE_CONTENT_ENGINE is not `onyx`,
#                 i.e. the mock adapter, which returns canned non-customer
#                 documents that must NOT be shown as recalled content)
#   skipped     — no query was issued at all (empty `q`), so the static side
#                 is untouched and we did not touch the engine
EngineMergeStatus = Literal["ok", "unavailable", "disabled", "skipped"]


class EngineItem(BaseModel):
    """One document recalled from the content engine, shaped for a card.

    Deliberately mirrors the *display* fields of `KnowledgeObject` without
    reusing it: engine documents have no `practice` / `methods` / facets and
    must never be mixed into the static catalog's contract. `source` is a
    constant discriminator so the SPA can group/label without guessing.
    """

    engine_doc_id: str = Field(..., description="Engine-side document id (Onyx citation/doc id).")
    title: str
    snippet: str = Field(..., description="Engine-provided snippet, already capped by the adapter.")
    source_type: str = Field(..., description="Engine source kind, e.g. 'user_file'.")
    # Typed `datetime` (NOT `str`) to match `port.EngineDocument.updated_at`
    # exactly. OEI-006 step 4 caught this the hard way: with `str | None` the
    # live Onyx adapter's real `datetime` blew up Pydantic validation and the
    # endpoint 500'd — mock mode never reproduces it because the mock adapter
    # and the schema agreed by accident. Pydantic serialises it to ISO 8601 in
    # JSON, which is what the documented contract shows.
    updated_at: datetime | None = None
    source: Literal["engine"] = "engine"


class LibraryResponse(BaseModel):
    """GET /api/v1/consulting/library response payload.

    `facets` is always the *full-set* facet catalog (not narrowed by the
    current filter) — see plan §8.1 for the UX rationale and §5 for the
    test that guards this invariant.

    OEI-006 adds `engine_items` + `engine_status`. Both are ADDITIVE and
    defaulted, so every pre-existing consumer of the static fields
    (`items`/`total`/`limit`/`offset`/`facets`) keeps its exact behaviour.
    The default `engine_status` is `disabled` — the "we did not merge
    anything" state — so a caller that builds this model directly never
    accidentally advertises live engine results.
    """

    items: list[KnowledgeObject]
    total: int
    limit: int
    offset: int
    facets: dict[str, list[str]]
    engine_items: list[EngineItem] = Field(default_factory=list)
    engine_status: EngineMergeStatus = "disabled"


class FacetsResponse(BaseModel):
    """GET /api/v1/consulting/facets response payload."""

    facets: dict[str, list[str]]
    total: int


# ---------------------------------------------------------------------------
# OEI-007 — document upload + status
# ---------------------------------------------------------------------------


# `status` mirrors the Onyx /api/user/projects/file/statuses lifecycle.
DocumentStatusT = Literal["PROCESSING", "COMPLETED", "FAILED"]


class UploadedDocument(BaseModel):
    """One row of the upload response — what happened to a single file.

    `accepted=True` means the file was uploaded to the engine (status will
    typically be PROCESSING and the caller should poll for completion).
    `accepted=False` means the upload endpoint refused the file *before* it
    ever reached the engine (whitelist / empty / oversize / unknown reason);
    `reason` carries the human-readable explanation.
    """

    name: str = Field(..., description="Original filename at upload time.")
    accepted: bool = Field(..., description="True iff the file reached the engine.")
    document_id: str | None = Field(
        default=None, description="Engine-side document id (UUID); present iff accepted=True."
    )
    status: DocumentStatusT | None = Field(
        default=None, description="Indexing lifecycle state (PROCESSING/COMPLETED/FAILED)."
    )
    chunk_count: int | None = Field(default=None, description="Indexed chunk count.")
    reason: str | None = Field(default=None, description="Rejection reason when accepted=False.")
    suggested_metadata: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Deterministic metadata suggestion (filename+title). Caller overrides.",
    )


class UploadResponse(BaseModel):
    """POST /api/v1/consulting/documents response — one row per submitted file.

    The HTTP status is **always 200** when the endpoint is reachable: per-file
    acceptance lives in `documents[i].accepted` and `documents[i].reason`.
    A request where *every* file is rejected still returns 200 + a `documents[]`
    with `accepted=False` rows — that way the SPA can render individual reasons
    instead of seeing a single 4xx hide everything.

    `static_catalog_size` is a small affordance for the SPA: confirms the static
    side was untouched by the upload, even when zero documents were accepted.
    """

    documents: list[UploadedDocument]
    static_catalog_size: int = Field(
        ..., description="Number of objects in the static seed catalog at upload time."
    )
    metadata_vocabulary_check: str = Field(
        default="ok",
        description="Diagnostic: 'ok' unless metadata validation explicitly dropped a value.",
    )


class DocumentStatusResponse(BaseModel):
    """GET /api/v1/consulting/documents/{document_id} response payload.

    Mirrors the engine's status record so the SPA can render "等待 / 已索引
    (N 块) / 失败 (原因)" without knowing about Onyx-specific fields.
    """

    document_id: str
    name: str
    status: DocumentStatusT
    chunk_count: int | None = None
    project_id: int | None = None
    failure_reason: str | None = None


__all__ = [
    "KnowledgeObject",
    "LibraryResponse",
    "FacetsResponse",
    "EngineItem",
    "EngineMergeStatus",
    "TypeT",
    "SourceOriginT",
    "ConfidenceT",
    "ReviewStateT",
    "DocumentStatusT",
    "UploadedDocument",
    "UploadResponse",
    "DocumentStatusResponse",
]
