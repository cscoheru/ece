"""MockContentEngineAdapter — offline deterministic implementation (OEI-003 §4 步骤 3).

Default when ECE_CONTENT_ENGINE=mock (or unset). Lets /engine/status and the
rest of the system run without a live Onyx (CI, demos, demos on a fresh laptop).
"""
from __future__ import annotations

import time

from ece.connectors.onyx.port import (
    ContentEnginePort,
    EngineDocument,
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


class MockContentEngineAdapter:
    """Deterministic, in-memory engine adapter.

    - search(): returns the project-1 docs (3) if query matches any of their
      keywords, else the full project-1 list (mock engines always have something).
    - engine_status(): returns hardcoded snapshot with last_search_latency_seconds
      updated each call.
    - list_projects(): returns _MOCK_PROJECTS.
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


# Runtime checkable assertion: MockContentEngineAdapter structurally conforms
assert isinstance(MockContentEngineAdapter(), ContentEnginePort)  # type: ignore[abstract]
