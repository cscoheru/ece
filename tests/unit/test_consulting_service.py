"""KC-001 — ConsultingCatalog service-layer binding tests.

Exercises the in-memory catalog directly (no FastAPI):
  - search() returns LibraryResponse with full-corpus facets
  - facets() returns FacetsResponse with stable keys
  - get(id) returns single object or None
  - sort/limit/offset work as documented
  - Multi-value filters use any-match semantics
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ece.consulting.service import _FACET_KEYS, ConsultingCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "src" / "ece" / "consulting" / "seed" / "consulting_objects.json"


@pytest.fixture(scope="module")
def catalog() -> ConsultingCatalog:
    return ConsultingCatalog.from_seed_path(SEED_PATH)


def test_search_returns_library_response_with_full_corpus_facets(catalog: ConsultingCatalog) -> None:
    """search() must return facets covering the full corpus, regardless of filter.
    Plan §8.1: facet search UX requires showing all choices — narrowing facets
    after filtering would trap the user (can't switch filters)."""
    full = catalog.facets().facets
    narrowed = catalog.search(type="case").facets
    assert full == narrowed, (
        "facets in search() must NOT depend on the current filter"
    )


def test_search_filters_by_type(catalog: ConsultingCatalog) -> None:
    """type filter restricts items to that single type."""
    resp = catalog.search(type="methodology")
    # All returned items must have the requested type
    for o in resp.items:
        assert o.type == "methodology"
    # total must equal the number of methodology records in the seed
    methodology_count = sum(1 for o in catalog.objects if o.type == "methodology")
    assert resp.total == methodology_count, (
        f"methodology filter: total={resp.total} but seed has {methodology_count} methodology records"
    )


def test_search_filters_by_source_origin(catalog: ConsultingCatalog) -> None:
    resp = catalog.search(source_origin="methodology_note")
    assert resp.total >= 1, "expected at least one methodology_note object"
    for o in resp.items:
        assert o.source_origin == "methodology_note"


def test_multi_value_filter_is_any_match(catalog: ConsultingCatalog) -> None:
    """passing practice=['a','b'] keeps items where practice intersects {a,b}."""
    all_practices = sorted({p for o in catalog.objects for p in o.practice})
    assert len(all_practices) >= 2, "test prerequisite: need ≥ 2 distinct practice values"
    pick = all_practices[:2]
    resp = catalog.search(practice=pick)
    # Every returned item must have at least one practice in {pick}
    for o in resp.items:
        assert set(o.practice) & set(pick), (
            f"{o.id!r} has practice={o.practice!r}, none in {pick}"
        )


def test_keyword_search_matches_across_text_fields(catalog: ConsultingCatalog) -> None:
    """q keyword must match title/summary/methods/problem_types/deliverables."""
    # Use a stable Chinese keyword that we know appears in the seed.
    resp = catalog.search(q="采购")
    # At least one item should match (we have a procurement case in the seed)
    assert resp.total >= 1, "expected at least one match for keyword '采购'"


def test_sort_title_orders_by_id(catalog: ConsultingCatalog) -> None:
    """sort='title' uses id as the stable secondary key. We don't have a
    separate title sort because id is already stable; the test guards that
    the id ordering is reproducible."""
    resp = catalog.search(sort="title")
    ids = [o.id for o in resp.items]
    assert ids == sorted(ids), f"sort=title must yield ascending id order, got {ids!r}"


def test_limit_and_offset_paginate(catalog: ConsultingCatalog) -> None:
    """limit + offset must page through results."""
    page1 = catalog.search(limit=5, offset=0)
    page2 = catalog.search(limit=5, offset=5)
    assert len(page1.items) == 5
    assert page1.total == page2.total, "total must be independent of paging"
    ids1 = {o.id for o in page1.items}
    ids2 = {o.id for o in page2.items}
    assert ids1.isdisjoint(ids2), "page 1 and page 2 must not overlap"


def test_get_returns_object_or_none(catalog: ConsultingCatalog) -> None:
    """get(id) must return the matching object or None (no exceptions)."""
    sample = catalog.objects[0]
    assert catalog.get(sample.id) is sample
    assert catalog.get("__definitely_not_a_real_id__") is None


def test_facets_have_six_documented_keys(catalog: ConsultingCatalog) -> None:
    """facets() must return all six documented facet keys (plan §3.2 + service _FACET_KEYS)."""
    assert tuple(_FACET_KEYS) == (
        "types", "practices", "engagement_phases",
        "client_industries", "problem_types", "source_origins",
    )
    facets = catalog.facets().facets
    assert set(facets.keys()) == set(_FACET_KEYS), (
        f"facets keys={sorted(facets.keys())} != expected={sorted(_FACET_KEYS)}"
    )
    # Every facet list must be non-empty (the seed is non-empty)
    for k, vs in facets.items():
        assert vs, f"facet {k!r} is empty"
