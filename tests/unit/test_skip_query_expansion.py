"""OEI-012 §A4/A6/A7 — `skip_query_expansion` plumbing (DB-free, no network).

What this file proves, and how:

  1. The real adapter actually puts `skip_query_expansion` **on the wire body**
     when True, and **omits it entirely** when False. A bare signature check
     would pass even if the flag were accepted and then dropped on the floor;
     the httpx MockTransport handler captures the real outgoing request, so
     this is a wire-level assertion, not a signature assertion.
  2. Mock and Onyx adapters expose the **same** `search()` parameter list
     (A6 "mock 与 onyx 签名同构"), so `ECE_CONTENT_ENGINE=mock` cannot hide a
     divergence in the request-controllable surface.
  3. The port Protocol declares the flag with default `False` — i.e. no
     call-site is forced to opt in (A4 "默认 False，无没有数字支撑的默认翻转").
  4. Existing `search()` contract is untouched by the new parameter: empty
     results still return `[]` (never raise), and transport failures still
     raise `EngineError` (A6 "合约不回归").

No postgres, no Onyx, no cookie: `httpx.MockTransport` handles the request in
process. Runs under the plain `make test` selection.
"""
from __future__ import annotations

import asyncio
import inspect
import json

import httpx
import pytest

from ece.connectors.onyx.mock_adapter import MockContentEngineAdapter
from ece.connectors.onyx.onyx_adapter import OnyxContentEngineAdapter
from ece.connectors.onyx.port import ContentEnginePort, EngineError


def _ok_payload() -> dict:
    """Minimal Onyx /api/search success body (matches OEI-002 field names)."""
    return {
        "results": [
            {
                "citation_id": "c1",
                "title": "案例管理咨询方法论",
                "content": "问题树 + MECE 拆解。",
                "source_type": "file",
                "updated_at": None,
            },
        ],
    }


def _stub_adapter(captured: list[httpx.Request], *, status: int = 200,
                  payload: dict | None = None,
                  raiser: Exception | None = None) -> OnyxContentEngineAdapter:
    """Build an OnyxContentEngineAdapter whose HTTP layer is in-process.

    `captured` collects every request the adapter emits, so tests can assert on
    the exact JSON body. Nothing here opens a socket or a database connection.
    """
    adapter = OnyxContentEngineAdapter(base_url="http://stub.invalid")

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if raiser is not None:
            raise raiser
        return httpx.Response(status, json=payload if payload is not None else _ok_payload())

    def _fake_client() -> httpx.Client:
        return httpx.Client(base_url="http://stub.invalid",
                            transport=httpx.MockTransport(handler))

    adapter._client = _fake_client  # type: ignore[method-assign]
    return adapter


# --- 1. wire-level proof ----------------------------------------------------


def test_flag_true_is_put_on_the_request_body() -> None:
    captured: list[httpx.Request] = []
    adapter = _stub_adapter(captured)

    docs = asyncio.run(adapter.search("问题树", skip_query_expansion=True))

    assert len(captured) == 1
    body = json.loads(captured[0].content.decode("utf-8"))
    assert body["skip_query_expansion"] is True
    assert body["query"] == "问题树"
    assert docs and docs[0].title == "案例管理咨询方法论"


def test_flag_false_omits_the_field_entirely() -> None:
    """Default call must be byte-identical to pre-OEI-012 traffic.

    Omitting (rather than sending False) means an engine that never knew the
    field sees exactly the request it saw before this cut.
    """
    captured: list[httpx.Request] = []
    adapter = _stub_adapter(captured)

    asyncio.run(adapter.search("问题树"))

    body = json.loads(captured[0].content.decode("utf-8"))
    assert "skip_query_expansion" not in body


def test_flag_recorded_in_audit_log_both_ways() -> None:
    captured: list[httpx.Request] = []
    adapter = _stub_adapter(captured)

    asyncio.run(adapter.search("q1", skip_query_expansion=True))
    asyncio.run(adapter.search("q2"))

    flags = [row["skip_query_expansion"] for row in adapter.audit_log]
    assert flags == [True, False]


# --- 2. adapter signature isomorphism (A6) ---------------------------------


def _search_params(cls: type) -> list[tuple[str, object]]:
    sig = inspect.signature(cls.search)
    return [
        (name, p.default)
        for name, p in sig.parameters.items()
        if name != "self"
    ]


def test_mock_and_onyx_search_signatures_are_isomorphic() -> None:
    assert _search_params(MockContentEngineAdapter) == _search_params(OnyxContentEngineAdapter)


def test_both_adapters_default_the_flag_to_false() -> None:
    expected = [
        ("query", inspect.Parameter.empty),
        ("top_k", None),
        ("caller", None),
        ("skip_query_expansion", False),
    ]
    assert _search_params(MockContentEngineAdapter) == expected
    assert _search_params(OnyxContentEngineAdapter) == expected


# --- 3. port Protocol declaration (A4) -------------------------------------


def test_port_protocol_declares_flag_defaulting_to_false() -> None:
    params = dict(_search_params(ContentEnginePort))
    assert params["skip_query_expansion"] is False


def test_mock_records_flag_and_keeps_fixture_results_stable() -> None:
    """Mock result set is corpus-independent, so the flag must not move it."""
    m = MockContentEngineAdapter()
    on = asyncio.run(m.search("问题树", skip_query_expansion=True))
    off = asyncio.run(m.search("问题树", skip_query_expansion=False))
    assert [d.title for d in on] == [d.title for d in off]
    assert m.audit_log[-1]["skip_query_expansion"] is False
    assert m.audit_log[-2]["skip_query_expansion"] is True


# --- 4. contract non-regression (A6) ---------------------------------------


def test_empty_results_still_return_empty_list_not_raise() -> None:
    captured: list[httpx.Request] = []
    adapter = _stub_adapter(captured, payload={"results": []})

    docs = asyncio.run(adapter.search("没有命中", skip_query_expansion=True))

    assert docs == []


@pytest.mark.parametrize("status", [500, 503])
def test_server_error_still_raises_engine_error_with_flag_on(status: int) -> None:
    adapter = _stub_adapter([], status=status, payload={"detail": "boom"})

    with pytest.raises(EngineError):
        asyncio.run(adapter.search("q", skip_query_expansion=True))


def test_transport_failure_still_raises_engine_error_with_flag_on() -> None:
    adapter = _stub_adapter([], raiser=httpx.ConnectError("no route"))

    with pytest.raises(EngineError):
        asyncio.run(adapter.search("q", skip_query_expansion=True))


def test_auth_failure_still_raises_engine_error_with_flag_on() -> None:
    adapter = _stub_adapter([], status=401, payload={"detail": "unauthorized"})

    with pytest.raises(EngineError):
        asyncio.run(adapter.search("q", skip_query_expansion=True))
