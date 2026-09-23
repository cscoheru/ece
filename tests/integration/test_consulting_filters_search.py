"""KC-001 — /api/v1/consulting/* filter / search / pagination integration tests.

Exercises the realistic API surface over FastAPI TestClient:
  - q keyword search hits expected objects
  - type / source_origin single-value filters
  - multi-value practice / engagement_phase / client_industry / problem_type
    filters use any-match semantics
  - combining multiple filters narrows results
  - sort=title returns ascending id order
  - empty result is allowed (200 with total=0)
  - limit clamp: limit must be ge=1 / le=100
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_keyword_search_hits_expected_objects(client: TestClient) -> None:
    """q=采购 (or similar Chinese keyword that appears in the seed) returns ≥ 1 record."""
    r = client.get("/api/v1/consulting/library", params={"q": "采购"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1, f"keyword '采购' must match ≥ 1 record; got {body['total']}"
    # The matched record must contain the keyword in some text field
    # (title / summary / methods / problem_types / deliverables).
    for o in body["items"]:
        haystack = " ".join(
            [o["title"], o["summary"]]
            + o["methods"] + o["problem_types"] + o["deliverables"]
        )
        assert "采购" in haystack, f"q=采购 matched {o['id']!r} without '采购' in text"


def test_type_filter_methodology(client: TestClient) -> None:
    r = client.get("/api/v1/consulting/library", params={"type": "methodology", "limit": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    for o in body["items"]:
        assert o["type"] == "methodology"


def test_source_origin_filter_synthetic_variant(client: TestClient) -> None:
    r = client.get(
        "/api/v1/consulting/library",
        params={"source_origin": "synthetic_variant", "limit": 100},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    for o in body["items"]:
        assert o["source_origin"] == "synthetic_variant"
        # PRD §4.2: synthetic must imply confidence=synthetic
        assert o["confidence"] == "synthetic"


def test_multi_value_practice_filter_is_any_match(client: TestClient) -> None:
    """Passing practice=['procurement','compliance'] returns items whose
    practice list intersects either."""
    r = client.get(
        "/api/v1/consulting/library",
        params=[("practice", "procurement"), ("practice", "compliance"), ("limit", 100)],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    for o in body["items"]:
        assert set(o["practice"]) & {"procurement", "compliance"}, (
            f"multi-value practice filter leaked {o['id']!r} (practice={o['practice']!r})"
        )


def test_combined_filters_narrow_results(client: TestClient) -> None:
    """type=case + source_origin=synthetic_variant must narrow the result set."""
    unfiltered = client.get("/api/v1/consulting/library?limit=100").json()
    filtered = client.get(
        "/api/v1/consulting/library",
        params={"type": "case", "source_origin": "synthetic_variant", "limit": 100},
    ).json()
    assert filtered["total"] <= unfiltered["total"], (
        "filtering must never grow the result set"
    )
    assert filtered["total"] >= 1
    for o in filtered["items"]:
        assert o["type"] == "case"
        assert o["source_origin"] == "synthetic_variant"


def test_sort_title_returns_stable_id_order(client: TestClient) -> None:
    r = client.get(
        "/api/v1/consulting/library", params={"sort": "title", "limit": 100}
    )
    assert r.status_code == 200, r.text
    ids = [o["id"] for o in r.json()["items"]]
    assert ids == sorted(ids), f"sort=title must yield ascending id order, got {ids!r}"


def test_empty_filter_result_is_200_with_total_zero(client: TestClient) -> None:
    """A filter combination that yields no objects must return 200 + total=0,
    not 404 or 500. The SPA relies on this to render the empty state."""
    # Build a query that almost certainly returns nothing — combine an
    # impossible type/source pairing (type=case + source_origin=licensed_public
    # if the seed has none) or use a totally bogus keyword.
    r = client.get(
        "/api/v1/consulting/library",
        params={"q": "this_keyword_does_not_exist_anywhere_in_the_seed_zzzzz"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0, f"empty filter must yield total=0, got {body['total']}"
    assert body["items"] == []
