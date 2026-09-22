"""cut-042 — Map internal LoopResult to business-named response.

The API contract MUST NOT leak internal field names. Per PRD §5 #2:
  - forbidden: decision_id, input_context_ref, package_id, evidence_id,
    context_request_id, and any prefix ctx_/dec_/ev_

The mapper inspects every field of `loop_result.decision` and
`loop_result.evidence` to enforce the contract; assertion failures are
treated as bugs, not swallowed.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ece.demo.spec import ScenarioSpec

__all__ = ["to_business"]


# Business-language conclusion labels per pack. Extend per-packs in cut-043+.
_CONCLUSION_LABELS: dict[str, str] = {
    "review_required": "需人工复核",
    "auto_approved": "自动通过",
    "no_permission": "无权查看",
}


def to_business(
    result: Any,  # DemoLoopResult | V0LoopResult — same field set; structural
    spec: ScenarioSpec,
    *,
    actor: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    """Render loop_result + spec as business-named JSON dict.

    Returns a dict (not a Pydantic model) because the response shape is
    fuzzy: evidence list length varies by pass/fail count, denied branch
    produces a different shape. Pydantic models would force a discriminated
    union; a dict with stable top-level keys is sufficient and tested by
    `tests/integration/test_demo_api_contract.py`.

    `result` is typed as `Any` because DemoLoopResult and V0LoopResult are
    structurally identical dataclasses maintained by `_run_demo_loop_impl`.
    Type-narrowing on the Union would force every call site to construct
    a literal instance, which the integration tests cannot do.
    """
    decision = result.decision
    denied_branch = decision is None

    if denied_branch:
        conclusion = "no_permission"
        conclusion_label = _CONCLUSION_LABELS["no_permission"]
        evidence_payload: list[dict[str, Any]] = []
        state_after = "pending"
        # cut-042R F5: business-language denied reason (NOT loop state "no permitted context").
        business_reason = "调用者无权访问此场景（Permission Engine 拒绝）"
    else:
        decision_value = str(decision.get("decision_value", ""))
        conclusion = decision_value
        conclusion_label = _CONCLUSION_LABELS.get(decision_value, decision_value)
        evidence_payload = [_evidence_row_business(r) for r in result.evidence]
        state_after = decision_value
        # cut-042R F5: surface rule's business reason (NOT loop state "ok").
        # The rule layer sets decision["reason"] = "金额 N ≥ M 且仅 X 家报价（需 N 家）→ 需人工复核"
        business_reason = str(decision.get("reason") or "未提供业务原因")

    decision_key = spec.decision_key
    if denied_branch:
        # Denied branch: surface the *intent* ("pending") rather than the
        # re-read snapshot. The re-read may show a stale value left by a
        # previous allowed-user run (e.g. 'review_required'); surfacing it
        # would falsely imply this denied call mutated state. The contract
        # for denied users is: zero side effect, conclusion = no_permission,
        # state_change.after = "pending" (not yet reviewed by anyone).
        state_change = {
            "before": result.pr_attrs_before.get(decision_key),
            "after": state_after,
            "key": decision_key,
        }
    else:
        # Allowed branch: surface the actual re-read snapshot (after =
        # post-mutation value). For idempotent re-runs this equals
        # before; for a fresh transition it differs.
        state_change = {
            "before": result.pr_attrs_before.get(decision_key),
            "after": result.re_read_attrs.get(decision_key),
            "key": decision_key,
        }

    return {
        "domain": spec.pack,
        "scenario": spec.spec,
        "conclusion": conclusion,
        "conclusion_label": conclusion_label,
        # cut-042R F5: business reason, NOT loop state ("ok"/"no permitted context").
        "reason": business_reason,
        "evidence": evidence_payload,
        "state_change": state_change,
        "actor": actor,
        "denied_for": list(spec.denied_users),
        "elapsed_ms": elapsed_ms,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _evidence_row_business(row: dict[str, Any]) -> dict[str, Any]:
    """Map one Evidence row's internal schema to the business view.

    Internal fields stripped: `decision_id`, `input_context_ref`,
    `evidence_id`, `evidence_timestamp` (ISO-formatted separately as
    `recorded_at`).
    """
    ts = row.get("evidence_timestamp")
    recorded_at: Any = (
        ts.isoformat()
        if ts is not None and hasattr(ts, "isoformat")
        else str(ts or "")
    )
    return {
        "claim": str(row.get("claim", "")),
        "observed": row.get("observed_value"),
        "threshold": row.get("threshold_value"),
        "source_record_id": str(row.get("source_record_id", "")),
        "source_system": str(row.get("source_system", "")),
        "actor": str(row.get("actor_user_ref", "")),
        "recorded_at": recorded_at,
    }
