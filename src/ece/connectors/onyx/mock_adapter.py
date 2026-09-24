"""MockContentEngineAdapter — offline deterministic implementation (OEI-003 §4 步骤 3).

Default when ECE_CONTENT_ENGINE=mock (or unset). Lets /engine/status and the
rest of the system run without a live Onyx (CI, demos, demos on a fresh laptop).

OEI-007 adds write-path methods (`upload_document` / `document_status`). The mock
implements them as a **module-level** in-memory store: every upload gets a
deterministic `mock-NNNN` id and goes straight to COMPLETED with `chunk_count=1`
so the closed-loop / upload → wait → recall flow can be exercised without Onyx.

Module-level (not instance) state is intentional: `get_content_engine()` returns
a fresh adapter each call, but a poll-after-upload flow must see the same store.
This mirrors the live adapter (the *data* lives in Onyx's process, not in our
adapter object). Tests reset the store explicitly via `reset_mock_engine_store()`.

Note (deliberate): the mock does NOT try to plug uploaded docs back into `search()`.
Doing so would either silently mix customer uploads into the canned catalogue (a
contract violation — OEI-006 §4 step 2 `disabled` semantics) or need a separate
"the mock also indexes this" channel. The consulting layer is responsible for the
`ECE_CONTENT_ENGINE=mock` short-circuit that already gates real recall.
"""
from __future__ import annotations

import time
from typing import Any

from ece.connectors.onyx.port import (
    ContentEnginePort,
    EngineDocument,
    EngineDocumentStatus,
    EngineError,
    EngineProject,
    EngineStatus,
)

_MOCK_PROJECTS: list[EngineProject] = [
    EngineProject(
        engine_project_id=1,
        name="OEI-001 Consulting Lab",
        raw={"source": "mock"},
    ),
    EngineProject(
        engine_project_id=2,
        name="Knowledge Management Demo",
        raw={"source": "mock"},
    ),
]

_MOCK_DOCS_BY_PROJECT: dict[int, list[EngineDocument]] = {
    1: [
        EngineDocument(
            engine_doc_id="mock-1-methodology",
            title="methodology-framework.md",
            snippet=(
                "[Mock] 问题树 / 假设驱动 / MECE 的实战组合(Demo Case) — "
                "consulting methodology for issue tree, hypothesis-driven, MECE."
            ),
            source_type="user_file",
            updated_at=None,
            raw={"mock": True, "project_id": 1},
        ),
        EngineDocument(
            engine_doc_id="mock-1-case",
            title="case-management-consulting.md",
            snippet=(
                "[Mock] 某零售集团供应链降本管理咨询案例 — "
                "background / problem / method / delivery / results."
            ),
            source_type="user_file",
            updated_at=None,
            raw={"mock": True, "project_id": 1},
        ),
        EngineDocument(
            engine_doc_id="mock-1-play",
            title="play-sales-delivery.md",
            snippet=(
                "[Mock] 销售→交付衔接五阶段 play — "
                "stages, actions, deliverables, responsibilities."
            ),
            source_type="user_file",
            updated_at=None,
            raw={"mock": True, "project_id": 1},
        ),
    ],
    2: [],
}


# Module-level write-path store (see module docstring).
_MOCK_UPLOADS: dict[str, EngineDocumentStatus] = {}
_MOCK_UPLOAD_SEQ: int = 0


def reset_mock_engine_store() -> None:
    """Drop all mock write-path state. Used by tests to keep cases isolated."""
    _MOCK_UPLOADS.clear()
    global _MOCK_UPLOAD_SEQ
    _MOCK_UPLOAD_SEQ = 0


class MockContentEngineAdapter:
    """Deterministic, in-memory engine adapter.

    - search(): returns the project-1 docs (3) if query matches any of their
      keywords, else the full project-1 list (mock engines always have something).
    - engine_status(): returns hardcoded snapshot with last_search_latency_seconds
      updated each call.
    - list_projects(): returns _MOCK_PROJECTS.
    - upload_document() (OEI-007): stores a record in the module-level store
      and returns it as a COMPLETED `EngineDocumentStatus`.
    - document_status() (OEI-007): reads from the module-level store.
    """

    def __init__(self) -> None:
        self._last_latency: float | None = None

    async def search(
        self, query: str, *, top_k: int | None = None
    ) -> list[EngineDocument]:
        start = time.perf_counter()
        # simulate ~50ms "engine work" so latency is non-zero
        time.sleep(0.05)
        # deterministic: query length influences number of results
        all_docs = _MOCK_DOCS_BY_PROJECT[1]
        if top_k is not None:
            results = all_docs[: max(1, min(top_k, len(all_docs)))]
        else:
            results = all_docs
        # record latency as float seconds
        self._last_latency = time.perf_counter() - start
        return list(results)

    async def engine_status(self) -> EngineStatus:
        all_docs = sum(len(v) for v in _MOCK_DOCS_BY_PROJECT.values())
        return EngineStatus(
            engine_name="mock",
            engine_version="0.1.0",
            tier="community",
            gpu_enabled=False,
            provider_name=None,
            default_model=None,
            project_count=len(_MOCK_PROJECTS),
            file_count=all_docs,
            last_search_latency_seconds=self._last_latency,
            raw={"mock": True},
        )

    async def list_projects(self) -> list[EngineProject]:
        return list(_MOCK_PROJECTS)

    # -- OEI-007 write path (deterministic, offline) --------------------------

    async def upload_document(
        self,
        filename: str,
        content: bytes,
        *,
        project_id: int,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EngineDocumentStatus:
        if not isinstance(content, (bytes, bytearray)):
            raise EngineError(
                f"mock upload requires bytes, got {type(content).__name__}"
            )
        global _MOCK_UPLOAD_SEQ
        _MOCK_UPLOAD_SEQ += 1
        doc_id = f"mock-{_MOCK_UPLOAD_SEQ:06d}"
        # Deterministic within a process: counter monotonic across the whole
        # process lifetime (so the same upload run by the same code twice gets
        # different doc_ids, just like Onyx would — UUIDs not integers there).
        record = EngineDocumentStatus(
            document_id=doc_id,
            name=filename or "document",
            status="COMPLETED",
            chunk_count=1,
            project_id=int(project_id),
            failure_reason=None,
            raw={
                "mock": True,
                "bytes": len(content),
                "ece_title": title,
                "ece_metadata": dict(metadata) if metadata else {},
            },
        )
        _MOCK_UPLOADS[doc_id] = record
        return record

    async def document_status(self, document_id: str) -> EngineDocumentStatus:
        rec = _MOCK_UPLOADS.get(document_id)
        if rec is None:
            raise EngineError(f"mock document_status: id={document_id!r} not found")
        # return a copy so callers can't mutate the store by accident
        return rec.model_copy(deep=True)


# Runtime checkable assertion: MockContentEngineAdapter structurally conforms
assert isinstance(MockContentEngineAdapter(), ContentEnginePort)  # type: ignore[abstract]
