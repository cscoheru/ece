"""Sprint 3 — Context Engine (Spec loader + Assembly Pipeline + Provenance).

Per ece/TASKS.md S3:
- S3.1 Context Spec loader (YAML → typed Pydantic model)
- S3.2 Assembly Pipeline 12 steps (ARCHITECTURE §3 / PRD §29)
- S3.3 Provenance + context_requests/context_items (DATA_MODEL §5)

Engine Core — zero domain knowledge (CLAUDE.md iron rule 4).
Domain packs provide YAML specs under `domain_packs/<pack>/context_specs/`.
"""
from .assembly import ContextPackage, assemble_context
from .provenance import build_sources, record_package
from .relationships import get_relationships
from .spec import ContextSpec, load_spec

__all__ = [
    "ContextSpec",
    "load_spec",
    "get_relationships",
    "build_sources",
    "record_package",
    "ContextPackage",
    "assemble_context",
]
