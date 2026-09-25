"""OEI-006 — Consulting Library × content engine merge (DB-free unit tests).

TASK §5.1 asked for exactly this: the mapping and the four-state policy proven
with **no database and no network**. Everything here runs against either a pure
function or a hand-written stub, so it is CI-safe on a laptop with neither
Postgres nor Onyx running.

This file also closes a gap OEI-003 left open: no test anywhere referenced
`EngineDocument` / `EngineError`, so nothing pinned the port contract. That is
precisely why the `updated_at` mismatch survived — the port declares
`datetime | None`, the mock adapter agreed by accident with our `str` field, and
only the LIVE Onyx adapter 500'd the endpoint (caught in OEI-006 step 4, see
`test_updated_at_accepts_a_real_datetime_from_the_live_mapping` below, which
runs the real Onyx result-mapping function with no network involved).

The four `engine_status` values are a policy, not a formatting choice:

  ok          we asked, the engine answered (even if the answer was "nothing")
  unavailable we asked, the engine failed      → static catalogue still served
  disabled    we deliberately did not ask      (no live engine selected)
  skipped     there was nothing to ask about   (empty query)
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ece.connectors.onyx.mock_adapter import MockContentEngineAdapter
from ece.connectors.onyx.onyx_adapter import _result_to_engine_document
from ece.connectors.onyx.port import (
    EngineCallerContext,
    EngineDocument,
    EngineError,
)
from ece.consulting import engine_merge
from ece.consulting.engine_merge import DEFAULT_TOP_K, merge_engine, to_engine_items
from ece.consulting.models import EngineItem
from ece.main import app

STATIC_FIELDS = ("items", "total", "limit", "offset", "facets")
ENGINE_FIELDS = ("engine_doc_id", "title", "snippet", "source_type", "updated_at", "source")


def _doc(
    doc_id: str = "1",
    title: str = "methodology-framework.md",
    snippet: str = "片段",
    source_type: str = "user_file",
    updated_at: datetime | None = None,
) -> EngineDocument:
    return EngineDocument(
        engine_doc_id=doc_id,
        title=title,
        snippet=snippet,
        source_type=source_type,
        updated_at=updated_at,
    )


class _StubEngine:
    """Minimal ContentEnginePort stand-in.

    `engine_status` / `list_projects` raise on purpose: `merge_engine` must not
    need them, and a future refactor that starts calling them should fail loudly
    here rather than silently doubling the per-request engine traffic.

    OEI-008: now exposes `engine_name = "onyx"` so `engine_merge`'s
    descriptor-based dispatch treats it as the live engine.
    """

    engine_name = "onyx"

    def __init__(self, docs: list[EngineDocument] | None = None, error: Exception | None = None):
        self.docs = docs or []
        self.error = error
        self.search_calls: list[tuple[str, int | None]] = []

    async def search(self, query: str, *, top_k: int | None = None,
                     caller: EngineCallerContext | None = None) -> list[EngineDocument]:
        self.search_calls.append((query, top_k))
        if self.error is not None:
            raise self.error
        return list(self.docs)

    async def engine_status(self, *, caller: EngineCallerContext | None = None):  # pragma: no cover - asserted not to be called
        raise AssertionError("merge_engine must not call engine_status()")

    async def list_projects(self, *, caller: EngineCallerContext | None = None):  # pragma: no cover - asserted not to be called
        raise AssertionError("merge_engine must not call list_projects()")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# to_engine_items — the pure mapping
# ---------------------------------------------------------------------------


def test_to_engine_items_maps_every_documented_field() -> None:
    ts = datetime(2026, 9, 23, 13, 6, 16, tzinfo=UTC)
    items = to_engine_items([_doc(doc_id="7bb48d46", title="case.md", snippet="案例", updated_at=ts)])
    assert len(items) == 1
    item = items[0]
    assert item.engine_doc_id == "7bb48d46"
    assert item.title == "case.md"
    assert item.snippet == "案例"
    assert item.source_type == "user_file"
    assert item.updated_at == ts


def test_to_engine_items_sets_the_source_discriminator() -> None:
    """`source` is what lets the SPA group/label without guessing."""
    assert to_engine_items([_doc()])[0].source == "engine"


def test_to_engine_items_of_empty_input_is_empty() -> None:
    assert to_engine_items([]) == []


def test_to_engine_items_does_not_truncate_the_snippet() -> None:
    """The API returns the whole adapter-capped snippet.

    Truncation for the card face is the SPA's job; doing it here would make the
    detail drawer lossy for no gain.
    """
    long_snippet = "x" * 900
    assert to_engine_items([_doc(snippet=long_snippet)])[0].snippet == long_snippet


def test_updated_at_accepts_a_real_datetime_from_the_live_mapping() -> None:
    """Regression guard for the OEI-006 step-4 500.

    Runs the REAL Onyx result mapper (`_result_to_engine_document`) on a payload
    shaped like Onyx /api/search — no network, no cookie — and pushes the result
    through the API model. With `updated_at: str | None` on `EngineItem` this
    raised ValidationError and the endpoint returned 500 while every mock-mode
    test stayed green.
    """
    doc = _result_to_engine_document(
        {
            "citation_id": 1,
            "title": "methodology-framework.md",
            "content": "问题树、假设驱动与 MECE",
            "source_type": "user_file",
            "updated_at": "2026-09-23T13:06:16+00:00",
            "link": "/app/?fileId=1",  # engine-internal; must not surface
        }
    )
    assert isinstance(doc.updated_at, datetime)

    item = to_engine_items([doc])[0]
    assert item.updated_at == datetime(2026, 9, 23, 13, 6, 16, tzinfo=UTC)
    # JSON view: an ISO 8601 string, i.e. what docs/API.md documents.
    assert item.model_dump(mode="json")["updated_at"] == "2026-09-23T13:06:16Z"


def test_engine_item_does_not_leak_engine_internal_fields() -> None:
    """`raw` (and the session-scoped `link` inside it) must never reach the API."""
    doc = _result_to_engine_document(
        {"citation_id": 9, "title": "t", "content": "c", "source_type": "user_file",
         "link": "/app/?fileId=9"}
    )
    dumped = to_engine_items([doc])[0].model_dump(mode="json")
    assert set(dumped) == set(ENGINE_FIELDS)
    assert "link" not in dumped
    assert "raw" not in dumped


# ---------------------------------------------------------------------------
# merge_engine — the four-state policy
# ---------------------------------------------------------------------------


def test_empty_query_is_skipped_and_never_touches_the_engine() -> None:
    """Opening the Library must not fire a retrieval."""
    stub = _StubEngine([_doc()])
    items, status = asyncio.run(merge_engine("", engine=stub))
    assert (items, status) == ([], "skipped")
    assert stub.search_calls == []


@pytest.mark.parametrize("blank", [None, "", "   ", "\t\n"])
def test_blank_query_is_skipped(blank: str | None) -> None:
    stub = _StubEngine([_doc()])
    items, status = asyncio.run(merge_engine(blank, engine=stub))
    assert (items, status) == ([], "skipped")
    assert stub.search_calls == []


@pytest.mark.parametrize("switch", [None, "mock", "MOCK", "something-else"])
def test_non_onyx_switch_is_disabled(monkeypatch: pytest.MonkeyPatch, switch: str | None) -> None:
    """Mock (explicit, default, or unknown-value fallback) is never real content.

    The mock adapter returns three canned documents that are NOT the customer's
    uploads; surfacing them as "recalled from your indexed documents" would be a
    lie, so the merge fails closed.
    """
    if switch is None:
        monkeypatch.delenv("ECE_CONTENT_ENGINE", raising=False)
    else:
        monkeypatch.setenv("ECE_CONTENT_ENGINE", switch)
    stub = _StubEngine([_doc()])
    # OEI-008: `engine_merge` reads `engine.engine_name` (not the env var) to
    # decide whether to short-circuit; force the stub to report a non-onyx name
    # so the test exercises the same code path it did pre-OEI-008.
    stub.engine_name = "mock"
    items, status = asyncio.run(merge_engine("问题树", engine=stub))
    assert (items, status) == ([], "disabled")
    assert stub.search_calls == []


def test_onyx_with_hits_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    stub = _StubEngine([_doc(doc_id="1")])
    items, status = asyncio.run(merge_engine("问题树怎么用", engine=stub))
    assert status == "ok"
    assert [i.engine_doc_id for i in items] == ["1"]
    assert stub.search_calls == [("问题树怎么用", DEFAULT_TOP_K)]


def test_onyx_with_no_hits_is_ok_not_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """'We asked and the answer was nothing' must not be confused with 'we did not ask'."""
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    items, status = asyncio.run(merge_engine("问题树怎么用", engine=_StubEngine([])))
    assert (items, status) == ([], "ok")


def test_engine_error_degrades_to_unavailable_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    stub = _StubEngine(error=EngineError("Onyx /api/search transport failure: boom"))
    items, status = asyncio.run(merge_engine("问题树怎么用", engine=stub))
    assert (items, status) == ([], "unavailable")


def test_top_k_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    stub = _StubEngine([_doc()])
    asyncio.run(merge_engine("问题树", engine=stub, top_k=3))
    assert stub.search_calls == [("问题树", 3)]


# ---------------------------------------------------------------------------
# Endpoint level — the static side must survive every engine outcome
# ---------------------------------------------------------------------------


def _library(client: TestClient, **params) -> dict:
    r = client.get("/api/v1/consulting/library", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_library_exposes_the_engine_group_in_onyx_mode(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    ts = datetime(2026, 9, 23, 13, 6, 16, tzinfo=UTC)
    stub = _StubEngine([_doc(doc_id="1", title="methodology-framework.md", snippet="问题树", updated_at=ts)])
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    monkeypatch.setattr(engine_merge, "get_content_engine", lambda: stub)

    body = _library(client, q="问题树怎么用")

    assert body["engine_status"] == "ok"
    assert len(body["engine_items"]) == 1
    item = EngineItem.model_validate(body["engine_items"][0])
    assert item.engine_doc_id == "1"
    assert item.source == "engine"
    assert item.updated_at == ts
    assert set(body) == set(STATIC_FIELDS) | {"engine_items", "engine_status"}


def test_library_static_fields_are_identical_when_the_engine_dies(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """A dead engine must cost the user the engine group and nothing else."""
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    monkeypatch.setattr(
        engine_merge, "get_content_engine", lambda: _StubEngine(error=EngineError("unreachable"))
    )
    degraded = _library(client, q="采购")

    monkeypatch.setenv("ECE_CONTENT_ENGINE", "mock")
    healthy_static = _library(client, q="采购")

    assert degraded["engine_status"] == "unavailable"
    assert degraded["engine_items"] == []
    for field in STATIC_FIELDS:
        assert degraded[field] == healthy_static[field], field


def test_library_defaults_to_disabled_without_a_live_engine(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.delenv("ECE_CONTENT_ENGINE", raising=False)
    body = _library(client, q="采购")
    assert (body["engine_status"], body["engine_items"]) == ("disabled", [])


def test_library_empty_query_is_skipped(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setenv("ECE_CONTENT_ENGINE", "onyx")
    stub = _StubEngine([_doc()])
    monkeypatch.setattr(engine_merge, "get_content_engine", lambda: stub)
    body = _library(client)
    assert (body["engine_status"], body["engine_items"]) == ("skipped", [])
    assert stub.search_calls == []
    # ...and the untouched static side still shows the whole catalogue.
    assert body["total"] == 36


# ---------------------------------------------------------------------------
# A8 — mock and onyx documents must produce the same shape (one model)
# ---------------------------------------------------------------------------


def test_mock_and_onyx_documents_map_to_the_same_shape() -> None:
    """Both engines' real document objects, mapped and validated by one model.

    Mock side: the live `MockContentEngineAdapter` (no network).
    Onyx side: the real `_result_to_engine_document` on a real payload shape
    (no network, no cookie).
    """
    mock_doc = asyncio.run(MockContentEngineAdapter().search("问题树"))[0]
    onyx_doc = _result_to_engine_document(
        {"citation_id": 1, "title": "methodology-framework.md", "content": "问题树",
         "source_type": "user_file", "updated_at": "2026-09-23T13:06:16+00:00"}
    )

    mock_json = to_engine_items([mock_doc])[0].model_dump(mode="json")
    onyx_json = to_engine_items([onyx_doc])[0].model_dump(mode="json")

    assert set(mock_json) == set(onyx_json) == set(ENGINE_FIELDS)
    for field in ENGINE_FIELDS:
        assert mock_json[field] is None or isinstance(mock_json[field], str), field
        assert onyx_json[field] is None or isinstance(onyx_json[field], str), field
    # ...and both survive the documented response model unchanged.
    assert EngineItem.model_validate(mock_json).source == "engine"
    assert EngineItem.model_validate(onyx_json).source == "engine"
