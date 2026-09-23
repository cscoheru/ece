"""KC-001 — /api/v1/consulting/* API contract suite.

Per Task §7.3 + plan §3.4 + PRD §5:
  - GET /api/v1/consulting/library returns 200 with full LibraryResponse
  - GET /api/v1/consulting/facets returns 200 with full FacetsResponse
  - GET /api/v1/consulting/objects/{id} returns 200 with KnowledgeObject
  - GET /api/v1/consulting/objects/{id_404} returns 404 (HTTPException)
  - All response fields are business-named; forbidden technical
    vocabulary (decision_id / policy_id / evidence_id / package_id /
    ctx_ / SQL / embedding / vector / prompt / token) must NOT appear
    in any API response
  - FastAPI TestClient starts the real app (not a mock) — same origin
    guardrail as cut-045R3
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app

# Same forbidden vocabulary set as tests/unit/test_consulting_spa_view.py.
# These must NEVER appear in any /api/v1/consulting/* response payload —
# the consulting catalog is a business-facing API and must not leak
# internal Kernel field names.
_FORBIDDEN_SUBSTRINGS = (
    "embedding", "embeddings",
    "vector", "vectors",
    "ctx_",
    "decision_id",
    "policy_id",
    "evidence_id",
    "package_id",
    "context_request_id",
    "input_context_ref",
    "SQL",
    "prompt",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_library_returns_200_with_expected_top_level_keys(client: TestClient) -> None:
    """GET /api/v1/consulting/library → 200, items/total/limit/offset/facets all present."""
    r = client.get("/api/v1/consulting/library")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("items", "total", "limit", "offset", "facets"):
        assert key in body, f"missing key {key!r} in library response: {body!r}"
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert body["total"] >= 36, f"expected ≥ 36 library records, got {body['total']}"
    # Facets must carry all six documented keys
    for fk in (
        "types", "practices", "engagement_phases",
        "client_industries", "problem_types", "source_origins",
    ):
        assert fk in body["facets"], f"facet key {fk!r} missing: {body['facets'].keys()}"


def test_get_facets_returns_200_with_six_keys(client: TestClient) -> None:
    """GET /api/v1/consulting/facets → 200, six stable facet keys."""
    r = client.get("/api/v1/consulting/facets")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("facets", "total"):
        assert key in body, f"missing key {key!r}: {body!r}"
    for fk in (
        "types", "practices", "engagement_phases",
        "client_industries", "problem_types", "source_origins",
    ):
        assert fk in body["facets"], f"facet key {fk!r} missing"


def test_get_object_returns_200_for_known_id(client: TestClient) -> None:
    """GET /api/v1/consulting/objects/{known_id} → 200 with KnowledgeObject."""
    # First, ask the library for one real id
    lib = client.get("/api/v1/consulting/library?limit=1").json()
    assert lib["items"], "library returned no items; cannot pick a known id"
    sample_id = lib["items"][0]["id"]

    r = client.get(f"/api/v1/consulting/objects/{sample_id}")
    assert r.status_code == 200, f"known id must return 200; got {r.status_code}: {r.text}"
    obj = r.json()
    assert obj["id"] == sample_id
    # Required business-named fields
    for key in (
        "type", "title", "summary",
        "practice", "engagement_phase", "client_industry",
        "problem_types", "methods", "deliverables", "outcomes",
        "source_origin", "confidence", "review_state",
    ):
        assert key in obj, f"missing field {key!r} in KnowledgeObject response"


def test_get_object_returns_404_for_unknown_id(client: TestClient) -> None:
    """GET /api/v1/consulting/objects/__nonexistent__ → 404 (HTTPException)."""
    r = client.get("/api/v1/consulting/objects/__definitely_not_a_real_id__")
    assert r.status_code == 404, (
        f"unknown id must return 404; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "detail" in body, "404 response must include 'detail' message"


def test_library_response_has_no_forbidden_technical_substrings(client: TestClient) -> None:
    """Library / facets / object responses must not leak any forbidden
    internal Kernel vocabulary."""
    endpoints = [
        "/api/v1/consulting/library",
        "/api/v1/consulting/facets",
    ]
    for url in endpoints:
        r = client.get(url)
        assert r.status_code == 200, r.text
        blob = repr(r.json())
        for tok in _FORBIDDEN_SUBSTRINGS:
            assert tok not in blob, f"{url!r} leaked forbidden {tok!r}"


def test_object_detail_response_has_no_forbidden_technical_substrings(client: TestClient) -> None:
    """Single-object detail response must not leak any forbidden vocabulary."""
    lib = client.get("/api/v1/consulting/library?limit=1").json()
    sample_id = lib["items"][0]["id"]
    r = client.get(f"/api/v1/consulting/objects/{sample_id}")
    assert r.status_code == 200, r.text
    blob = repr(r.json())
    for tok in _FORBIDDEN_SUBSTRINGS:
        assert tok not in blob, f"object detail leaked forbidden {tok!r}"


def test_library_endpoint_via_query_paging(client: TestClient) -> None:
    """Library endpoint must respect limit + offset query params."""
    r1 = client.get("/api/v1/consulting/library?limit=3&offset=0").json()
    r2 = client.get("/api/v1/consulting/library?limit=3&offset=3").json()
    assert len(r1["items"]) == 3
    assert len(r2["items"]) == 3
    assert r1["total"] == r2["total"], "total must be independent of paging"
    # page 1 and page 2 must not overlap
    ids1 = {o["id"] for o in r1["items"]}
    ids2 = {o["id"] for o in r2["items"]}
    assert ids1.isdisjoint(ids2)


def test_library_endpoint_with_type_filter_returns_only_that_type(client: TestClient) -> None:
    """type=methodology must return only methodology records."""
    r = client.get("/api/v1/consulting/library?type=methodology&limit=100")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    for o in body["items"]:
        assert o["type"] == "methodology", (
            f"type=methodology leaked non-methodology record: {o!r}"
        )
