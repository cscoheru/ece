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
  * `merge_engine(q, *, engine=None)` — the async policy wrapper that decides
    WHETHER to ask the engine and turns failures into `unavailable` instead of
    an exception escaping to the client.

Policy (mirrors TASK §4 step 2):

  q empty               → ([], "skipped")     never touch the engine
  engine not `onyx`     → ([], "disabled")    mock adapter is not real content
  EngineError           → ([], "unavailable") static side still served, HTTP 200
  else                  → (items, "ok")       possibly empty list, still "ok"

The degraded path is the important one: a dead engine must cost the user the
engine group and nothing else. It must never turn a working static Library into
a 5xx.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ece.connectors.onyx.port import EngineDocument, EngineError
from ece.connectors.onyx.selector import get_content_engine
from ece.consulting.models import EngineItem, EngineMergeStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

    from ece.connectors.onyx.port import ContentEnginePort

# How many engine hits we are willing to put on one Library page. The static
# side pages at `limit` (default 24); the engine group is a *hint* rail, not a
# second catalogue, so it stays small and cheap.
DEFAULT_TOP_K = 8


def _engine_switch_is_onyx() -> bool:
    """True only when the selector would build the live Onyx adapter.

    This mirrors the switch in `connectors/onyx/selector.get_content_engine()`
    *verbatim* (including "unknown value falls back to mock"), because OEI-006
    §7's write-permission whitelist does not include `src/ece/connectors/onyx/**`
    — so we cannot add an `engine_name` descriptor to the port and ask the
    adapter what it is. Duplicating one env read is the price; the divergence
    risk is bounded by mirroring the expression exactly rather than
    "improving" it (no `.strip()`, no case folding beyond what the selector
    does), and by failing CLOSED: any value that is not exactly `onyx` is
    treated as mock, which hides the engine group rather than showing the mock
    adapter's canned documents as if they were the customer's own uploads.
    """
    return (os.environ.get("ECE_CONTENT_ENGINE") or "mock").lower() == "onyx"


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
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[EngineItem], EngineMergeStatus]:
    """Return `(engine_items, engine_status)` for one Library request.

    Never raises for engine-side problems: an unreachable engine is a
    `unavailable` status, not an exception. A caller-side bug (bad argument)
    still raises normally.
    """
    query = (q or "").strip()
    if not query:
        # Opening the Library must not fire a retrieval — the static catalogue
        # is the whole page until the user actually types something.
        return [], "skipped"

    if not _engine_switch_is_onyx():
        return [], "disabled"

    if engine is None:
        engine = get_content_engine()

    try:
        docs = await engine.search(query, top_k=top_k)
    except EngineError:
        # Covers transport failure, auth failure, 5xx and unparseable payload —
        # the adapter wraps all of them into EngineError. Degrade, don't crash.
        return [], "unavailable"

    return to_engine_items(docs), "ok"


__all__ = ["DEFAULT_TOP_K", "merge_engine", "to_engine_items"]
