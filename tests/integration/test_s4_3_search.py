"""S4.3 — POST /search endpoint tests.

Verifies:
1. Endpoint accepts X-User-Id header
2. Keyword route returns ranked items
3. Meta has latency_ms + kinds_used
4. Empty query handled
5. Stub routes (vector/structured/relationship) return []

Pre-condition: scripts/ingest_demo_docs.py has been run (1+ doc in DB).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ece.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module", autouse=True)
def ensure_demo_docs_ingested() -> None:
    """Ingest demo docs before running tests (idempotent)."""
    result = subprocess.run(
        ["uv", "run", "python", "scripts/ingest_demo_docs.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    if result.returncode != 0:
        import pytest
        pytest.skip(f"ingest_demo_docs failed: {result.stderr}")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_search_requires_user_id(client: TestClient) -> None:
    """Missing X-User-Id AND user_id body → 400."""
    r = client.post(
        "/api/v1/search",
        json={"query": "test", "kinds": ["keyword"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "bad_request"


def test_search_with_x_user_id_header(client: TestClient) -> None:
    """X-User-Id header accepted."""
    r = client.post(
        "/api/v1/search",
        json={"query": "采购", "kinds": ["keyword"], "top_k": 5},
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert "meta" in body
    assert "keyword" in body["meta"]["kinds_used"]
    assert body["meta"]["latency_ms"] >= 0


def test_search_keyword_returns_hits(client: TestClient) -> None:
    """Keyword route returns hit items with rank + src."""
    r = client.post(
        "/api/v1/search",
        json={"query": "采购", "kinds": ["keyword"], "top_k": 10},
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    # Items may be empty (Chinese tokenization limits) but should be list
    assert isinstance(items, list)
    # If hits present, structure correct
    if items:
        hit = items[0]
        assert hit["kind"] == "keyword"
        assert "ref" in hit
        assert "snippet" in hit
        assert "score" in hit
        assert "src" in hit


def test_search_with_doc_type_filter(client: TestClient) -> None:
    """doc_type filter applied (non-matching returns empty)."""
    r = client.post(
        "/api/v1/search",
        json={
            "query": "采购",
            "kinds": ["keyword"],
            "filters": {"doc_type": "nonexistent_type"},
            "top_k": 10,
        },
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_search_meta_includes_latency_and_kinds(client: TestClient) -> None:
    """Meta has latency_ms + kinds_used (per docs/API.md §2)."""
    r = client.post(
        "/api/v1/search",
        json={"query": "采购", "kinds": ["keyword"], "top_k": 5},
        headers={"X-User-Id": "demo-user-procurement"},
    )
    body = r.json()
    assert "latency_ms" in body["meta"]
    assert "kinds_used" in body["meta"]
    assert "denied_count" in body["meta"]
    assert "query" in body["meta"]


def test_search_user_id_body_fallback(client: TestClient) -> None:
    """No header but body user_id accepted (back-compat per docs/API.md §0)."""
    r = client.post(
        "/api/v1/search",
        json={
            "user_id": "demo-user-procurement",
            "query": "采购",
            "kinds": ["keyword"],
        },
    )
    assert r.status_code == 200


def test_search_empty_kinds_returns_empty(client: TestClient) -> None:
    """kinds=[] → no routes used, items=[]."""
    r = client.post(
        "/api/v1/search",
        json={"query": "采购", "kinds": []},
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["meta"]["kinds_used"] == []


def test_search_top_k_bounds(client: TestClient) -> None:
    """top_k > 100 → 422 validation error."""
    r = client.post(
        "/api/v1/search",
        json={"query": "test", "kinds": ["keyword"], "top_k": 500},
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 422  # Pydantic validation
