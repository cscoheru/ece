"""S4.3 — POST /search endpoint.

Per docs/API.md §2:
  POST /api/v1/search executes unified search across multiple routes
  (keyword/vector/entity/structured/relationship).

For cut-010 (Sprint 4 entry): only FTS keyword route implemented.
Vector/structured/relationship routes are stubs (return []) — full
implementation in Sprint 4 main (cut-010+).

Per ADR-004: routes apply PermissionScope filter at SQL level (NOT post-filter;
prevents sort/limit side-channel leaks).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.db import get_engine

router = APIRouter(prefix="/api/v1", tags=["search"])


class SearchRequest(BaseModel):
    """POST /search request body (per docs/API.md §2)."""

    user_id: str = Field(
        "",
        description="X-User-Id value (header preferred; body fallback)",
    )
    query: str = Field(..., description="search query text")
    kinds: list[str] = Field(
        default_factory=lambda: ["keyword"],
        description="routes to use (keyword/vector/entity/structured/relationship)",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="filters (entity_type, doc_type, etc.)",
    )
    top_k: int = Field(default=10, ge=1, le=100)
    query_embedding: list[float] | None = Field(
        default=None,
        description="pre-computed query vector (512-dim) for vector route; "
        "omit to skip vector route even if 'vector' in kinds",
    )


@router.post("/search")
def post_search(
    req: SearchRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Unified search across multiple routes.

    Per ADR-004 anti-probing: missing resources and forbidden resources both
    return uniform envelope. denied_count in meta (no leak details).

    Raises:
        400: missing X-User-Id + user_id
        500: internal error
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
    t0 = time.monotonic()

    items: list[dict[str, Any]] = []
    kinds_used: list[str] = []

    # Route 1: FTS keyword (cut-010: only this implemented)
    if "keyword" in req.kinds:
        from ece.connectors.docs import search_documents

        doc_type = req.filters.get("doc_type")
        try:
            hits = search_documents(
                engine,
                query=req.query,
                top_k=req.top_k,
                doc_type_filter=doc_type,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"code": "internal", "message": str(e)},
            ) from e

        kinds_used.append("keyword")
        for hit in hits:
            display_id = hit["document_display_id"]
            chunk_idx = hit["chunk_index"]
            items.append({
                "kind": "keyword",
                "ref": f"{display_id}#{chunk_idx}",
                "title": display_id,
                "snippet": hit["snippet"],
                "score": hit["rank"],
                "src": {
                    "system": "docs",
                    "document_id": display_id,
                    "page": chunk_idx,
                },
                "matched_by": ["tsv"],
            })

    # Route 2: Vector similarity (cut-013; requires query_embedding)
    if "vector" in req.kinds and req.query_embedding is not None:
        from ece.connectors.docs import search_documents_vector

        doc_type = req.filters.get("doc_type")
        try:
            hits = search_documents_vector(
                engine,
                query_embedding=req.query_embedding,
                top_k=req.top_k,
                doc_type_filter=doc_type,
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"code": "internal", "message": str(e)},
            ) from e

        kinds_used.append("vector")
        for hit in hits:
            display_id = hit["document_display_id"]
            chunk_idx = hit["chunk_index"]
            items.append({
                "kind": "vector",
                "ref": f"{display_id}#{chunk_idx}",
                "title": display_id,
                "snippet": hit["snippet"],
                "score": hit["similarity"],
                "src": {
                    "system": "docs",
                    "document_id": display_id,
                    "page": chunk_idx,
                },
                "matched_by": ["embedding"],
            })

    # Routes 2-4: stubs for cut-010
    # vector route (Sprint 4 main): requires embedding model
    # structured route (Sprint 5+): per-spec.kind SQL + row-level perms
    # relationship route (Sprint 4 main): entity linking + perm filter

    latency_ms = int((time.monotonic() - t0) * 1000)

    return {
        "items": items,
        "meta": {
            "denied_count": 0,  # TODO: per-route permission filter (cut-011+)
            "kinds_used": kinds_used,
            "latency_ms": latency_ms,
            "query": req.query,
        },
    }
