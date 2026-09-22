"""cut-042 — Rule registry.

Domain packs self-register their rules at module import time via
`register_rule(...)`. The engine (`ece.v0.loop` / `ece.demo.loop`) reads
rules through `get_rule(rule_id)` and never imports pack modules directly.

The registry is a module-level dict (`_REGISTRY`) — module load order is
deterministic in CPython (PEP 328 + import system), so the first
registration wins for a given rule_id. Subsequent registrations of an existing
id raise `ValueError` to surface packaging bugs immediately, not at first
call.

cut-042R2 R2-F2 — added optional `materialize_fn` to RuleDescriptor so packs can
declare pack-owned deterministic relations materializers (e.g. quote_count →
SELECTS relations). The engine calls `materialize_fn(engine, root_source_id,
params)` AFTER permission check, BEFORE rule evaluation, on the allowed path.

Why `importlib.import_module(...)` (runtime, not static `from ... import`):
keeps the `ece → ece.domain_packs` import contract (lint-imports 2 kept)
intact. grimp AST analysis does not see runtime imports.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import Engine  # cut-042R2 R2-F2

from ece.context.assembly import ContextPackage

__all__ = ["RuleDescriptor", "get_rule", "list_rule_ids", "register_rule"]


@dataclass(frozen=True)
class RuleDescriptor:
    """The wiring of one deterministic rule + decision builder.

    evaluate_fn signature: ``(ctx: ContextPackage, params: dict) -> list[dict]``
        Returns the rule's evaluated conditions. Packs adapt their existing
        S3 functions (which take scalar args like ``amount``, ``quote_count``)
        by wrapping them — see ``src/ece/domain_packs/procurement/agent/v0_rules.py``.

    build_decision_fn signature: ``(conditions: list[dict], ctx: ContextPackage) -> dict``
        Returns the 8-key Decision dict per V0 spike §7.

    materialize_fn signature: ``(engine: Engine, root_source_id: str, params: dict) -> None``
        cut-042R2 R2-F2 — pack-owned deterministic relations materializer.
        Called by the engine AFTER permission check, BEFORE rule evaluation,
        on the allowed path only. Used to rebuild relational state
        (e.g. SELECTS relations count == params["quote_count"]).
        Optional: None means no materialization for this rule.
    """

    rule_id: str
    decision_key: str
    evaluate_fn: Callable[[ContextPackage, dict[str, Any]], list[dict[str, Any]]]
    build_decision_fn: Callable[[list[dict[str, Any]], ContextPackage], dict[str, Any]]
    materialize_fn: Callable[[Engine, str, dict[str, Any]], None] | None = None


_REGISTRY: dict[str, RuleDescriptor] = {}


def register_rule(
    rule_id: str,
    *,
    decision_key: str,
    evaluate_fn: Callable[[ContextPackage, dict[str, Any]], list[dict[str, Any]]],
    build_decision_fn: Callable[[list[dict[str, Any]], ContextPackage], dict[str, Any]],
    materialize_fn: Callable[[Engine, str, dict[str, Any]], None] | None = None,
) -> None:
    """Register a rule under `rule_id`. Raises ValueError on duplicate."""
    if rule_id in _REGISTRY:
        raise ValueError(
            f"duplicate rule_id={rule_id!r} in registry; second registration refused "
            f"(existing descriptor: {_REGISTRY[rule_id]!r})"
        )
    _REGISTRY[rule_id] = RuleDescriptor(
        rule_id=rule_id,
        decision_key=decision_key,
        evaluate_fn=evaluate_fn,
        build_decision_fn=build_decision_fn,
        materialize_fn=materialize_fn,
    )


def get_rule(rule_id: str) -> RuleDescriptor:
    """Look up a registered rule. Raises KeyError if not registered."""
    try:
        return _REGISTRY[rule_id]
    except KeyError as exc:
        raise KeyError(
            f"rule_id={rule_id!r} not registered; "
            f"available={list_rule_ids()}"
        ) from exc


def list_rule_ids() -> list[str]:
    """Return all currently registered rule ids (unsorted, Python dict order)."""
    return list(_REGISTRY.keys())
