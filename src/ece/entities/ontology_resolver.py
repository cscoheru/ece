"""Per-source-system ontology resolver.

Before cut-043, `ece.entities.pipeline.is_allowed` was hard-coded to the
procurement ontology (`from ece.domain_packs.procurement import is_allowed`).
This violated ECE 铁律 4 ("domain pack isolation") — the engine imported a
specific pack, so the second pack could not ship its own ontology.

cut-043R R5-B3 — INVERTED registration direction.

  - The resolver lives at `ece.entities.ontology_resolver` (engine side).
  - It exposes a pure `register_ontology_for_system(prefix, fn_pair)` API.
  - It does NOT import any `ece.domain_packs.*` module — ever.
  - Each pack's `__init__.py` imports this resolver and calls `register_*`.

Why this matters: `ece.entities` is engine. The engine must NOT know which
packs exist. The previous design had `_ensure_default()` and
`_register_knowledge_default()` reach across the boundary at module-load
time — Codex R5-B3 caught that as a 铁律 4 violation. The corrected design
treats registration as a pure, opt-in side effect that flows IN to the
resolver from outside.

Failure mode (R5-B3 followup): unknown source_system is FAIL-CLOSED —
`is_allowed_for_system` returns False (refuses the relation), and a
warning is logged once per unknown prefix. The legacy "fall back to
procurement" behaviour is gone; if a new pack is added it must register
its own ontology or relations from it will be rejected. This is the only
safe default for an isolation-critical boundary.
"""
from __future__ import annotations

from collections.abc import Callable

__all__ = [
    "register_ontology_for_system",
    "is_allowed_for_system",
    "allowed_targets_for_system",
    "registered_prefixes",
]


# system-prefix → (is_allowed, allowed_targets) callable pair.
# Keyed by the `source_system` prefix (the part before the first ':').
_REGISTRY: dict[str, tuple[Callable[[str, str, str], bool], Callable[[str, str], list[str]]]] = {}

# cut-043R R5-B3 — warn-once for unknown source_system prefixes. Helps the
# next pack author discover they forgot to register.
_WARNED_PREFIXES: set[str] = set()


def register_ontology_for_system(
    system_prefix: str,
    is_allowed_fn: Callable[[str, str, str], bool],
    allowed_targets_fn: Callable[[str, str], list[str]],
) -> None:
    """Register an ontology pair for a `source_system` prefix.

    Idempotent: re-registering the same prefix overwrites (useful for tests).
    The resolver stores `(is_allowed_fn, allowed_targets_fn)` as a tuple —
    callers should not mutate the pair. The pair is typed `Callable` so the
    resolver has zero knowledge of pack internals.
    """
    if not isinstance(system_prefix, str) or not system_prefix:
        raise ValueError(
            f"system_prefix must be a non-empty string; got {system_prefix!r}"
        )
    _REGISTRY[system_prefix] = (is_allowed_fn, allowed_targets_fn)


def registered_prefixes() -> tuple[str, ...]:
    """Return the tuple of registered source-system prefixes.

    Used by tests to assert registration state without exposing the dict.
    """
    return tuple(sorted(_REGISTRY.keys()))


def _lookup(prefix: str) -> tuple[Callable[[str, str, str], bool], Callable[[str, str], list[str]]] | None:
    pair: tuple[Callable[[str, str, str], bool], Callable[[str, str], list[str]]] | None = _REGISTRY.get(prefix)
    if pair is None and prefix not in _WARNED_PREFIXES:
        _WARNED_PREFIXES.add(prefix)
        import warnings
        warnings.warn(
            f"ontology_resolver: unknown source_system prefix={prefix!r}; "
            f"known prefixes={registered_prefixes()}. Relations from this "
            f"source_system will be REJECTED (fail-closed). If this is a new "
            f"pack, call register_ontology_for_system(...) in its __init__.py.",
            stacklevel=2,
        )
    return pair


def is_allowed_for_system(
    src_type: str,
    relation: str,
    dst_type: str,
    source_system: str,
) -> bool:
    """Route ontology check to the pack owning this source_system.

    cut-043R R5-B3 — fail-closed. Unknown prefix returns False (reject
    the relation). The previous "fall back to procurement" behaviour was
    removed because it re-introduced the very isolation violation the
    resolver exists to prevent.
    """
    prefix = source_system.split(":", 1)[0] if source_system else ""
    pair = _lookup(prefix)
    if pair is None:
        return False
    is_allowed_fn = pair[0]
    return is_allowed_fn(src_type, relation, dst_type)


def allowed_targets_for_system(src_type: str, relation: str, source_system: str) -> list[str]:
    """Route allowed_targets lookup to the pack owning this source_system.

    Unknown prefix returns an empty list (fail-closed) — the calling code
    should treat this as "no valid targets", which the integration tests
    verify.
    """
    prefix = source_system.split(":", 1)[0] if source_system else ""
    pair = _lookup(prefix)
    if pair is None:
        return []
    allowed_targets_fn = pair[1]
    return allowed_targets_fn(src_type, relation)
