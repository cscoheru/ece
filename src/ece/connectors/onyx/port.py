"""ContentEnginePort — Protocol + Pydantic models (OEI-003 §4 + OEI-007 + OEI-008).

Five methods:
- search(query, *, top_k=None, caller=None)             — read (OEI-003)
- engine_status(*, caller=None)                         — read (OEI-003)
- list_projects(*, caller=None)                        — read (OEI-003)
- upload_document(filename, content, *, project_id,
                 title=None, metadata=None, caller=None)  — write (OEI-007)
- document_status(document_id, *, caller=None)          — write (OEI-007)

OEI-008 — Identity threading:
  Every method now takes an optional `caller: EngineCallerContext | None = None`
  so the caller's identity reaches the adapter for audit + recall labels. The
  Port also exposes `engine_name` so the consulting layer's `engine_merge` no
  longer has to mirror the selector switch (the previous "unable to describe"
  comment is now obsolete — see `04-port-engine-descriptor.txt`).

分层纪律:Onyx 专有字段(citation_id / source_type:user_file / 等)只能活在 adapter
内部,Port 与统一返回模型(Pydantic)零依赖 Onyx。`EngineCallerContext` likewise
imports nothing from Onyx.

Permission discipline (CE limitation, see `07-ce-permission-limitation.md`):
  The Port **cannot** push per-user permissions into the engine (CE has no
  external-source permission sync — that capability is on the EE side). The
  Port therefore passes `caller` for *audit*, not for *enforcement*: per-result
  filtering happens on the ECE side. This is the design contract; every
  adapter emission must surface it in its audit log.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ece.identity.parser import Identity


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


# ---------------------------------------------------------------------------
# OEI-008 — EngineCallerContext (the "who" payload threaded through Port)
# ---------------------------------------------------------------------------


EngineCallerSourceT = Literal["jwt", "header", "anonymous", "test"]


@dataclass(frozen=True)
class EngineCallerContext:
    """Identity payload carried through every ContentEnginePort call.

    Three sources:
      - "jwt"        — caller resolved from `Authorization: Bearer …` (cut-027/032)
      - "header"     — caller resolved from legacy `X-User-Id` header
                       (cut-036 R36.2: only when `ECE_ALLOW_HEADER_AUTH=1`)
      - "anonymous"  — no caller (allowed on read-only surfaces; explicitly
                       forbidden on upload — see OEI-008 §A5)
      - "test"       — internal marker for unit tests; never produced by
                       the API layer

    `roles` is a frozen tuple (not a list) so the context is hashable and
    cheap to put in audit records.

    Construct via `EngineCallerContext.from_headers(...)` (helpers in
    `src/ece/connectors/onyx/caller.py`) or `EngineCallerContext.anonymous()`.
    Direct construction is allowed (it's a dataclass) but `source` must be
    one of the literal values above.
    """

    user_ref: str | None
    roles: tuple[str, ...] = ()
    department: str = ""
    is_management: bool = False
    org_id: str | None = None
    source: EngineCallerSourceT = "anonymous"

    @classmethod
    def anonymous(cls) -> EngineCallerContext:
        """The "no caller" context. Used for read-only anonymous endpoints."""
        return cls(user_ref=None, roles=(), department="", is_management=False,
                   org_id=None, source="anonymous")

    @classmethod
    def from_identity(
        cls,
        identity: Identity | None,
        *,
        source: EngineCallerSourceT = "header",
    ) -> EngineCallerContext:
        """Build from a resolved `Identity` (or `None` for anonymous).

        Lazy TYPE_CHECKING import keeps port.py independent of the
        identity module at module load time.
        """
        if identity is None:
            return cls.anonymous()
        return cls(
            user_ref=identity.user_ref,
            roles=tuple(identity.roles),
            department=identity.department or "",
            is_management=identity.is_management,
            org_id=None,
            source=source,
        )

    def display(self) -> str:
        """Stable string for audit logs (no secrets, no PII beyond user_ref)."""
        ref = self.user_ref or "<anonymous>"
        return f"{ref}[{self.source},dept={self.department or '-'},mgmt={self.is_management}]"


@runtime_checkable
class ContentEnginePort(Protocol):
    """Abstract port to a content + search engine.

    Implementations: OnyxContentEngineAdapter (real), MockContentEngineAdapter (offline).
    Every method now takes an optional `caller: EngineCallerContext | None = None`
    (OEI-008). Adapters MUST record the caller's identity for audit; callers
    MAY pass `None` for read-only anonymous access (see OEI-008 §A5).
    """

    @property
    def engine_name(self) -> str:
        """A stable string identifying the engine kind.

        Lets the consulting layer describe the live engine without
        re-implementing the selector switch (eliminates the debt
        documented in OEI-007 §R1). MUST be lowercase, no spaces.
        """
        ...

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        caller: EngineCallerContext | None = None,
    ) -> list[EngineDocument]:
        """Run a search query and return up to top_k documents (engine's default if None).

        MUST NOT raise on empty results — return [] instead.
        MUST raise EngineError on transport / HTTP / parsing failures.
        `caller` is for audit only (does not affect results — see CE
        permission-limitation note in module docstring).
        """
        ...

    async def engine_status(self, *, caller: EngineCallerContext | None = None) -> EngineStatus:
        """Return current engine state snapshot.

        MUST raise EngineError if engine is unreachable.
        """
        ...

    async def list_projects(self, *, caller: EngineCallerContext | None = None) -> list[EngineProject]:
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
        caller: EngineCallerContext | None = None,
    ) -> EngineDocumentStatus:
        """Upload a document to the engine and return its initial status.

        `content` is the raw file bytes (the engine does the text extraction).
        `metadata` is engine-shaped advisory data — the adapter may store it
        however the engine supports; MUST NOT raise when the engine ignores it.

        `caller` MUST be non-None on this write path (OEI-008 §A5):
        anonymous uploads are forbidden. Adapters MUST raise `EngineError`
        if `caller` is None — the consulting layer's upload route guards
        this with a 401/403 before reaching the Port.

        MUST raise EngineError on transport / HTTP / parsing failures.
        MUST raise EngineError if the engine rejects the upload (non-2xx).
        The returned `status` will typically be PROCESSING — the caller polls
        `document_status` for the lifecycle.
        """
        ...

    async def document_status(
        self,
        document_id: str,
        *,
        caller: EngineCallerContext | None = None,
    ) -> EngineDocumentStatus:
        """Poll the indexing status of a document previously uploaded.

        MUST raise EngineError if the engine is unreachable.
        MUST raise EngineError if `document_id` is not known to the engine
        (adapters that get `[]` back from the engine's batch status endpoint
        translate this into EngineError so the consulting layer can render
        a clear "not found / expired" state).
        """
        ...
