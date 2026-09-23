"""KC-001 — Consulting Knowledge Copilot module.

A file-backed, in-memory catalog of consulting knowledge objects (cases,
methodologies, proposal plays, deliverable templates, risk checks,
industry notes) exposed as read-only FastAPI endpoints under
``/api/v1/consulting/*``.

Scope is intentionally narrow — see
``docs/demo-platform/CONSULTING_CONTEXT_KERNEL_KC001_TASK.md`` for the
explicit in-scope / out-of-scope contract.
"""
from __future__ import annotations

from ece.consulting.models import (
    FacetsResponse,
    KnowledgeObject,
    LibraryResponse,
)
from ece.consulting.router import router
from ece.consulting.service import ConsultingCatalog, default_catalog

__all__ = [
    "ConsultingCatalog",
    "default_catalog",
    "FacetsResponse",
    "KnowledgeObject",
    "LibraryResponse",
    "router",
]
