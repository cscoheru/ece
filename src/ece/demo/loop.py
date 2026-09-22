"""cut-042 — Pack-driven six-step loop (generic, scenario-spec driven).

`run_demo_loop` is the cut-042-056 public entry point: same six-step shape as
the V0 spike but driven entirely by a ScenarioSpec + the rule registry. Packs
self-register their rules; the engine reads them via `get_rule(rule_id)`.

This module is the generic counterpart of `ece.v0.loop.run_v0_loop`. Both
share the same §9 contract — assemble / extract / rule / decision / evidence
/ update / re-read — but `run_demo_loop` is pack-agnostic and reads intent /
subject / rule / decision_key from the ScenarioSpec.

Per cut-042 PRD §5: subject_entity_type from spec, not hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.engine import Engine

from ece.v0.loop import (
    _run_demo_loop_impl,  # reuse the proven body
)

__all__ = ["run_demo_loop"]


@dataclass
class DemoLoopResult:
    """Pack-driven six-step result. Mirrors V0LoopResult field set.

    Kept as a distinct type from V0LoopResult so future callers can
    distinguish "spike-procurement result" vs "generic pack result" without
    inspecting scenario_spec. Field semantics are identical.
    """

    package_id: str
    reason: str
    counts: dict[str, int] = field(default_factory=dict)
    denied: list[dict[str, Any]] = field(default_factory=list)
    pr_ref: str | None = None
    pr_attrs_before: dict[str, Any] = field(default_factory=dict)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    quote_refs: list[dict[str, str]] = field(default_factory=list)
    rule_id: str = ""
    conditions: list[dict[str, Any]] = field(default_factory=list)
    decision: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    re_read_attrs: dict[str, Any] = field(default_factory=dict)


def run_demo_loop(
    engine: Engine,
    user_ref: str,
    root_source_id: str,
    scenario_spec: Any,  # ScenarioSpec — imported lazily by caller
    *,
    params: dict[str, Any] | None = None,
) -> DemoLoopResult:
    """Public entry — generic pack-driven loop.

    Delegates to the shared `_run_demo_loop_impl` (defined in `ece.v0.loop` so
    the V0 spike and the generic loop share one proven code path). Result
    dataclass is `DemoLoopResult`; V0 spike continues to return V0LoopResult
    via its own thin wrapper.
    """
    raw = _run_demo_loop_impl(
        engine, user_ref, root_source_id, scenario_spec,
        _result_factory=DemoLoopResult,
        params=params,
    )
    # V0LoopResult is a strict superset of DemoLoopResult fields; we trust the
    # shared impl to populate the same set. The dataclass type is purely a
    # return-type label.
    return raw  # type: ignore[return-value]
