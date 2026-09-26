"""OEI-013 — the Library recall-mode gate (`ECE_LIBRARY_SKIP_QUERY_EXPANSION`).

`merge_engine` gained one conditional keyword in OEI-013. It is small, and that
is exactly why it needs pinning: it is the ONLY thing separating the demo's two
measured recall modes, and a silent change to it would flip the product-layer
numbers in `onyx-lab/OEI-013/evidence/03*.json` without any test going red.

The design is a TWO-gate AND:

    library_deterministic_recall()  and  engine.supports_skip_query_expansion

Both gates are tested independently, because each one alone would be a bug:

  * gate 1 alone → narrower engines (including the suite's own test doubles,
    whose `search()` signature predates OEI-012) get an unexpected kwarg and
    raise TypeError at request time. That is the failure the second gate exists
    to prevent, and it is why no existing assertion had to change for OEI-013.
  * gate 2 alone → the deterministic path would be on by default, contradicting
    the shipping default the product-layer numbers chose.

The env is read at CALL time, not import time. There is a specific reason: the
first version of this code cached it at module import, which made a mode switch
require a process restart AND made it untestable without `importlib.reload`.
These tests would fail against that version.
"""
from __future__ import annotations

import asyncio

import pytest

from ece.connectors.onyx.port import EngineCallerContext, EngineDocument
from ece.consulting import engine_merge
from ece.consulting.engine_merge import library_deterministic_recall, merge_engine

ENV = "ECE_LIBRARY_SKIP_QUERY_EXPANSION"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts from the shipped default (unset → engine default)."""
    monkeypatch.delenv(ENV, raising=False)


class _RecordingEngine:
    """Minimal Port double that records the kwargs its `search` was handed.

    Deliberately NOT built on MockAdapter: the point is to observe the exact
    call, and to control `supports_skip_query_expansion` independently of the
    real adapters' values.
    """

    engine_name = "onyx"          # must pass the LIVE_ENGINE_NAME gate

    def __init__(self, *, supports: bool = True) -> None:
        self.supports_skip_query_expansion = supports
        self.calls: list[dict] = []

    async def search(self, query: str, **kwargs) -> list[EngineDocument]:
        self.calls.append({"query": query, **kwargs})
        return []


def _run(engine: _RecordingEngine) -> list[dict]:
    """Call `merge_engine` once and return only the calls it just made.

    Returns the DELTA, not `engine.calls` — `test_the_env_is_read_at_call_time`
    drives the same engine three times and would otherwise see an accumulating
    list and silently assert against the wrong call.
    """
    before = len(engine.calls)
    # sql_engine=None → the DB-free fallback path, so no registry is needed.
    asyncio.run(merge_engine("诊断", engine=engine))
    return engine.calls[before:]


# ---- the descriptor ---------------------------------------------------------

def test_descriptor_is_exported() -> None:
    assert "library_deterministic_recall" in engine_merge.__all__


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", " 1 "])
def test_truthy_values_request_deterministic_recall(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV, value)
    assert library_deterministic_recall() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "2", "yes please"])
def test_everything_else_is_the_engine_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(ENV, value)
    assert library_deterministic_recall() is False


def test_default_when_unset_is_the_engine_default() -> None:
    """The shipped default. OEI-013 measured it as the better product-layer
    trade (hit@3 80% vs 0% on the rewrite path), so it must stay off."""
    assert library_deterministic_recall() is False


# ---- gate 1: is the flag read, and is it read at CALL time? -----------------

def test_off_by_default_sends_no_flag() -> None:
    engine = _RecordingEngine()
    (call,) = _run(engine)
    assert "skip_query_expansion" not in call
    assert call["top_k"] == engine_merge.DEFAULT_TOP_K


def test_on_with_a_supporting_engine_sends_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV, "1")
    engine = _RecordingEngine(supports=True)
    (call,) = _run(engine)
    assert call["skip_query_expansion"] is True


def test_the_env_is_read_at_call_time_not_import_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Toggling the env between two calls must change both calls.

    A module-import-time cache would make the second call repeat the first."""
    engine = _RecordingEngine()

    (first,) = _run(engine)
    assert "skip_query_expansion" not in first

    monkeypatch.setenv(ENV, "1")
    (second,) = _run(engine)
    assert second["skip_query_expansion"] is True

    monkeypatch.delenv(ENV)
    (third,) = _run(engine)
    assert "skip_query_expansion" not in third


# ---- gate 2: engines that never opted in ------------------------------------

def test_engine_without_the_descriptor_never_receives_the_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate that kept every existing test double working unchanged.

    With the env ON, a narrow engine (no `supports_skip_query_expansion`
    attribute at all) must still be called with the original signature."""
    monkeypatch.setenv(ENV, "1")
    engine = _RecordingEngine()
    del engine.supports_skip_query_expansion       # an older/narrower engine
    (call,) = _run(engine)
    assert "skip_query_expansion" not in call
    assert library_deterministic_recall() is True   # ...even though the env said yes


def test_engine_declaring_false_never_receives_the_kwarg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declaring the capability as False must behave like not having it."""
    monkeypatch.setenv(ENV, "1")
    engine = _RecordingEngine(supports=False)
    (call,) = _run(engine)
    assert "skip_query_expansion" not in call


# ---- the gates that were already there must still gate ----------------------

def test_empty_query_never_reaches_the_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV, "1")
    engine = _RecordingEngine()
    items, status = asyncio.run(merge_engine("   ", engine=engine))
    assert (items, status) == ([], "skipped")
    assert engine.calls == []


def test_non_onyx_engine_short_circuits_before_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV, "1")
    engine = _RecordingEngine()
    engine.engine_name = "mock"
    items, status = asyncio.run(merge_engine("诊断", engine=engine))
    assert (items, status) == ([], "disabled")
    assert engine.calls == []


def test_caller_is_always_threaded_through() -> None:
    """OEI-013 must not have disturbed OEI-008's audit thread-through."""
    engine = _RecordingEngine()
    caller = EngineCallerContext(user_ref="demo-user", source="test")
    asyncio.run(merge_engine("诊断", engine=engine, caller=caller))
    assert engine.calls[0]["caller"] is caller
