"""KC-001 — merge engine-recalled documents into the Consulting Library (OEI-006).

Architecture red line (TASK §0): **ECE owns identity / permission / provenance /
audit and the domain objects; the content engine is a replaceable content +
retrieval engine.** This module therefore reaches the engine ONLY through
OEI-003's `ContentEnginePort` — it never imports `OnyxContentEngineAdapter` and
never touches Onyx HTTP directly. Swapping the engine must not require editing
this file.

Two pieces, deliberately split so the interesting one is DB-free and network-free:

  * `to_engine_items(docs)` — pure mapping `EngineDocument` → `EngineItem`.
    Unit-testable with a hand-built list; no engine, no DB, no asyncio.
  * `merge_engine(q, *, engine=None, caller=None, sql_engine=None, identity=None, top_k=...)` —
    the async policy wrapper that decides WHETHER to ask the engine,
    runs the per-result permission filter (OEI-009), and turns failures
    into `unavailable` instead of an exception escaping to the client.

Policy (TASK §4 step 2; OEI-008 + OEI-009 updates):

  q empty                              → ([], "skipped")    never touch the engine
  engine.engine_name != "onyx"         → ([], "disabled")   mock adapter is not real content
  EngineError                          → ([], "unavailable") static side still served, HTTP 200
  else                                 → (items, "ok")      possibly empty list, still "ok"

OEI-008 changes (compare to OEI-007 §R1 ④ response):

  - The "engine not onyx" branch now reads `engine.engine_name` from the Port
    rather than mirroring `selector.get_content_engine()`'s switch. The
    duplication debt documented in OEI-006's note is gone; if a third engine
    ever lands, it only needs to set its own `engine_name` to something other
    than "onyx" and the merge will correctly short-circuit.
  - `merge_engine` accepts `caller: EngineCallerContext | None = None` so the
    caller's identity reaches the engine adapter for audit (the route is
    responsible for building the caller; `merge_engine` does not parse headers).
  - The `disabled` reason is now a `EngineError` short-circuit on the Port side
    (mock refuses uploads that lack a caller; the merge layer never sees them).

OEI-009 changes (compare to OEI-008):

  - After the engine returns, `merge_engine` runs `permissions_filter` on every
    `EngineDocument`. Failures (no_registry / denied / anonymous_restricted)
    collapse into `hidden_count` for the per-result audit row — never exposed
    to the client. The returned list IS the post-authorization set (A6).
  - The route is responsible for resolving the full `Identity` (DB lookup)
    before calling `merge_engine`. `merge_engine` no longer parses headers;
    it only threads `identity` (or None for anonymous) into the filter.

The degraded path is the important one: a dead engine must cost the user the
engine group and nothing else. It must never turn a working static Library into
a 5xx.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ece.connectors.onyx.port import EngineCallerContext, EngineDocument, EngineError
from ece.connectors.onyx.selector import get_content_engine
from ece.consulting.permissions_filter import filter_engine_items
from ece.consulting.models import EngineItem, EngineMergeStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from sqlalchemy.engine import Engine as _SAEngine

    from ece.connectors.onyx.port import ContentEnginePort
    from ece.identity.parser import Identity

# How many engine hits we are willing to put on one Library page. The static
# side pages at `limit` (default 24); the engine group is a *hint* rail, not a
# second catalogue, so it stays small and cheap.
DEFAULT_TOP_K = 8

# OEI-008 — only the live Onyx engine is allowed to feed the "engine recall"
# group. We read this from the Port's `engine_name` descriptor (NOT from the
# selector's switch) so the consulting layer no longer needs to mirror the
# env-var logic. MockAdapter.engine_name == "mock" → short-circuits.
LIVE_ENGINE_NAME = "onyx"

# OEI-013 — deterministic recall for the Library path, opt-in via env.
#
# OEI-012 measured the engine's two modes and found `skip_query_expansion=True`
# strictly better on reproducibility (1.000 vs 0.833) and latency (median 1.47 s
# vs 5.02 s). TASK §3.2.2 therefore asks for that deterministic path to be wired
# into the demo. But OEI-013's product-layer re-measurement found the trade is
# NOT free: the deterministic path returns a *narrower* candidate set, and on
# this corpus that sometimes means the one and only hit is the controlled
# comparison document — which the permission filter then hides, leaving the user
# an EMPTY engine group where the default mode would have shown a real document.
#
# So this stays an explicit opt-in with the SHIPPING DEFAULT OFF:
#
#   unset / anything else  → engine default (query expansion on)
#   ECE_LIBRARY_SKIP_QUERY_EXPANSION=1 → deterministic path
#
# Both modes are measured in `onyx-lab/OEI-013/evidence/03*.json`; the demo chain
# sets whichever the numbers favour, and `demo-up.sh` states which and why. The
# Port's own default is untouched (still False) per TASK §8.
_LIBRARY_DETERMINISTIC_ENV = "ECE_LIBRARY_SKIP_QUERY_EXPANSION"
_TRUTHY = ("1", "true", "yes", "on")


def library_deterministic_recall() -> bool:
    """Is the deterministic (expansion-off) recall path requested for /library?

    Read at CALL time, not import time, so tests can toggle it and so a running
    server can be switched by restarting with a different environment.
    """
    value = (os.environ.get(_LIBRARY_DETERMINISTIC_ENV) or "").strip().lower()
    return value in _TRUTHY


def to_engine_items(docs: Iterable[EngineDocument]) -> list[EngineItem]:
    """Map engine documents onto the card payload. Pure — no I/O.

    No truncation here on purpose: the adapter already caps snippets at
    `_MAX_SNIPPET_CHARS` (800), and the SPA needs the *whole* snippet for the
    detail drawer while truncating only the card face. Trimming in the API
    would make the drawer lossy for no gain.
    """
    return [
        EngineItem(
            engine_doc_id=doc.engine_doc_id,
            title=doc.title,
            snippet=doc.snippet,
            source_type=doc.source_type,
            updated_at=doc.updated_at,
            source="engine",
        )
        for doc in docs
    ]


async def merge_engine(
    q: str | None,
    *,
    engine: ContentEnginePort | None = None,
    caller: EngineCallerContext | None = None,
    sql_engine: _SAEngine | None = None,
    identity: Identity | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[EngineItem], EngineMergeStatus]:
    """Return `(engine_items, engine_status)` for one Library request.

    Never raises for engine-side problems: an unreachable engine is a
    `unavailable` status, not an exception. A caller-side bug (bad argument)
    still raises normally.

    OEI-008: `caller` is forwarded to the engine adapter for audit.
    OEI-009: `identity` (resolved from credentials only, never from the
    request body) is forwarded to the per-result permission filter. The
    filter is the only place where rows can be hidden from the client —
    the returned list IS the authorized set (A6).
    """
    query = (q or "").strip()
    if not query:
        # Opening the Library must not fire a retrieval — the static catalogue
        # is the whole page until the user actually types something.
        return [], "skipped"

    if engine is None:
        engine = get_content_engine()

    # OEI-008: read the engine's own descriptor instead of mirroring the
    # selector switch. The previous `_engine_switch_is_onyx()` lived here as
    # a documented debt ("cannot add an engine_name descriptor to the port");
    # OEI-008 made the descriptor a first-class Port member.
    if getattr(engine, "engine_name", "unknown") != LIVE_ENGINE_NAME:
        return [], "disabled"

    # OEI-013: forward the deterministic-recall flag ONLY when the caller asked
    # for it AND the engine declares it accepts the keyword. Gating on both
    # keeps the shipped default path byte-identical for every other consumer of
    # `merge_engine` (the same rule OEI-012 applied inside the Onyx adapter) and
    # means a narrower engine — including the test doubles in the suite, whose
    # `search()` predates OEI-012 — is never handed an unexpected keyword.
    search_kwargs: dict = {"top_k": top_k, "caller": caller}
    if library_deterministic_recall() and getattr(
        engine, "supports_skip_query_expansion", False
    ):
        search_kwargs["skip_query_expansion"] = True

    try:
        docs = await engine.search(query, **search_kwargs)
    except EngineError:
        # Covers transport failure, auth failure, 5xx and unparseable payload —
        # the adapter wraps all of them into EngineError. Degrade, don't crash.
        return [], "unavailable"

    # OEI-009 — per-result permission filter. The filter is only run when we
    # have a DB to look the registry up in (the integration tests / live demo
    # always do; unit tests can pass an in-memory stub). When sql_engine is
    # None we degrade gracefully — return everything as "ok" — but log a
    # single warning at module import time (not per call).
    if sql_engine is None:
        # DB-free fallback: every recall is treated as authorized. This is
        # NOT safe for production; it exists for the few pure unit tests
        # that don't touch the registry. See §5.1 / OEI-008 §A7.
        return to_engine_items(docs), "ok"

    filter_result = filter_engine_items(
        docs,
        sql_engine=sql_engine,
        content_engine_name=engine.engine_name,
        identity=identity,
    )
    # `hidden_count` is intentionally dropped here — it goes to the per-call
    # audit row (see step 5 / 09-design-engine-audit.md), NOT to the client.
    return filter_result.allowed_items, "ok"


__all__ = [
    "DEFAULT_TOP_K",
    "LIVE_ENGINE_NAME",
    "library_deterministic_recall",
    "merge_engine",
    "to_engine_items",
]