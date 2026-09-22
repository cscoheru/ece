"""cut-044 (Compliance) — Rule R-COMP-AUDIT + Decision builder.

Per PRD §6 row 3:
  "审计证据归集（EvidenceIQ-lite） → 控制项 + 审计期间 →
   期间内证据数 ≥ N ∧ 覆盖全部系统 → 充分；否则缺口清单 →
   证据包清单 + 缺口列表"

Hard contract enforced here (and asserted by
`tests/unit/test_compliance_rule_and_decision.py`):

  - Pure functions. No external integrations, no ORM or DB connection, no
    model inference call. Every output is a pure function of the inputs.
  - `evaluate_rule_R_COMP_AUDIT(control, evidence_set, today)` always returns
    exactly two conditions in a fixed order, each with the six keys the S2
    decision needs (name, expr, actual, threshold, passed, claim).
  - `build_decision(conditions, ctx)` returns the eight-key Decision dict.
  - `reason` is a pure function of the conditions — byte-identical across
    calls, no datetime/time/uuid/timestamp leakage.

Why two conditions, not one:
  PRD §6 row 3 splits the audit conclusion into two business gates:
    (1) 期间内证据数 ≥ N  — quantity gate
    (2) 覆盖全部系统        — coverage gate
  Both must pass for `evidence_package_sufficient`; any failure yields
  `gap_list`. Splitting the gate into two conditions preserves the
  "evidence 同构" invariant (per PRD §6) — every pack's evidence rows
  store a structured pass-flag plus a business-language claim.

Module purity (S3 criterion 5): this file MUST NOT import the DB-driver ORM
or hold a DB handle — the loop wrapper (`_evaluate_via_params` at module
bottom) resolves evidence_set from the assembled Context and passes it in
as a plain list[dict], keeping the rule layer deterministic + testable.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ece.context.assembly import ContextPackage

__all__ = [
    "DECISION_ID_PREFIX",
    "RULE_ID",
    "DECISION_KEY",
    "build_decision",
    "evaluate_rule_R_COMP_AUDIT",
]


RULE_ID = "R-COMP-AUDIT"
# cut-044 — decision_key="review_status" mirrors S4's write-back slot; the domain
# semantics live in `decision_value` ("evidence_package_sufficient" / "gap_list").
# This keeps the loop's re-read invariant working without a per-pack JSONB key
# migration (cut-043 wart → cut-045 may generalize decision_key write-back).
DECISION_KEY = "review_status"
DECISION_ID_PREFIX = "dec_"

_CONDITION_KEYS = ("name", "expr", "actual", "threshold", "passed", "claim")


def evaluate_rule_R_COMP_AUDIT(  # noqa: N802 (spec-mandated name per PRD §6)
    control: dict[str, Any],
    evidence_set: list[dict[str, Any]],
    request_period_start: str,
    request_period_end: str,
    today: str,  # ISO date string 'YYYY-MM-DD' — kept string for determinism + JSONB round-trip.
    # RESERVED: kept in signature for API stability + future staleness checks,
    # but does NOT participate in filtering — see docstring §3 (cut-044R1 R1-B1).
) -> list[dict[str, Any]]:
    """Evaluate R-COMP-AUDIT.

    Always returns two conditions, in a fixed order:

        0. evidence_count_meets_threshold   — passes iff count(evidence_in_audit) >= control.evidence_min
        1. system_coverage_complete         — passes iff control.required_systems ⊆ covered_systems

    Each condition carries all six keys `evaluated_conditions` needs downstream:
    `name`, `expr`, `actual`, `threshold`, `passed`, `claim`. `claim` and
    `threshold` are kept on the condition (not derived in the persistence
    layer) because they are business-language statements that the rule layer
    is the right place for — mirrors the procurement S3 + cut-043 KM design.

    `control` is a dict sourced from the Control entity's `attrs` (JSONB).
    Expected keys:
        - id:                str (e.g. "COMP-CTL-001")
        - required_systems:  list[str] (e.g. ["erp-system", "hr-system", "finance-system"])
        - evidence_min:      int (e.g. 3)

    `evidence_set` is a list of dicts sourced from evidence_package entities'
    `attrs` (JSONB). Expected per-item keys:
        - system:      str (e.g. "erp-system")
        - control_id:  str (e.g. "COMP-CTL-001")
        - period_start: str (ISO date 'YYYY-MM-DD')
        - period_end:   str (ISO date 'YYYY-MM-DD')

    `request_period_start` / `request_period_end` (cut-044R1 R1-B1):
    caller-supplied audit period. The API boundary MUST validate them as
    strict YYYY-MM-DD canonical round-trip + reversal check (mirror of
    cut-043R4 R8-B1). The rule filters by **intersection** — an evidence
    package is in-audit iff its `[period_start, period_end]` overlaps the
    request `[request_period_start, request_period_end]` window:
        ev.period_start <= request_period_end AND ev.period_end >= request_period_start
    Intersection (rather than containment) is the cut-044R1 design decision —
    see plan §2.1. Audit semantics: "evidence with any overlap of the audit
    window is in-scope for scrutiny."

    `today` (cut-044R1 R1-B1): reserved for future staleness checks
    (e.g. "reject evidence older than N days from today"). Currently it
    does NOT participate in filtering — the audit period + intersection
    filter alone decide inclusion. The parameter is kept in signature for
    API stability (callers already pass it) and to avoid a breaking
    change to other tests that import this function.
    """
    control_id = str(control.get("id", control.get("source_id", "")))
    required_systems = list(control.get("required_systems", []) or [])
    evidence_min = int(control.get("evidence_min", 0))

    # cut-044R1 R1-B1: filter by audit-period INTERSECTION, not by today
    # coverage. evidence_in_audit = evidence_set entries whose
    # [period_start, period_end] window has any overlap with the request
    # audit [request_period_start, request_period_end]. Empty strings are
    # treated as "no overlap" (defensive; API already rejects empties as 422).
    in_audit: list[dict[str, Any]] = []
    for ev in evidence_set:
        if str(ev.get("control_id", "")) != control_id:
            continue
        ev_ps = str(ev.get("period_start", "") or "")
        ev_pe = str(ev.get("period_end", "") or "")
        if not ev_ps or not ev_pe:
            continue
        if ev_ps <= request_period_end and ev_pe >= request_period_start:
            in_audit.append(ev)

    count = len(in_audit)
    covered_systems = {str(ev.get("system", "")) for ev in in_audit if ev.get("system")}
    required_set = set(required_systems)

    met_count = count >= evidence_min
    coverage_complete = required_set.issubset(covered_systems) if required_set else (count >= evidence_min)

    count_claim = (
        f"控制项 {control_id} 审计期间内证据 {count} 条, 已达阈值 ≥ {evidence_min} 条"
        if met_count
        else f"控制项 {control_id} 审计期间内证据 {count} 条, 不足阈值 ≥ {evidence_min} 条"
    )
    sorted_covered = sorted(covered_systems) if covered_systems else []
    sorted_required = sorted(required_set) if required_set else []
    sorted_missing = sorted(required_set - covered_systems)
    coverage_claim = (
        f"已覆盖系统 {sorted_covered}, 满足 {sorted_required} 的覆盖要求"
        if coverage_complete
        else f"已覆盖系统 {sorted_covered or '无'}, 缺少 {sorted_missing}"
    )

    return [
        {
            "name": "evidence_count_meets_threshold",
            "expr": (
                f"count(evidence_in_period for {control_id}) >= evidence_min "
                f"({count} >= {evidence_min})"
            ),
            "actual": count,
            "threshold": evidence_min,
            "passed": met_count,
            "claim": count_claim,
        },
        {
            "name": "system_coverage_complete",
            "expr": (
                f"required_systems {sorted_required} ⊆ covered_systems {sorted_covered}"
            ),
            # cut-044 — evidence_records.observed_value / threshold_value are NUMERIC
            # columns (per src/ece/migrations/versions/0008_evidence_records.py:49-50,
            # same S2 lock-down as cut-043 KM). Pass-flag is 0/1 int; the system
            # lists live in `claim` (free-text) to preserve the evidence-同构 invariant.
            "actual": 1 if coverage_complete else 0,
            "threshold": 1,
            "passed": coverage_complete,
            "claim": coverage_claim,
        },
    ]


def build_decision(
    conditions: list[dict[str, Any]],
    ctx: ContextPackage,
) -> dict[str, Any]:
    """Build the eight-key Decision dict (per V0 spike §7 schema).

    Two values are read from the Context (`package_id` → `input_context_ref`,
    `request_id`); `decision_id` is generated here. No other state crosses
    the boundary.

    decision_value semantics:
        both passed     → "evidence_package_sufficient"   (无缺口)
        any failed      → "gap_list"                      (存在缺口, on allowlist)

    `gap_list` is the cut-044 zero-evidence business outcome (PRD §6 row 3
    "缺口清单"). It is allowlisted via `zero_evidence_decisions: [gap_list]`
    in the ScenarioSpec so the generic loop does NOT raise RuntimeError
    when the rule emits 0 evidence (mirrors cut-043R R5-B2 lesson).
    """
    by_name = {c["name"]: c for c in conditions}
    count_passed = bool(by_name["evidence_count_meets_threshold"]["passed"])
    coverage_passed = bool(by_name["system_coverage_complete"]["passed"])
    decision_value = "evidence_package_sufficient" if (count_passed and coverage_passed) else "gap_list"

    return {
        "decision_id": f"{DECISION_ID_PREFIX}{uuid.uuid4()}",
        "rule_id": RULE_ID,
        "decision_key": DECISION_KEY,
        "decision_value": decision_value,
        "evaluated_conditions": list(conditions),
        "reason": _build_reason(count_passed, coverage_passed, by_name),
        "input_context_ref": ctx.package_id,
        "request_id": ctx.request_id,
    }


def _build_reason(
    count_passed: bool,
    coverage_passed: bool,
    by_name: dict[str, dict[str, Any]],
) -> str:
    """Render the reason string as a pure function of the conditions.

    Three branches; no datetime, no uuid, no timestamp — so N=10 calls byte-equal.
    """
    count_claim = by_name["evidence_count_meets_threshold"]["claim"]
    coverage_claim = by_name["system_coverage_complete"]["claim"]

    if count_passed and coverage_passed:
        return f"{count_claim}；{coverage_claim} → 无缺口, 审计证据包充分"
    if not count_passed and not coverage_passed:
        return f"{count_claim}；{coverage_claim} → 存在缺口, 需补充证据数量并覆盖缺失系统"
    if not count_passed:
        return f"{count_claim}；{coverage_claim} → 存在缺口, 证据数量不足"
    return f"{count_claim}；{coverage_claim} → 存在缺口, 系统覆盖不全"


# cut-044 — pack self-registration via the ece.demo rule registry.
# The pure function `evaluate_rule_R_COMP_AUDIT(control, evidence_set,
# request_period_start, request_period_end, today)` keeps its signature
# (locked by tests/unit/test_compliance_rule_and_decision.py); we adapt it
# to the generic `(ctx, params) -> conditions` registry contract by pulling
# control + evidence_set from the assembled Context and params dict, and
# routing `period_start` / `period_end` through to the rule's intersection
# filter (cut-044R1 R1-B1).
#
# Import is a runtime side-effect, delayed to module bottom so pack modules
# don't form an import cycle with the engine.


def _register_for_demo() -> None:
    from ece.demo.registry import register_rule

    def _evaluate_via_params(ctx: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
        ctx_entities = getattr(ctx, "entities", []) or []

        # Resolve control (root) from the assembled Context.
        # cut-044 design: evidence_packages are inlined into control.attrs
        # (NOT a separate entity type). The wrapper reads them directly
        # and adapts to the rule's (control, evidence_set, today) signature.
        control_entity = next(
            (
                {**e.get("attrs", {}), "id": e.get("ref", "")}
                for e in ctx_entities
                if e.get("type") == "control"
            ),
            {},
        )

        raw_evidence = control_entity.get("evidence_packages", []) or []
        evidence_set: list[dict[str, Any]] = []
        for ev in raw_evidence:
            if not isinstance(ev, dict):
                continue
            evidence_set.append(
                {
                    "system": str(ev.get("system", "") or ""),
                    "control_id": str(control_entity.get("id", "") or ""),
                    "period_start": str(ev.get("period_start", "") or ""),
                    "period_end": str(ev.get("period_end", "") or ""),
                }
            )

        today = str(params.get("today") or "2026-09-22")
        # cut-044R1 R1-B1: API boundary (api.py) already validates
        # period_start / period_end as strict YYYY-MM-DD canonical round-trip
        # + period_start <= period_end (422 otherwise). By the time we reach
        # this wrapper both fields are guaranteed non-empty + canonical.
        request_period_start = str(params.get("period_start") or "")
        request_period_end = str(params.get("period_end") or "")
        return evaluate_rule_R_COMP_AUDIT(
            control_entity,
            evidence_set,
            request_period_start,
            request_period_end,
            today,
        )

    register_rule(
        RULE_ID,
        decision_key=DECISION_KEY,
        evaluate_fn=_evaluate_via_params,
        build_decision_fn=build_decision,
        # cut-044 compliance has no materializer — control/system relations
        # are static in the fixture (mirrors cut-043 KM design intent).
        materialize_fn=None,
    )


_register_for_demo()
