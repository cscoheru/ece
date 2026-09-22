"""cut-043 (Knowledge Management) — Rule R-KM-ACCESS + Decision builder.

Per PRD §6 row 2:
  "员工提问、制度版本 → 政策版本在有效期内 ∧ 员工有权限 → 有据回答;
   过期/无权限 → 提示提供有效版本 → 回答 + 出处链（证据同构）"

Hard contract enforced here (and asserted by
`tests/unit/test_knowledge_rule_and_decision.py`):

  - Pure functions. No external integrations, no ORM or DB connection, no model
    inference call. Every output is a pure function of the inputs.
  - `evaluate_rule_R_KM_ACCESS(policy, employee, today)` always returns exactly
    two conditions in a fixed order, each with the six keys the S2 decision
    needs (name, expr, actual, threshold, passed, claim).
  - `build_decision(conditions, ctx)` returns the eight-key Decision schema. It
    reads `ctx.package_id` and `ctx.request_id` for two of them; it generates
    the `decision_id` itself.
  - `reason` is a pure function of the conditions — byte-identical across calls,
    no datetime/time/uuid/timestamp leakage.

Why rule-layer temporal check (not `as_of` in assemble_context):
  `ece.demo.loop.run_demo_loop` does NOT pass `as_of` to `assemble_context`,
  so temporal filtering must be done in the rule body. The policy's
  `valid_from` / `valid_to` attrs are read here and compared against the
  caller-supplied `today` (which is part of the test parametrize, not
  system-time — keeps the rule deterministic, testable).

Why rule-layer permission check (not engine check_permission):
  PRD §7 纪律 #2 demands a *demonstration* of denied users. The KM "员工有权限"
  semantic is a *rule-level* lookup against `employee.attrs.roles`, NOT an
  engine-level ACL. The denied_users list in ScenarioSpec is the engine-level
  gate; the rule body is the business-rule gate.

Module purity (S3 criterion 5): this file MUST NOT import the DB-driver ORM
or hold a DB handle — the relations materializer (if any) would live in a
separate module (mirrors `procurement/agent/materializer.py`). cut-043 KM
needs no materializer (policy/permission relations are static in the fixture).
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
    "evaluate_rule_R_KM_ACCESS",
]


RULE_ID = "R-KM-ACCESS"
# cut-043 — decision_key="review_status" mirrors S4's write-back slot; the domain
# semantics live in `decision_value` ("answerable" / "needs_valid_policy"). This
# keeps the loop's re-read invariant (`root.attrs[decision_key] == decision_value`)
# working without a per-pack JSONB key migration. Documented as a known wart;
# cut-045 may generalize S4 to write back by decision_key rather than the four
# hard-coded review_* fields.
DECISION_KEY = "review_status"
DECISION_ID_PREFIX = "dec_"

_CONDITION_KEYS = ("name", "expr", "actual", "threshold", "passed", "claim")


def evaluate_rule_R_KM_ACCESS(  # noqa: N802 (spec-mandated name per PRD §6)
    policy: dict[str, Any],
    employee: dict[str, Any],
    today: str,  # ISO date string 'YYYY-MM-DD' — kept string for determinism + JSONB round-trip
) -> list[dict[str, Any]]:
    """Evaluate R-KM-ACCESS.

    Always returns two conditions, in a fixed order:

        0. policy_in_validity_window      — passes iff valid_from <= today < valid_to
        1. employee_has_read_permission   — passes iff required_role in employee.roles

    Each condition carries all six keys `evaluated_conditions` needs downstream:
    `name`, `expr`, `actual`, `threshold`, `passed`, `claim`. `claim` and
    `threshold` are kept on the condition (not derived in the persistence
    layer) because they are business-language statements that the rule layer
    is the right place for — mirrors the procurement S3 design.

    `policy` and `employee` are dicts sourced from Context entities' `attrs`
    (JSONB). Expected keys:

        policy:
          - valid_from: str (ISO date)
          - valid_to:   str (ISO date)
          - required_role: str
          - id:         str (e.g. "KM-POL-001") — used in claim text

        employee:
          - id:    str (e.g. "km-alice")
          - roles: list[str] (e.g. ["hr"])

    `today` is the caller's anchor date (not system-time). The rule must be
    pure, so we never read datetime.now() here — that would break N=10
    byte-equal determinism.
    """
    # Defensive parsing — string-typed JSONB values come back as strings.
    valid_from = str(policy.get("valid_from", ""))
    valid_to = str(policy.get("valid_to", ""))
    required_role = str(policy.get("required_role", ""))
    policy_id = str(policy.get("id", policy.get("source_id", "")))

    employee_id = str(employee.get("id", employee.get("source_id", "")))
    employee_roles = list(employee.get("roles", []) or [])

    in_window = (valid_from <= today < valid_to) if (valid_from and valid_to) else False
    has_perm = required_role in employee_roles if required_role else False

    # cut-043 — evidence_records.observed_value / threshold_value are NUMERIC columns
    # (per src/ece/migrations/versions/0008_evidence_records.py:49-50), so the rule
    # body emits a 0/1 pass-flag for both the validity and permission conditions.
    # The date / role / human-readable details live in `claim` (a free-text string),
    # preserving the "evidence 同构 (per PRD §6)" invariant: every pack's evidence
    # rows store a structured pass-flag plus a business-language claim.
    validity_claim = (
        f"制度 {policy_id} 在有效期内（{valid_from} 至 {valid_to}，今日 {today}）"
        if in_window
        else f"制度 {policy_id} 不在有效期内（{valid_from} 至 {valid_to}，今日 {today}）"
    )
    permission_claim = (
        f"员工 {employee_id} 具备 '{required_role}' 角色，可访问此制度"
        if has_perm
        else f"员工 {employee_id} 缺少 '{required_role}' 角色，无权访问此制度"
    )

    return [
        {
            "name": "policy_in_validity_window",
            "expr": f"valid_from <= today < valid_to ({valid_from} <= {today} < {valid_to})",
            "actual": 1 if in_window else 0,
            "threshold": 1,
            "passed": in_window,
            "claim": validity_claim,
        },
        {
            "name": "employee_has_read_permission",
            "expr": f"required_role {required_role!r} in employee.roles {employee_roles}",
            "actual": 1 if has_perm else 0,
            "threshold": 1,
            "passed": has_perm,
            "claim": permission_claim,
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
        validity AND permission  → "answerable"             (有据回答)
        validity OR permission failed → "needs_valid_policy" (提示提供有效版本)
    """
    by_name = {c["name"]: c for c in conditions}
    validity_passed = by_name["policy_in_validity_window"]["passed"]
    permission_passed = by_name["employee_has_read_permission"]["passed"]
    decision_value = "answerable" if (validity_passed and permission_passed) else "needs_valid_policy"

    return {
        "decision_id": f"{DECISION_ID_PREFIX}{uuid.uuid4()}",
        "rule_id": RULE_ID,
        "decision_key": DECISION_KEY,
        "decision_value": decision_value,
        "evaluated_conditions": list(conditions),
        "reason": _build_reason(validity_passed, permission_passed, by_name),
        "input_context_ref": ctx.package_id,
        "request_id": ctx.request_id,
    }


def _build_reason(
    validity_passed: bool,
    permission_passed: bool,
    by_name: dict[str, dict[str, Any]],
) -> str:
    """Render the reason string as a pure function of the conditions.

    Three branches; no datetime, no uuid, no timestamp — so N=10 calls byte-equal.
    """
    validity_claim = by_name["policy_in_validity_window"]["claim"]
    permission_claim = by_name["employee_has_read_permission"]["claim"]

    if validity_passed and permission_passed:
        return f"{validity_claim}；{permission_claim} → 有据可答"
    if not validity_passed and not permission_passed:
        return f"{validity_claim}；{permission_claim} → 请提供有效版本并确认访问权限"
    if not validity_passed:
        return f"{validity_claim}；{permission_claim} → 请提供当前有效版本"
    return f"{validity_claim}；{permission_claim} → 当前用户无访问权限，请联系制度归口部门"


# cut-043 — pack self-registration via the ece.demo rule registry.
# The original S3 function `evaluate_rule_R_KM_ACCESS(policy, employee, today)` keeps
# its signature (locked by tests/unit/test_knowledge_rule_and_decision.py); we adapt
# it to the generic `(ctx, params) -> conditions` registry contract by pulling
# policy/employee from the Context and params dict.
#
# Import is a runtime side-effect, delayed to module bottom so pack modules don't
# form an import cycle with the engine.


def _register_for_demo() -> None:
    from ece.demo.registry import register_rule

    def _evaluate_via_params(ctx: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
        # Resolve policy (root) from the assembled Context, and the employee
        # directly from `ctx.user` (assemble_context has already resolved the
        # caller's identity including their roles — no need to load a separate
        # person entity). The rule sees *materialized* truth, mirroring the
        # procurement R3-B1 fix in cut-042R3.
        ctx_entities = getattr(ctx, "entities", []) or []
        policy = next(
            (
                {**e.get("attrs", {}), "id": e.get("source_id", e.get("ref", ""))}
                for e in ctx_entities
                if e.get("type") == "policy_document"
            ),
            {},
        )
        # Employee = the caller; assemble_context puts roles on ctx.user.
        ctx_user = getattr(ctx, "user", {}) or {}
        employee_entity = {
            "id": ctx_user.get("id") or params.get("employee_id", ""),
            "roles": list(ctx_user.get("roles", []) or []),
        }
        today = str(params.get("today") or "2026-09-22")
        return evaluate_rule_R_KM_ACCESS(policy, employee_entity, today)

    register_rule(
        RULE_ID,
        decision_key=DECISION_KEY,
        evaluate_fn=_evaluate_via_params,
        build_decision_fn=build_decision,
        # cut-043 KM has no materializer — policy/permission relations are
        # static in the fixture (mirrors the procurement spike design intent).
        materialize_fn=None,
    )


_register_for_demo()
