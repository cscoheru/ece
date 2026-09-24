"""ContentEnginePort — Protocol + Pydantic models (OEI-003 §4 步骤 2).

Three methods:
- search(query, *, top_k=None) -> list[EngineDocument]
- engine_status() -> EngineStatus
- list_projects() -> list[EngineProject]

分层纪律:Onyx 专有字段(citation_id / source_type:user_file / 等)只能活在 adapter
内部,Port 与统一返回模型(Pydantic)零依赖 Onyx。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field


class EngineDocument(BaseModel):
    """A single recalled document chunk from the engine.

    `raw` carries engine-specific fields (e.g. Onyx citation_id, semantic_identifier)
    so adapters don't need to redefine the schema for every engine.
    """

    engine_doc_id: str = Field(..., description="engine-stable doc identifier (uuid or hash)")
    title: str = Field(..., description="human-readable document title")
    snippet: str = Field(..., description="text snippet used for display (truncated)")
    source_type: str = Field(..., description="origin type tag (e.g. user_file, web)")
    updated_at: datetime | None = Field(default=None, description="last update timestamp from engine")
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="engine-specific extras (citation_id, semantic_identifier, link, etc.)",
    )


class EngineProject(BaseModel):
    """A project/workspace on the engine (e.g. Onyx user project)."""

    engine_project_id: int = Field(..., description="engine-side integer project id")
    name: str = Field(..., description="project name")
    raw: dict[str, Any] = Field(default_factory=dict, description="engine-specific extras")


class EngineStatus(BaseModel):
    """Snapshot of engine runtime state."""

    engine_name: str = Field(..., description="engine identifier, e.g. 'onyx'")
    engine_version: str = Field(..., description="engine version string")
    tier: str = Field(..., description="engine tier, e.g. 'community' or 'enterprise'")
    gpu_enabled: bool = Field(default=False, description="GPU embedding acceleration on")
    provider_name: str | None = Field(default=None, description="default LLM provider name if any")
    default_model: str | None = Field(default=None, description="default LLM model name if any")
    project_count: int = Field(default=0, description="number of projects on engine")
    file_count: int = Field(default=0, description="number of files in primary project if known")
    last_search_latency_seconds: float | None = Field(
        default=None,
        description="most recent search latency (seconds); None if no search yet",
    )
    raw: dict[str, Any] = Field(default_factory=dict, description="engine-specific extras")


class EngineError(RuntimeError):
    """Raised when the engine is unreachable / returns a non-recoverable error.

    Port callers (including /engine/status page) must translate this into a
    structured degraded response — NOT 500 naked crash.
    """


@runtime_checkable
class ContentEnginePort(Protocol):
    """Abstract port to a content + search engine.

    Implementations: OnyxContentEngineAdapter (real), MockContentEngineAdapter (offline).
    """

    async def search(self, query: str, *, top_k: int | None = None) -> list[EngineDocument]:
        """Run a search query and return up to top_k documents (engine's default if None).

        MUST NOT raise on empty results — return [] instead.
        MUST raise EngineError on transport / HTTP / parsing failures.
        """
        ...

    async def engine_status(self) -> EngineStatus:
        """Return current engine state snapshot.

        MUST raise EngineError if engine is unreachable.
        """
        ...

    async def list_projects(self) -> list[EngineProject]:
        """List all projects on the engine.

        MUST raise EngineError on transport failure.
        """
        ...
