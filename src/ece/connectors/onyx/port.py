"""ContentEnginePort — Protocol + Pydantic models (OEI-003 §4 步骤 2).

Three read methods (OEI-003):
- search(query, *, top_k=None) -> list[EngineDocument]
- engine_status() -> EngineStatus
- list_projects() -> list[EngineProject]

Two write methods (OEI-007):
- upload_document(filename, content: bytes, *, project_id, title=None, metadata=None) -> EngineDocumentStatus
- document_status(document_id: str) -> EngineDocumentStatus

分层纪律:Onyx 专有字段(citation_id / source_type:user_file / 等)只能活在 adapter
内部,Port 与统一返回模型(Pydantic)零依赖 Onyx。

Note: OEI-007 deliberately keeps `engine_doc_id` on `EngineDocument` (the search-side
identifier, set from Onyx `citation_id` for each recall) SEPARATE from `document_id`
on `EngineDocumentStatus` (the upload-side identifier, set from Onyx `user_file.id`).
They live in different namespaces — see `OnyxContentEngineAdapter.upload_document` for
the mapping notes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

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


# OEI-007 — write-path models ----------------------------------------------------

# Status values mirror Onyx /api/user/projects/file/statuses response exactly so
# the consulting layer can show "waiting → ready / failed" without parsing.
EngineDocumentPhaseT = Literal["PROCESSING", "COMPLETED", "FAILED"]


class EngineDocumentStatus(BaseModel):
    """Status of a document previously submitted via `upload_document`.

    `document_id` is the engine-side identifier returned by upload (Onyx
    `user_file.id`, a UUID). It is deliberately a different namespace from
    `EngineDocument.engine_doc_id` (the per-search citation id).
    """

    document_id: str = Field(..., description="Engine-side identifier (Onyx user_file.id, UUID).")
    name: str = Field(..., description="Original filename at upload time.")
    status: EngineDocumentPhaseT = Field(..., description="Indexing lifecycle state.")
    chunk_count: int | None = Field(default=None, description="Indexed chunk count; null while PROCESSING or on FAILED.")
    project_id: int | None = Field(default=None, description="Project this document belongs to.")
    failure_reason: str | None = Field(
        default=None, description="When status=FAILED, the engine-supplied reason if any."
    )
    raw: dict[str, Any] = Field(default_factory=dict, description="engine-specific extras")


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

    async def upload_document(
        self,
        filename: str,
        content: bytes,
        *,
        project_id: int,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EngineDocumentStatus:
        """Upload a document to the engine and return its initial status.

        `content` is the raw file bytes (the engine does the text extraction).
        `metadata` is engine-shaped advisory data — the adapter may store it
        however the engine supports; MUST NOT raise when the engine ignores it.

        MUST raise EngineError on transport / HTTP / parsing failures.
        MUST raise EngineError if the engine rejects the upload (non-2xx).
        The returned `status` will typically be PROCESSING — the caller polls
        `document_status` for the lifecycle.
        """
        ...

    async def document_status(self, document_id: str) -> EngineDocumentStatus:
        """Poll the indexing status of a document previously uploaded.

        MUST raise EngineError if the engine is unreachable.
        MUST raise EngineError if `document_id` is not known to the engine
        (adapters that get `[]` back from the engine's batch status endpoint
        translate this into EngineError so the consulting layer can render
        a clear "not found / expired" state).
        """
        ...
