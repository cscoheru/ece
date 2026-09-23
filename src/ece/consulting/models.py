"""KC-001 — Consulting Knowledge Copilot data models.

Pydantic v2 models for the file-backed consulting catalog. Schema mirrors
the YAML definition in `docs/demo-platform/CONSULTING_CONTEXT_KERNEL_PRD_V2.md`
§4 plus the JSON contract in `docs/demo-platform/CONSULTING_CONTEXT_KERNEL_KC001_TASK.md` §4.

Type enums are deliberately restricted via ``Literal[...]`` so the seed bundle
cannot silently introduce new categories without explicit schema migration.
"""
from __future__ import annotations

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


class LibraryResponse(BaseModel):
    """GET /api/v1/consulting/library response payload.

    `facets` is always the *full-set* facet catalog (not narrowed by the
    current filter) — see plan §8.1 for the UX rationale and §5 for the
    test that guards this invariant.
    """

    items: list[KnowledgeObject]
    total: int
    limit: int
    offset: int
    facets: dict[str, list[str]]


class FacetsResponse(BaseModel):
    """GET /api/v1/consulting/facets response payload."""

    facets: dict[str, list[str]]
    total: int


__all__ = [
    "KnowledgeObject",
    "LibraryResponse",
    "FacetsResponse",
    "TypeT",
    "SourceOriginT",
    "ConfidenceT",
    "ReviewStateT",
]
