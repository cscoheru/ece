"""KC-001 — FastAPI router for the Consulting Knowledge Copilot.

Three read-only endpoints, all backed by the bundled JSON seed catalog
(no DB, no LLM, no embedding, no chat — Task §3 Out-of-scope).

  GET /api/v1/consulting/library        — filtered + searched + paginated
  GET /api/v1/consulting/facets         — full-corpus facet catalog
  GET /api/v1/consulting/objects/{id}   — single object detail (404 if absent)

The router deliberately raises HTTP 404 (not 422) on a missing object id
because the SPA uses the status code to render the "not found" empty
state — distinct from "your filter excluded everything", which renders
the regular empty state with status 200 and ``total=0``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ece.consulting.engine_merge import merge_engine
from ece.consulting.models import FacetsResponse, KnowledgeObject, LibraryResponse
from ece.consulting.service import default_catalog

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
    # OEI-006: the static response is computed FIRST and is never mutated — the
    # engine merge only ever adds the two new fields on top. `model_copy(update=)`
    # (rather than rebuilding the response) is what structurally guarantees the
    # static fields stay byte-identical for existing consumers.
    engine_items, engine_status = await merge_engine(q)
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


__all__ = ["router"]
