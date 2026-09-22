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

cut-042R changes (Codex HOLD 2026-09-22, F2/F3/F4):
  - The module-level `SPIKE_SOURCE_SYSTEM` constant and `pack="procurement"`
    hardcode have been removed. The loop now reads source_system / pack from
    `scenario_spec.source_system` / `scenario_spec.pack`, becoming pack-agnostic.
  - Step [0] (cut-042R F3) wrote API params back to the root entity's attributes via
    `_apply_params_to_root_attrs`. This was BEFORE permission check — a violation
    of Permission Before Intelligence when the caller was denied.
  - Step [5]/[6] guard against `evidence_ids[0]` IndexError when 0 rows exist.
    `apply_context_update` accepts None for the auto_approved path (F4 fix
    in `ece.context.update`).

cut-042R2 changes (Codex 第二轮 HOLD 2026-09-22, R2-F1/R2-F2):
  - **R2-F1 (CRITICAL) — Permission Before Materialization.** The loop is
    reordered: step [1] is now the FIRST read-only `assemble_context`, BEFORE
    any write. If `ctx.denied and root is None`, the function returns
    immediately with ZERO writes — `_apply_params_to_root_attrs`, the
    relations materializer, evidence persistence, and `apply_context_update`
    are all skipped. The denied path's DB state is byte-equal to before the
    request.
  - **R2-F2 — Pack-owned deterministic materializer.** New step [3b] calls
    `descriptor.materialize_fn(engine, root_source_id, effective_params)`
    between step [3a] (params → root.attrs) and step [3c] (re-assemble
    context). The procurement pack's materializer rebuilds SELECTS
    relations so their count equals `params["quote_count"]`. The re-read
    in step [3c] sees the materialized state, so the rule and evidence
    computed downstream agree with the DB.
"""
from __future__ import annotations

import contextlib
import importlib
import json
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

# The four keys §8 writes back. Kept here so the re-read cross-check names them once.
REVIEW_KEYS = (
    "review_status",
    "review_decision_id",
    "review_evidence_id",
    "review_updated_at",
)

# cut-042R F2: removed SPIKE_SOURCE_SYSTEM module constant.
# Source system now comes from scenario_spec.source_system (per-pack declaration
# in ece/domain_packs/<pack>/scenarios/<scenario>.yaml).

# cut-042: procurement-pack scenario spec, lazy-built at first call. Used by
# the thin `run_v0_loop` wrapper to preserve the V0 spike behavior verbatim
# while the engine itself becomes pack-agnostic via `run_demo_loop`. Lazy to
# break the v0.loop ↔ demo.* import cycle.
_SPIKE_SPEC: ScenarioSpec | None = None


def _get_spike_spec() -> ScenarioSpec:
    """Load the V0 spike's ScenarioSpec from its YAML declaration.

    cut-042R F2: the V0 spike scenario is a procurement-pack artifact, but its
    CONFIG lives in `ece.domain_packs.procurement.scenarios.default.yaml` —
    NOT inline here. This function is a thin loader that keeps the V0 spike's
    behavioral contract (run with the procurement-pack default scenario) while
    ensuring v0/loop.py itself contains zero procurement business strings.

    For F3 root_params_fields: the YAML's `root_params_fields` field declares
    which request params should be written back to root.attrs. The V0 spike's
    YAML specifies `amount` only (since `quote_count` lives on quote entities,
    not on the PR root).

    Lazy: deferred import to break the v0.loop ↔ demo.* circular dependency.
    """
    from ece.demo.spec import load_scenario_spec

    global _SPIKE_SPEC
    if _SPIKE_SPEC is None:
        # Single source of truth: the procurement pack's default.yaml. Any change
        # to the V0 spike's scenario config happens there, not in this module.
        _SPIKE_SPEC = load_scenario_spec("procurement", "default")
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
    # [3] RULE — cut-042R F2: rule_id is sourced from ScenarioSpec at run time;
    # the dataclass field has no procurement-specific default. The string "" is
    # the safe-by-default value that the impl populates from scenario_spec.rule_id.
    rule_id: str = ""
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
    pack: str,  # cut-042R F2: pack from scenario_spec, not hardcoded
) -> dict[str, Any]:
    """Step [6]'s re-read: ask the assembly path again.

    Reading the row back through `assemble_context` is what makes this a *closed loop*
    rather than "we wrote and then we read". A raw SQL read proves the row moved; it
    does not prove the Context path surfaces the new state, which is the thing V3's
    `Context Update` actually promises.
    """
    re_ctx = assemble_context(
        engine, user_ref, intent_name,
        [{"type": root_entity_type, "id": display_id}], pack=pack,
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


def _resolve_display_id(engine: Engine, source_id: str, source_system: str) -> str:
    """Resolve a fixture-level `source_id` to the entity's `display_id` for
    `assemble_context`. Refuses to guess if the lookup misses (defensive — the caller
    should have a clear error, not a silent retry).

    cut-042R F2: `source_system` is a parameter, NOT a module constant.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": source_system},
        ).first()
    if row is None:
        raise ValueError(
            f"no entity with source_id={source_id!r} source_system={source_system!r}"
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
# cut-042R F3 — Step [0]: apply API params to root entity's attributes.
# ---------------------------------------------------------------------------


_APPLY_PARAMS_SQL = text("""
    UPDATE entities
    SET attributes = COALESCE(attributes, '{}'::jsonb) || CAST(:params AS jsonb)
    WHERE source_id = :sid AND source_system = :sys
""")


def _apply_params_to_root_attrs(
    engine: Engine,
    source_id: str,
    source_system: str,
    params: dict[str, Any],
    root_params_fields: tuple[str, ...],
) -> None:
    """cut-042R F3 — write API params back to the root entity's attributes.

    Codex 实测 amount=1_500_000 后, DB.amount 仍是 1_280_000 (seed fixture 默认),
    因为 effective_params 只进入 rule in-memory, 不写回 DB. 此函数把 params 真实
    合并到 root.attrs (jsonb), 后续 assemble_context re-read 看到的就是真值.

    仅写 `root_params_fields` 中声明的字段 (避免覆盖 review_status 等关键 attrs).
    """
    if not params or not root_params_fields:
        return
    safe: dict[str, Any] = {
        k: v for k, v in params.items() if k in root_params_fields
    }
    if not safe:
        return
    with engine.begin() as conn:
        conn.execute(
            _APPLY_PARAMS_SQL,
            {"params": json.dumps(safe), "sid": source_id, "sys": source_system},
        )


# ---------------------------------------------------------------------------
# cut-042 — pack-driven six-step loop (`run_demo_loop`).
#
# This is the generic counterpart to `run_v0_loop`. It reads intent / rule /
# subject_entity_type / decision_key / source_system from `scenario_spec` and
# resolves the rule function via `ece.demo.registry.get_rule(...)`. No
# `ece.domain_packs` import exists in the call graph from here on — the
# registry decouples engine from pack.
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

    cut-042R F2/F3/F4: this body is now pack-agnostic:
      - source_system, pack, default_root_source_id come from scenario_spec
      - step [0] applies API params to root.attrs (F3)
      - step [5]/[6] handle 0-evidence case for auto_approved (F4)
    """
    params = params or {}
    _ensure_pack_registered(scenario_spec.pack)  # idempotent; see below
    # Defer the registry import to runtime to break the
    # v0.loop ↔ demo.api ↔ demo.loop cycle at module load time.
    from ece.demo.registry import get_rule
    descriptor = get_rule(scenario_spec.rule_id)

    source_system = scenario_spec.source_system
    if not source_system:
        raise ValueError(
            f"ScenarioSpec.source_system is required for pack={scenario_spec.pack!r} "
            f"spec={scenario_spec.spec!r}; declare it in scenarios/{scenario_spec.spec}.yaml"
        )

    # [1] assemble_context — pack-agnostic, intent + root_entity come from spec.
    #     READ-ONLY: this step MUST NOT mutate any DB row. All writes happen
    #     AFTER the permission check, on the allowed path only (R2-F1).
    display_id = _resolve_display_id(engine, root_source_id, source_system)
    root_type = str(scenario_spec.root_entity["type"])
    ctx = assemble_context(
        engine, user_ref, scenario_spec.spec,
        [{"type": root_type, "id": display_id}],
        pack=scenario_spec.pack,
    )

    # [2] extract root + SELECTS quotes; denied → early return (ZERO WRITE).
    root = next((e for e in ctx.entities if e["type"] == root_type), None)
    quotes = [r for r in ctx.relationships if r["rel"] == "SELECTS"]
    counts = {"entities": len(ctx.entities), "relationships": len(ctx.relationships)}

    if ctx.denied and root is None:
        # cut-042R2 R2-F1 — denied branch is ZERO-WRITE. No _apply_params_to_root_attrs,
        # no materializer, no rule, no evidence, no apply_context_update. The only
        # work is returning the result; the DB stays byte-equal to before the request.
        return _result_factory(
            package_id=ctx.package_id,
            # cut-042R F5: business language via mapper, not here. The V0 spike
            # returns its legacy `reason` for the 47 regression tests; the API
            # mapper converts this to "调用者无权访问此场景" at the contract layer.
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

    # [3a] cut-042R F3 — write API params to root.attrs (allowed path only).
    #     cut-042R2 R2-F1 — moved here from step [0] (was BEFORE permission check).
    _apply_params_to_root_attrs(
        engine, root_source_id, source_system,
        effective_params, scenario_spec.root_params_fields,
    )

    # [3b] cut-042R2 R2-F2 — pack-owned deterministic relations materializer
    #     (allowed path only). Rebuilds SELECTS relations count to match
    #     params.relations_fields (e.g. quote_count). Called BEFORE re-assemble
    #     so the rule sees the new state.
    if descriptor.materialize_fn is not None and scenario_spec.relations_fields:
        for _field in scenario_spec.relations_fields:
            descriptor.materialize_fn(engine, root_source_id, effective_params)

    # [3c] cut-042R2 R2-F1 — re-assemble context so the rule sees the
    #     materialized values (post-3a/3b writes). Without this re-assemble,
    #     the rule would compute against pre-materialize state, leaving
    #     evidence observed_value out of sync with DB.
    ctx = assemble_context(
        engine, user_ref, scenario_spec.spec,
        [{"type": root_type, "id": display_id}],
        pack=scenario_spec.pack,
    )
    root = next((e for e in ctx.entities if e["type"] == root_type), None)
    assert root is not None, "re-read lost root entity after materialize"
    quotes = [r for r in ctx.relationships if r["rel"] == "SELECTS"]
    counts = {"entities": len(ctx.entities), "relationships": len(ctx.relationships)}

    # [3c-refresh] cut-042R3 R3-B1 — ALWAYS refresh effective_params from the
    #     post-materialize re-read, regardless of whether the client provided
    #     a value. The previous guard ("if not in params") caused inconsistency
    #     when client passed quote_count=999 (materializer clamps to 3, DB has
    #     3, but effective_params still had 999 → rule/evidence/reason drifted
    #     from DB). Now re-read IS the source of truth for both amount and
    #     quote_count.
    effective_params["amount"] = root["attrs"].get("amount", 0)
    effective_params["quote_count"] = len(quotes)

    # [4] [5] rule + decision + evidence — pure functions from registry.
    conditions = descriptor.evaluate_fn(ctx, effective_params)
    dec = descriptor.build_decision_fn(conditions, ctx)

    persist_evidence(
        engine, ctx, dec,
        subject_entity_type=scenario_spec.subject_entity_type,
    )
    rows = get_evidence_for_decision(engine, dec["decision_id"])
    evidence_ids = [r["evidence_id"] for r in rows]

    # cut-042R F4 — handle 0-evidence case for clean/auto_approved path.
    # cut-043R R5-B2 — generalize: ANY decision_value on the pack's
    # `zero_evidence_decisions` allowlist is permitted with no evidence rows.
    # Procurement declares ["auto_approved"]; knowledge declares
    # ["needs_valid_policy"] so a double-failure (validity AND permission both
    # failed) does not 500.
    primary_evidence_id: str | None = evidence_ids[0] if evidence_ids else None
    allowed_zero_evidence = set(scenario_spec.zero_evidence_decisions or ())
    if primary_evidence_id is None and dec["decision_value"] not in allowed_zero_evidence:
        raise RuntimeError(
            f"decision {dec['decision_value']!r} has no evidence rows but is not in "
            f"scenario_spec.zero_evidence_decisions={sorted(allowed_zero_evidence)}; "
            f"evidence_ids={evidence_ids}, conditions={conditions}"
        )

    # [6] apply_context_update + re-read through assembly path.
    apply_context_update(
        engine, root_source_id, source_system, dec, primary_evidence_id,
        zero_evidence_decisions=scenario_spec.zero_evidence_decisions,
    )
    re_read_attrs = _re_read_through_assembly(
        engine, user_ref, display_id, root_type, scenario_spec.spec,
        scenario_spec.pack,
    )
    _assert_loop_closed(
        dec, re_read_attrs, engine, display_id, scenario_spec.decision_key,
    )

    # cut-042R F5: V0 spike returns its legacy `reason="ok"` here for the 47
    # regression tests; the API mapper converts this to the rule's business
    # reason at the contract layer (`ece.demo.mapper.to_business`).
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


# cut-042: lazy pack registration. Packs self-register their rules when their
# `scenarios` package is first imported (which transitively imports `agent.*`).
# To avoid forcing every V0 spike test to import the pack at module load time
# (which would re-couple engine and pack statically), we trigger the import
# inside the loop on first call. This keeps the import graph:
#   engine  →  registry  ←  pack (via runtime importlib)
# and preserves `ece → ece.domain_packs` static-import contract for lint-imports.
_REGISTERED_PACKS: set[str] = set()


def _ensure_pack_registered(pack: str) -> None:
    """cut-042R F2 — generic pack side-effect trigger (no pack-name hardcode).

    Packs self-register via their `scenarios/__init__.py` (which imports the
    pack's `agent.*` module that calls `_register_for_demo`). We import
    `ece.domain_packs.<pack>.scenarios` here — generic across all packs.

    Packs without a `scenarios` module (or with no registration side-effect)
    are silently skipped. The pack name itself is treated as a safe identifier
    by the caller (see `ece.demo.spec._SAFE_IDENTIFIER`); this function does
    not re-validate.
    """
    if pack in _REGISTERED_PACKS:
        return
    with contextlib.suppress(ModuleNotFoundError):
        importlib.import_module(f"ece.domain_packs.{pack}.scenarios")
    _REGISTERED_PACKS.add(pack)
