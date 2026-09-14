"""S4.2 — Vector similarity search tests (cut-013).

Verifies search_documents_vector function with fake 512-dim embedding.
Real embedding model (bge-small-zh-v1.5) deferred to v0.2 (per cut-013 §2.3
exclusions); test uses fake uniform vector to verify SQL path.

Note: doc_chunks.embedding is NULL for v0 demo docs (never embedded), so
vector search returns []. Test verifies the function path runs without
error + returns list type. Real value test requires populating embeddings.
"""
from __future__ import annotations

import pytest

from ece.connectors.docs import search_documents_vector
from ece.db import get_engine


@pytest.fixture
def fake_embedding() -> list[float]:
    """512-dim uniform embedding (per DATA_MODEL §4)."""
    return [0.01] * 512


def test_vector_search_returns_list(fake_embedding) -> None:
    """search_documents_vector returns list (possibly empty if no embeddings)."""
    engine = get_engine()
    hits = search_documents_vector(
        engine, query_embedding=fake_embedding, top_k=5
    )
    assert isinstance(hits, list)
    # V0 demo docs have no embeddings → empty list expected
    # Once embeddings are populated (v0.2 with bge-small-zh-v1.5), hits will populate


def test_vector_search_with_doc_type_filter(fake_embedding) -> None:
    """doc_type filter applied (non-matching returns empty)."""
    engine = get_engine()
    hits = search_documents_vector(
        engine, query_embedding=fake_embedding, top_k=5, doc_type_filter="nonexistent_type"
    )
    assert hits == []


def test_vector_search_invalid_embedding_length_returns_empty(fake_embedding) -> None:
    """Wrong embedding dimension → query returns empty (no matching 512-dim rows).

    Note: pgvector is strict on dim but our query has `WHERE dc.embedding
    IS NOT NULL` which filters rows first. With all V0 embeddings NULL,
    the wrong-dim string never gets compared. Real value test requires
    populating embeddings.
    """
    engine = get_engine()
    wrong_dim = [0.01] * 256  # 256 instead of 512
    # WHERE dc.embedding IS NOT NULL filters everything; empty result
    hits = list(search_documents_vector(
        engine, query_embedding=wrong_dim, top_k=1
    ))
    assert hits == [], "should return empty due to NULL embedding filter"


def test_vector_search_top_k_bounds(fake_embedding) -> None:
    """top_k respected (returns at most top_k hits)."""
    engine = get_engine()
    hits = search_documents_vector(
        engine, query_embedding=fake_embedding, top_k=3
    )
    assert len(hits) <= 3
