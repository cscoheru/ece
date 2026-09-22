"""cut-043 — Per-source-system ontology resolver.

Before cut-043, `ece.entities.pipeline.is_allowed` was hard-coded to the
procurement ontology (`from ece.domain_packs.procurement import is_allowed`).
This violated ECE 铁律 4 ("domain pack isolation") — the engine imported a
specific pack, so the second pack could not ship its own ontology.

This resolver routes ontology validation by `source_system` prefix:

    `spike:`  →  procurement ontology (the spike fixture)
    `km:`     →  knowledge ontology (cut-043)
    `compliance:` → compliance ontology (cut-044, future)

Anything else falls back to procurement (preserves the cut-042 baseline).
This keeps each pack owning its own triple whitelist, satisfies 铁律 4, and
makes "换域不换底座" a real property — not a doc claim.

Why a runtime registry rather than a hard-coded dict:
  Each pack's ontology module is opt-in — importing `knowledge` registers
  itself. Compliance (cut-044) just adds another register call. No engine
  code changes when a new pack ships.
"""
from __future__ import annotations

from collections.abc import Callable

__all__ = [
    "register_ontology_for_system",
    "is_allowed_for_system",
    "allowed_targets_for_system",
]


# system-prefix → (is_allowed, allowed_targets) callable pair.
# Keyed by the `source_system` prefix (the part before the first ':').
_REGISTRY: dict[str, tuple[Callable[[str, str, str], bool], Callable[[str, str], list[str]]]] = {}

# Default fallback: procurement ontology (preserves cut-042 baseline behavior
# so the spike fixture and demo:demo fixture keep working unchanged).
_DEFAULT = None


def _ensure_default() -> None:
    global _DEFAULT
    if _DEFAULT is not None:
        return
    from ece.domain_packs.procurement import allowed_targets, is_allowed
    _DEFAULT = (is_allowed, allowed_targets)


def register_ontology_for_system(
    system_prefix: str,
    is_allowed_fn: Callable[[str, str, str], bool],
    allowed_targets_fn: Callable[[str, str], list[str]],
) -> None:
    """Register an ontology pair for a `source_system` prefix.

    Idempotent: re-registering the same prefix overwrites (useful for tests).
    """
    _REGISTRY[system_prefix] = (is_allowed_fn, allowed_targets_fn)


def is_allowed_for_system(
    src_type: str,
    relation: str,
    dst_type: str,
    source_system: str,
) -> bool:
    """Route ontology check to the pack owning this source_system."""
    prefix = source_system.split(":", 1)[0] if source_system else ""
    pair = _REGISTRY.get(prefix)
    if pair is None:
        _ensure_default()
        pair = _DEFAULT
    return pair[0](src_type, relation, dst_type)


def allowed_targets_for_system(src_type: str, relation: str, source_system: str) -> list[str]:
    """Route allowed_targets lookup to the pack owning this source_system."""
    prefix = source_system.split(":", 1)[0] if source_system else ""
    pair = _REGISTRY.get(prefix)
    if pair is None:
        _ensure_default()
        pair = _DEFAULT
    return pair[1](src_type, relation)


# cut-043 — knowledge pack self-registration at module import time.
# The `knowledge/__init__.py` imports this module via its side-effect import,
# which causes the resolver to route `km:*` source_systems to the KM ontology.
def _register_knowledge_default() -> None:
    from ece.domain_packs.knowledge import allowed_targets as km_allowed_targets
    from ece.domain_packs.knowledge import is_allowed as km_is_allowed

    register_ontology_for_system("km", km_is_allowed, km_allowed_targets)


_register_knowledge_default()
