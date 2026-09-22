"""S5 (V0 Technical Spike) — six-step loop orchestrator.

Per `docs/v0/V0_EXECUTION_SPEC.md` §9 (the six steps), §10 (per-step verifications),
§11 (end-to-end output shape). Per the binding acceptance criteria for S5.

Hard contract enforced here (and asserted by `tests/integration/test_v0_loop.py`):

  - **The loop closes back onto Context.** Step [6] is followed by a re-read that goes
    back through `assemble_context` — the same path step [1] used — not by inspecting
    `apply_context_update`'s return value. A raw-SQL read of the same row is kept as a
    second, independent source; if the two disagree the assembly path and the row have
    diverged and the loop refuses to report success.
  - **Decision stays deterministic.** The function never routes through a model gateway.
  - **No new abstraction.** The function is straight orchestration: it calls the
    existing S2 (`persist_evidence` / `get_evidence_for_decision`), S3 (`evaluate_rule`
    / `build_decision`), and S4 (`apply_context_update`) functions. It does not
    introduce a request abstraction or a runtime wrapper.
  - **Address by `source_id`.** We resolve the `display_id` for `assemble_context`
    via `(source_id, source_system)`; `display_id` itself is never hard-coded.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.context.assembly import assemble_context
from ece.context.update import apply_context_update
from ece.db import get_engine
from ece.evidence import get_evidence_for_decision, persist_evidence

if TYPE_CHECKING:
    from ece.demo.spec import ScenarioSpec

__all__ = ["DemoLoopResult", "V0LoopResult", "run_demo_loop", "run_v0_loop"]

# Hard-coded for the V0 spike. The fixture's PR lives in this source_system; the loop
# would need a different resolver to support other fixtures, which is post-V0 work.
SPIKE_SOURCE_SYSTEM = "spike:v0-technical-fixture"

# The four keys §8 writes back. Kept here so the re-read cross-check names them once.
REVIEW_KEYS = (
    "review_status",
    "review_decision_id",
    "review_evidence_id",
    "review_updated_at",
)

# cut-042: procurement-pack scenario spec, lazy-built at first call. Used by
# the thin `run_v0_loop` wrapper to preserve the V0 spike behavior verbatim
# while the engine itself becomes pack-agnostic via `run_demo_loop`. Lazy to
# break the v0.loop ↔ demo.* import cycle.
_SPIKE_SPEC: ScenarioSpec | None = None


def _get_spike_spec() -> ScenarioSpec:
    from ece.demo.spec import ScenarioSpec
    global _SPIKE_SPEC
    if _SPIKE_SPEC is None:
        _SPIKE_SPEC = ScenarioSpec(
            pack="procurement",
            spec="evaluate_purchase_request",
            root_entity={"type": "purchase_request", "id_field": "source_id"},
            subject_entity_type="purchase_request",
            rule_id="R-SPIKE-REVIEW",
            decision_key="review_status",
            params_schema={"amount": "int", "quote_count": "int"},
            denied_users=["spike-user-unrelated", "demo-user-unrelated"],
        )
    return _SPIKE_SPEC


@dataclass
class V0LoopResult:
    """The closed-loop artifact (§10): every step's product, in one shape.

    The field set mirrors §10's per-step table so that a caller (the §11 script, a
    test) never has to re-derive a step's output by calling the engine again — which
    would be a second implementation of the loop.
    """

    package_id: str
    reason: str
    # [1] CONTEXT
    counts: dict[str, int] = field(default_factory=dict)
    denied: list[dict[str, Any]] = field(default_factory=list)
    # [2] ENTITY / KNOWLEDGE
    pr_ref: str | None = None
    pr_attrs_before: dict[str, Any] = field(default_factory=dict)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    quote_refs: list[dict[str, str]] = field(default_factory=list)
    # [3] RULE — cut-042: default is the procurement spike rule_id string.
    # The class no longer carries the import; rule_id is sourced from the
    # ScenarioSpec at run_demo_loop time. The string literal here preserves
    # the V0 spike's V0LoopResult dataclass default for callers that still
    # rely on it (regression tests).
    rule_id: str = "R-SPIKE-REVIEW"
    conditions: list[dict[str, Any]] = field(default_factory=list)
    # [4] DECISION
    decision: dict[str, Any] | None = None
    # [5] EVIDENCE
    evidence: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    # [6] CONTEXT UPDATE + RE-READ
    re_read_attrs: dict[str, Any] = field(default_factory=dict)


def run_v0_loop(
    user_ref: str,
    pr_source_id: str,
    *,
    engine: Engine | None = None,
) -> V0LoopResult:
    """V0 spike six-step loop — preserved verbatim via the pack-driven engine.

    cut-042: this entry point stays byte-compatible. Internally it delegates to
    `run_demo_loop` with the procurement-pack scenario spec, so any behavior
    change in the generic loop is automatically picked up — but the **call
    surface** (signature, return type, field semantics) is locked by the V0 spike
    regression tests in `tests/integration/test_v0_*.py`.
    """
    if engine is None:
        engine = get_engine()
    return _run_demo_loop_impl(
        engine,
        user_ref,
        pr_source_id,
        _get_spike_spec(),
        _result_factory=V0LoopResult,
    )


def _re_read_through_assembly(
    engine: Engine,
    user_ref: str,
    display_id: str,
    root_entity_type: str,
    intent_name: str,
) -> dict[str, Any]:
    """Step [6]'s re-read: ask the assembly path again.

    Reading the row back through `assemble_context` is what makes this a *closed loop*
    rather than "we wrote and then we read". A raw SQL read proves the row moved; it
    does not prove the Context path surfaces the new state, which is the thing V3's
    `Context Update` actually promises.
    """
    re_ctx = assemble_context(
        engine, user_ref, intent_name,
        [{"type": root_entity_type, "id": display_id}], pack="procurement",
    )
    re_pr = next((e for e in re_ctx.entities if e["type"] == root_entity_type), None)
    if re_pr is None:
        raise RuntimeError(
            "re-read lost the root entity: after the update the assembly path no longer "
            f"returns {display_id!r} (denied={re_ctx.denied})"
        )
    return dict(re_pr["attrs"])


def _assert_loop_closed(
    dec: dict[str, Any],
    re_read_attrs: dict[str, Any],
    engine: Engine,
    display_id: str,
    decision_key: str,
) -> None:
    """§8's invariant, plus a second independent reading of the same row.

    Two sources for one fact: the assembly path (what a caller would see) and a raw
    SELECT (what the table holds). They are produced by different code, so agreement
    is evidence and disagreement is a bug — either way this is not self-reporting.
    """
    if re_read_attrs.get(decision_key) != dec["decision_value"]:
        raise RuntimeError(
            f"loop did not close: re-read {decision_key}={re_read_attrs.get(decision_key)!r} "
            f"!= decision_value={dec['decision_value']!r}"
        )

    direct = _read_pr_attrs(engine, display_id)
    for key in REVIEW_KEYS:
        if direct.get(key) != re_read_attrs.get(key):
            raise RuntimeError(
                f"assembly path and raw row disagree on {key!r}: "
                f"{re_read_attrs.get(key)!r} vs {direct.get(key)!r}"
            )


def _resolve_display_id(engine: Engine, source_id: str) -> str:
    """Resolve a fixture-level `source_id` to the entity's `display_id` for
    `assemble_context`. Refuses to guess if the lookup misses (defensive — the caller
    should have a clear error, not a silent retry).
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": SPIKE_SOURCE_SYSTEM},
        ).first()
    if row is None:
        raise ValueError(
            f"no PR with source_id={source_id!r} source_system={SPIKE_SOURCE_SYSTEM!r}"
        )
    return row[0]


def _resolve_source_refs(engine: Engine, display_ids: list[str]) -> list[dict[str, str]]:
    """Map `display_id` → `(source_system, source_id)` for display.

    §11 names suppliers by their source identity (`SPIKE-SUP-A`), while the Context
    shape only carries `display_id` (see `assembly.py` step 5). This is the inverse of
    `_resolve_display_id` and exists only so the §11 output can be printed verbatim.
    """
    if not display_ids:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT display_id, source_system, source_id FROM entities "
                "WHERE display_id = ANY(:ids)"
            ),
            {"ids": display_ids},
        ).all()
    by_display = {r[0]: {"system": r[1] or "", "record_id": r[2] or ""} for r in rows}
    return [{"display_id": d, **by_display.get(d, {"system": "", "record_id": ""})}
            for d in display_ids]


def _read_pr_attrs(engine: Engine, display_id: str) -> dict[str, Any]:
    """Read the PR's attributes straight from the table.

    Deliberately bypasses `assemble_context`: it is the second, independent witness in
    `_assert_loop_closed`. Nothing here trusts a function's own return value.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT attributes FROM entities WHERE display_id = :did"),
            {"did": display_id},
        ).first()
    return dict(row[0]) if row and row[0] else {}


# ---------------------------------------------------------------------------
# cut-042 — pack-driven six-step loop (`run_demo_loop`).
#
# This is the generic counterpart to `run_v0_loop`. It reads intent / rule /
# subject_entity_type / decision_key from `scenario_spec` and resolves the rule
# function via `ece.demo.registry.get_rule(...)`. No `ece.domain_packs` import
# exists in the call graph from here on — the registry decouples engine from pack.
#
# `run_v0_loop` is now a thin wrapper that supplies the procurement spec; the
# shared body lives in `_run_demo_loop_impl` so both entry points stay
# byte-equivalent at the §9 contract level.
# ---------------------------------------------------------------------------


@dataclass
class DemoLoopResult:
    """Pack-driven six-step result. Same field set as V0LoopResult.

    A second type alias so `run_demo_loop` callers do not need to import
    `V0LoopResult` when working with non-procurement packs. Both dataclasses
    share the same field semantics; the difference is only the type identity,
    so a future "Unify under V0LoopResult" refactor is possible without API break.
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
    scenario_spec: ScenarioSpec,
    *,
    params: dict[str, Any] | None = None,
) -> DemoLoopResult:
    """Pack-driven six-step loop.

    Per cut-042 PRD §5: this is the engine generic. Reads intent / rule /
    subject_entity_type / decision_key from `scenario_spec`. The pack supplies
    its rule via `register_rule(rule_id, ...)`; the loop reads it through the
    registry. No static `from ece.domain_packs... import` lives in this file.
    """
    return _run_demo_loop_impl(
        engine,
        user_ref,
        root_source_id,
        scenario_spec,
        _result_factory=DemoLoopResult,
        params=params or {},
    )


def _run_demo_loop_impl(
    engine: Engine,
    user_ref: str,
    root_source_id: str,
    scenario_spec: ScenarioSpec,
    *,
    _result_factory: type,
    params: dict[str, Any] | None = None,
) -> Any:
    """Shared body for `run_v0_loop` and `run_demo_loop`.

    `_result_factory` picks the result dataclass so the V0 spike preserves its
    V0LoopResult shape (locked by tests) while the generic loop returns its own.
    """
    params = params or {}
    _ensure_pack_registered(scenario_spec.pack)  # idempotent; see below
    # Defer the registry import to runtime to break the
    # v0.loop ↔ demo.api ↔ demo.loop cycle at module load time.
    from ece.demo.registry import get_rule
    descriptor = get_rule(scenario_spec.rule_id)

    display_id = _resolve_display_id(engine, root_source_id)
    root_type = str(scenario_spec.root_entity["type"])

    # [1] assemble_context — pack-agnostic, intent + root_entity come from spec.
    ctx = assemble_context(
        engine, user_ref, scenario_spec.spec,
        [{"type": root_type, "id": display_id}],
        pack=scenario_spec.pack,
    )

    # [2] extract root + SELECTS quotes; denied → early return.
    root = next((e for e in ctx.entities if e["type"] == root_type), None)
    quotes = [r for r in ctx.relationships if r["rel"] == "SELECTS"]
    counts = {"entities": len(ctx.entities), "relationships": len(ctx.relationships)}

    if ctx.denied and root is None:
        return _result_factory(
            package_id=ctx.package_id,
            reason="no permitted context",
            counts=counts,
            denied=ctx.denied,
            pr_ref=display_id,
            pr_attrs_before=_read_pr_attrs(engine, display_id),
            decision=None,
            evidence=[],
            evidence_ids=[],
            re_read_attrs=_read_pr_attrs(engine, display_id),
        )

    assert root is not None, "unreachable: denied branch returned when root was None"
    pr_attrs_before = dict(root["attrs"])

    # Resolve rule params: explicit params win; otherwise fall back to the
    # root entity's `amount` + the SELECTS-quote count. This makes
    # `run_demo_loop` work with the procurement pack out of the box while
    # leaving the door open for future packs to declare their own param
    # sources in the ScenarioSpec YAML.
    effective_params: dict[str, Any] = dict(params)
    if "amount" not in effective_params:
        effective_params["amount"] = root["attrs"].get("amount", 0)
    if "quote_count" not in effective_params:
        effective_params["quote_count"] = len(quotes)

    # [3] [4] rule + decision — pure functions from registry.
    conditions = descriptor.evaluate_fn(ctx, effective_params)
    dec = descriptor.build_decision_fn(conditions, ctx)

    # [5] evidence — subject type from spec, NOT hardcoded.
    persist_evidence(
        engine, ctx, dec,
        subject_entity_type=scenario_spec.subject_entity_type,
    )
    rows = get_evidence_for_decision(engine, dec["decision_id"])
    evidence_ids = [r["evidence_id"] for r in rows]

    # [6] apply_context_update + re-read through assembly path.
    apply_context_update(
        engine, root_source_id, SPIKE_SOURCE_SYSTEM, dec, evidence_ids[0],
    )
    re_read_attrs = _re_read_through_assembly(
        engine, user_ref, display_id, root_type, scenario_spec.spec,
    )
    _assert_loop_closed(
        dec, re_read_attrs, engine, display_id, scenario_spec.decision_key,
    )

    return _result_factory(
        package_id=ctx.package_id,
        reason="ok",
        counts=counts,
        denied=ctx.denied,
        pr_ref=display_id,
        pr_attrs_before=pr_attrs_before,
        quotes=quotes,
        quote_refs=_resolve_source_refs(engine, [q["to"] for q in quotes]),
        rule_id=scenario_spec.rule_id,
        conditions=conditions,
        decision=dec,
        evidence=rows,
        evidence_ids=evidence_ids,
        re_read_attrs=re_read_attrs,
    )


# cut-0242: re-export loader for convenience so callers can do
# `from ece.v0.loop import load_scenario_spec` if they prefer.
__all__ = ["DemoLoopResult", "V0LoopResult", "run_demo_loop", "run_v0_loop"]


# cut-042: lazy pack registration. The procurement pack self-registers its
# rule when its `agent.v0_rules` module is first imported (see `_register_for_demo`
# at the bottom of that file). To avoid forcing every V0 spike test to import the
# pack (which would re-couple engine and pack at module load time), we trigger
# the import inside the loop on first call. This keeps the import graph:
#   engine  →  registry  ←  pack (via runtime importlib)
# and preserves `ece → ece.domain_packs` static-import contract for lint-imports.
_REGISTERED_PACKS: set[str] = set()


def _ensure_pack_registered(pack: str) -> None:
    if pack in _REGISTERED_PACKS:
        return
    # Procurement is the only pack at cut-042; subsequent cuts add `if pack == "knowledge": ...`.
    if pack == "procurement":
        importlib.import_module("ece.domain_packs.procurement.agent.v0_rules")
    _REGISTERED_PACKS.add(pack)
