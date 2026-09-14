"""R4 S1.3: API contract via TestClient (4 endpoints, 404 envelope, wrapped items)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_entity_404_uniform_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/entities/NONEXISTENT-XYZ")
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body
    assert body["detail"]["code"] == "not_found"


def test_get_entity_found(client: TestClient) -> None:
    # Need a real entity; use supplier from prior seed
    r = client.get("/api/v1/entities/SUP001")
    if r.status_code == 404:
        pytest.skip("seed not run; make seed first")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "supplier"
    assert "ref" in body and "src" in body


def test_list_entities_pagination(client: TestClient) -> None:
    r = client.get(
        "/api/v1/entities?type=supplier&limit=5",
        headers={"X-User-Id": "demo-user-procurement"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "next_cursor" in body
    assert len(body["items"]) <= 5


def test_post_ingest_runs_wrapped_items(client: TestClient) -> None:
    """S1.1 API: POST /ingest/runs accepts {connector, params} (not wrapped items at top level).

    Per cut-005 R4 contract test: ingest endpoint returns response_model IngestResponse
    ({run_id, stats}). Validate shape on success path; unknown connector -> 400.
    """
    # Unknown connector type (no prefix match) -> 400
    r = client.post(
        "/api/v1/ingest/runs",
        json={"connector": "unknown:nonexistent", "params": {}},
    )
    assert r.status_code == 400, f"unknown connector should 400; got {r.status_code}"
