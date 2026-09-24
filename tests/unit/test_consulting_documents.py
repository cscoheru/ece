"""OEI-007 — DB-free unit tests for the Consulting upload + status pipeline.

Covers:
  - metadata.py: whitelist / size guards / vocabulary check / deterministic
    suggestion / caller-override semantics
  - Port contract: both Mock and Onyx satisfy `ContentEnginePort` and the
    `EngineDocumentStatus` shape
  - mock adapter write path: deterministic per-process counter; status
    round-trip; cross-instance consistency (simulates the live adapter's
    process-wide state)
  - upload route (TestClient, mock engine): happy / bad-ext / empty / oversize
    / partial multi-file / aggregate oversize / zero-files / status 404 /
    status 502 when engine is down

No DB, no Onyx — runs in 0.0x seconds.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from ece.connectors.onyx.mock_adapter import (
    MockContentEngineAdapter,
    reset_mock_engine_store,
)
from ece.connectors.onyx.onyx_adapter import OnyxContentEngineAdapter
from ece.connectors.onyx.port import (
    ContentEnginePort,
    EngineDocumentStatus,
)
from ece.consulting import metadata as md
from ece.consulting.models import (
    DocumentStatusResponse,
    UploadResponse,
)
from ece.main import app

# ---------------------------------------------------------------------------
# metadata.py — pure-function tests (no app, no engine, no DB)
# ---------------------------------------------------------------------------


def test_whitelist_accepts_documented_extensions() -> None:
    for ext in (".md", ".txt", ".docx", ".pdf"):
        assert md.check_extension(f"foo{ext}") == ext


@pytest.mark.parametrize("filename,reason_keyword", [
    ("bad.exe", "not allowed"),
    ("image.png", "not allowed"),
    ("archive.zip", "not allowed"),
    ("noext", "no extension"),
    ("", "empty"),
])
def test_whitelist_rejects_with_clear_reason(filename: str, reason_keyword: str) -> None:
    with pytest.raises(ValueError, match=reason_keyword):
        md.check_extension(filename)


def test_check_single_size_rejects_empty_and_oversize() -> None:
    with pytest.raises(ValueError, match="empty"):
        md.check_single_size(0)
    with pytest.raises(ValueError, match="too large"):
        md.check_single_size(md.MAX_SINGLE_FILE_BYTES + 1)
    # boundary + normal both pass
    md.check_single_size(1)
    md.check_single_size(md.MAX_SINGLE_FILE_BYTES)


def test_check_aggregate_size_rejects_oversize_only() -> None:
    md.check_aggregate_size(0)  # 0 sum is not an error (only per-file empty is)
    md.check_aggregate_size(md.MAX_TOTAL_BYTES)
    with pytest.raises(ValueError, match="aggregate too large"):
        md.check_aggregate_size(md.MAX_TOTAL_BYTES + 1)


def test_suggest_metadata_is_deterministic_across_n_runs() -> None:
    """TASK §4 step 3 (A3): same input × N → byte-identical."""
    for _ in range(5):
        a = md.suggest_metadata("retail-case.md", "零售门店坪效诊断")
        b = md.suggest_metadata("retail-case.md", "零售门店坪效诊断")
        assert a == b
        # Also: every emitted value lands in the seed vocab (no suggestion outside)
        assert a["client_industry"] == ["retail"]
        assert a["client_industry"][0] in md.ALLOWED_INDUSTRIES
        assert all(v in md.ALLOWED_INDUSTRIES for v in a["client_industry"])


def test_suggest_metadata_emits_no_vocab_violations() -> None:
    cases = [
        ("bank-pricing-case.md", None),
        ("retail-case.md", "零售"),
        ("methodology.md", "MECE"),
        ("play-proposal.md", "sales"),
        ("anything.md", "energy insurance"),
        ("unknown.bin", "随便"),
    ]
    for fname, title in cases:
        s = md.suggest_metadata(fname, title)
        for k, vs in s.items():
            if not vs:
                continue
            allowed = {
                "type": md.ALLOWED_TYPES,
                "engagement_phase": md.ALLOWED_PHASES,
                "client_industry": md.ALLOWED_INDUSTRIES,
            }[k]
            for v in vs:
                assert v in allowed, f"suggested {k}={v!r} not in vocab"


def test_resolve_metadata_caller_wins_and_garbage_dropped() -> None:
    suggestion = md.suggest_metadata("retail-case.md", "零售")
    # Caller asks for energy + a fake type + a non-vocab value
    merged = md.resolve_metadata(
        {"client_industry": ["energy"], "type": "proposal_play",
         "garbage_value": "drop-1"},
        suggestion,
    )
    assert merged["client_industry"] == ["energy"]
    assert merged["type"] == ["proposal_play"]  # caller overrode suggestion
    # Unknown keys are silently dropped — we don't pretend we know what to do
    # with them. (The seed vocab check is the only authoritative gate.)
    assert "garbage_value" not in merged


def test_validate_metadata_drops_unknown_keys_silently() -> None:
    """Unknown keys pass through the function; the consulting route forwards only
    known fields to the engine (the engine ignores the rest anyway). We do NOT
    refuse the upload — that would be a UX trap."""
    out = md.validate_metadata({"client_industry": ["retail"], "unknown_key": ["v"]})
    assert out["client_industry"] == ["retail"]
    # Unknown keys are silently dropped (not in _dropped — only known-but-invalid
    # values go there, since unknown keys are caller-side advice we can't interpret).
    assert "unknown_key" not in out


# ---------------------------------------------------------------------------
# Port contract
# ---------------------------------------------------------------------------


def test_adapters_satisfy_port_protocol() -> None:
    assert isinstance(MockContentEngineAdapter(), ContentEnginePort)
    assert isinstance(OnyxContentEngineAdapter(), ContentEnginePort)


def test_engine_document_status_shape_is_stable() -> None:
    """Both adapters produce the same status shape."""
    # mock
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    rec_m = asyncio.run(m.upload_document("x.md", b"hello", project_id=1))
    # onyx shape (no network — just model_validate on a dict)
    from ece.connectors.onyx.onyx_adapter import _upload_status_record
    sample = {
        "id": "abc-123", "name": "x.md", "status": "COMPLETED",
        "chunk_count": 4, "project_id": 1, "file_id": "def-456",
    }
    rec_o = _upload_status_record(sample)
    for r in (rec_m, rec_o):
        assert isinstance(r, EngineDocumentStatus)
        assert set(r.model_dump(mode="json").keys()) == {
            "document_id", "name", "status", "chunk_count",
            "project_id", "failure_reason", "raw",
        }


# ---------------------------------------------------------------------------
# Mock adapter write path
# ---------------------------------------------------------------------------


def test_mock_upload_then_status_roundtrip() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    rec = asyncio.run(m.upload_document("foo.md", b"hello", project_id=1,
                                        title="T", metadata={"k": "v"}))
    s = asyncio.run(m.document_status(rec.document_id))
    assert s.document_id == rec.document_id
    assert s.status == "COMPLETED"
    assert s.chunk_count == 1
    # metadata is preserved in raw for end-to-end tracing
    assert s.raw["ece_metadata"] == {"k": "v"}
    assert s.raw["ece_title"] == "T"


def test_mock_status_unknown_raises_engine_error() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    with pytest.raises(Exception) as ei:
        asyncio.run(m.document_status("does-not-exist"))
    assert "not found" in str(ei.value).lower()


def test_mock_store_persists_across_instances() -> None:
    """Selector returns a fresh MockContentEngineAdapter per call — but the
    module-level store means polls always find the upload."""
    reset_mock_engine_store()
    m1 = MockContentEngineAdapter()
    rec = asyncio.run(m1.upload_document("foo.md", b"x", project_id=1))
    m2 = MockContentEngineAdapter()  # different instance
    s = asyncio.run(m2.document_status(rec.document_id))
    assert s.document_id == rec.document_id


def test_mock_doc_ids_are_unique_within_process() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    ids = set()
    for i in range(5):
        r = asyncio.run(m.upload_document(f"f{i}.md", b"x", project_id=1))
        assert r.document_id not in ids
        ids.add(r.document_id)


def test_reset_mock_engine_store_clears_state() -> None:
    from ece.connectors.onyx.port import EngineError
    m = MockContentEngineAdapter()
    rec = asyncio.run(m.upload_document("foo.md", b"x", project_id=1))
    reset_mock_engine_store()
    with pytest.raises(EngineError, match="not found"):
        asyncio.run(m.document_status(rec.document_id))


# ---------------------------------------------------------------------------
# Router-level (TestClient + mock engine)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    reset_mock_engine_store()
    return TestClient(app)


def _post_files(c: TestClient, files, data=None):
    return c.post("/api/v1/consulting/documents", files=files, data=data or {})


def test_upload_happy(client: TestClient) -> None:
    files = [("file", ("foo.md", b"# body\n\n" * 10, "text/markdown"))]
    r = client.post("/api/v1/consulting/documents", files=files, data={"title": "Foo"})
    assert r.status_code == 200
    body = r.json()
    UploadResponse.model_validate(body)
    assert body["documents"][0]["accepted"] is True
    assert body["documents"][0]["document_id"].startswith("mock-")
    assert body["static_catalog_size"] == 36  # KC-001 baseline preserved


def test_upload_bad_extension_rejected(client: TestClient) -> None:
    files = [("file", ("bad.exe", b"x", "application/octet-stream"))]
    r = client.post("/api/v1/consulting/documents", files=files)
    assert r.status_code == 200
    assert r.json()["documents"][0]["accepted"] is False
    assert "not allowed" in r.json()["documents"][0]["reason"]


def test_upload_empty_rejected_per_file(client: TestClient) -> None:
    files = [("file", ("empty.md", b"", "text/markdown"))]
    r = client.post("/api/v1/consulting/documents", files=files)
    assert r.status_code == 200
    assert r.json()["documents"][0]["accepted"] is False
    assert "empty" in r.json()["documents"][0]["reason"]


def test_upload_oversize_single_rejected_per_file(client: TestClient) -> None:
    big = b"x" * (md.MAX_SINGLE_FILE_BYTES + 1)
    files = [("file", ("big.md", big, "text/markdown"))]
    r = client.post("/api/v1/consulting/documents", files=files)
    assert r.status_code == 200
    assert r.json()["documents"][0]["accepted"] is False
    assert "too large" in r.json()["documents"][0]["reason"]


def test_upload_aggregate_oversize_is_413(client: TestClient) -> None:
    huge = b"x" * (md.MAX_TOTAL_BYTES + 1)
    files = [("file", ("huge.md", huge, "text/markdown"))]
    r = client.post("/api/v1/consulting/documents", files=files)
    assert r.status_code == 413


def test_upload_zero_files_is_422(client: TestClient) -> None:
    r = client.post("/api/v1/consulting/documents", files=[])
    assert r.status_code == 422


def test_upload_multi_file_partial_success(client: TestClient) -> None:
    files = [
        ("file", ("good.md", b"# good\n" * 10, "text/markdown")),
        ("file", ("bad.exe", b"x", "application/octet-stream")),
        ("file", ("empty.md", b"", "text/markdown")),
    ]
    r = client.post("/api/v1/consulting/documents", files=files)
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs[0]["accepted"] is True
    assert docs[1]["accepted"] is False
    assert docs[2]["accepted"] is False
    assert r.json()["static_catalog_size"] == 36


def test_upload_metadata_vocab_check_field(client: TestClient) -> None:
    """Caller passes garbage values — `metadata_vocabulary_check` should be
    'dropped' so the SPA can render a hint."""
    files = [("file", ("foo.md", b"# ok\n" * 5, "text/markdown"))]
    r = client.post("/api/v1/consulting/documents", files=files,
                    data={"client_industry": "made_up_industry"})
    assert r.status_code == 200
    # Dropped silently + hinted
    assert r.json()["metadata_vocabulary_check"] == "dropped"


def test_get_status_happy(client: TestClient) -> None:
    files = [("file", ("foo.md", b"# ok\n" * 10, "text/markdown"))]
    up = client.post("/api/v1/consulting/documents", files=files)
    doc_id = up.json()["documents"][0]["document_id"]
    s = client.get(f"/api/v1/consulting/documents/{doc_id}")
    assert s.status_code == 200
    DocumentStatusResponse.model_validate(s.json())
    assert s.json()["document_id"] == doc_id
    assert s.json()["status"] in ("PROCESSING", "COMPLETED", "FAILED")


def test_get_status_unknown_returns_404(client: TestClient) -> None:
    s = client.get("/api/v1/consulting/documents/does-not-exist")
    assert s.status_code == 404


def test_get_status_engine_down_returns_502(client: TestClient, monkeypatch) -> None:
    """When the engine is unreachable, the GET endpoint must surface 502, not 500."""
    # Patch the *module*, not the APIRouter instance. ece.consulting.__init__
    # re-exports `router` as the APIRouter, so `import ece.consulting.router as X`
    # binds X to the APIRouter — we must reach for the module via sys.modules.
    import sys
    router_mod = sys.modules["ece.consulting.router"]
    from ece.connectors.onyx.port import EngineError

    class _Boom:
        async def document_status(self, *a, **kw):
            raise EngineError("transport failure: connection refused")

    monkeypatch.setattr(router_mod, "get_content_engine", lambda: _Boom())
    s = client.get("/api/v1/consulting/documents/anything")
    assert s.status_code == 502


def test_get_status_engine_not_found_returns_404(client: TestClient, monkeypatch) -> None:
    import sys
    router_mod = sys.modules["ece.consulting.router"]
    from ece.connectors.onyx.port import EngineError

    class _NotFound:
        async def document_status(self, *a, **kw):
            raise EngineError("Onyx status: document_id='x' not found")

    monkeypatch.setattr(router_mod, "get_content_engine", lambda: _NotFound())
    s = client.get("/api/v1/consulting/documents/anything")
    assert s.status_code == 404


# ---------------------------------------------------------------------------
# Static side untouched — uploads must not change the static catalog payload.
# ---------------------------------------------------------------------------


def test_static_side_byte_identical_with_or_without_uploads(client: TestClient) -> None:
    baseline = client.get("/api/v1/consulting/library", params={"q": "零售"}).json()
    base_static = {k: baseline[k] for k in ("items", "total", "limit", "offset", "facets")}

    files = [("file", ("x.md", b"# x\n" * 5, "text/markdown")),
             ("file", ("bad.exe", b"x", "application/octet-stream"))]
    client.post("/api/v1/consulting/documents", files=files)

    after = client.get("/api/v1/consulting/library", params={"q": "零售"}).json()
    after_static = {k: after[k] for k in ("items", "total", "limit", "offset", "facets")}
    assert after_static == base_static
    # engine side DID change (mock engine is disabled in default mode, so unchanged)
    # but the two new fields are present and defaults are sane:
    assert "engine_items" in after
    assert "engine_status" in after
