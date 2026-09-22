"""S3 (V0 Technical Spike) — Rule R-SPIKE-REVIEW + Decision builder.

Per `docs/v0/V0_EXECUTION_SPEC.md` §5 / §6 / §9 step [3]+[4].
Per the binding acceptance criteria for S3 (审验者裁定, 2026-09-21).

Hard contract enforced here (and asserted by `tests/unit/test_v0_rule_and_decision.py`):

  - Pure functions. No external integrations, no ORM or DB connection, no model
    inference call. Every output is a pure function of the inputs.
  - `evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)` always returns exactly two
    conditions in a fixed order, each with the six keys the S2 decision needs.
  - `build_decision(conditions, ctx)` returns the eight-key Decision schema. It reads
    `ctx.package_id` and `ctx.request_id` for two of them; it generates the
    `decision_id` itself. No new abstraction.
  - `reason` is a pure function of the conditions — byte-identical across calls and
    free of time-like substrings, so it cannot carry hidden non-determinism.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from ece.domain_packs.procurement.agent.rules import PRICE_COMPARISON_THRESHOLD

if TYPE_CHECKING:
    from ece.context.assembly import ContextPackage

__all__ = [
    "DECISION_ID_PREFIX",
    "RULE_ID",
    "DECISION_KEY",
    "REQUIRED_QUOTES",
    "build_decision",
    "evaluate_rule_R_SPIKE_REVIEW",
]

# The minimum number of supplier quotes required to skip price-comparison review.
# Per `docs/v0/V0_EXECUTION_SPEC.md` §5; rules.py has no existing constant for this.
REQUIRED_QUOTES = 3

RULE_ID = "R-SPIKE-REVIEW"
DECISION_KEY = "review_status"
DECISION_ID_PREFIX = "dec_"

_CONDITION_KEYS = ("name", "expr", "actual", "threshold", "passed", "claim")


def evaluate_rule_R_SPIKE_REVIEW(amount: int, quote_count: int) -> list[dict[str, Any]]:  # noqa: N802 (spec-mandated name per `docs/v0/V0_EXECUTION_SPEC.md` §5/§9)
    """Evaluate R-SPIKE-REVIEW.

    Always returns two conditions, in a fixed order:

        0. amount_gte_threshold   — passes iff amount >= PRICE_COMPARISON_THRESHOLD
        1. quote_count_lt_required — passes iff quote_count < REQUIRED_QUOTES

    Each condition carries all six keys `evaluated_conditions` needs downstream:
    `name`, `expr`, `actual`, `threshold`, `passed`, `claim`. `claim` and `threshold`
    are kept on the condition (not derived in the persistence layer) because they are
    business-language statements that the rule layer is the right place for — see the
    S2 review record on the §6/§7 spec gap.
    """
    amount_passed = amount >= PRICE_COMPARISON_THRESHOLD
    quote_count_passed = quote_count < REQUIRED_QUOTES

    return [
        {
            "name": "amount_gte_threshold",
            "expr": f"amount >= {PRICE_COMPARISON_THRESHOLD}",
            "actual": amount,
            "threshold": PRICE_COMPARISON_THRESHOLD,
            "passed": amount_passed,
            "claim": f"金额 {amount:,} {'≥' if amount_passed else '<'} "
                     f"{PRICE_COMPARISON_THRESHOLD:,}",
        },
        {
            "name": "quote_count_lt_required",
            "expr": f"quote_count < {REQUIRED_QUOTES}",
            "actual": quote_count,
            "threshold": REQUIRED_QUOTES,
            "passed": quote_count_passed,
            "claim": f"报价家数 {quote_count} {'<' if quote_count_passed else '≥'} "
                     f"{REQUIRED_QUOTES}",
        },
    ]


def build_decision(
    conditions: list[dict[str, Any]],
    ctx: ContextPackage,
) -> dict[str, Any]:
    """Build the eight-key Decision dict.

    Two values are read from the Context (`package_id` → `input_context_ref`,
    `request_id`); `decision_id` is generated here. No other state crosses the boundary.
    """
    by_name = {c["name"]: c for c in conditions}
    amount_passed = by_name["amount_gte_threshold"]["passed"]
    quote_count_passed = by_name["quote_count_lt_required"]["passed"]
    decision_value = "review_required" if amount_passed and quote_count_passed else "auto_approved"

    return {
        "decision_id": f"{DECISION_ID_PREFIX}{uuid.uuid4()}",
        "rule_id": RULE_ID,
        "decision_key": DECISION_KEY,
        "decision_value": decision_value,
        "evaluated_conditions": list(conditions),
        "reason": _build_reason(amount_passed, quote_count_passed, by_name),
        "input_context_ref": ctx.package_id,
        "request_id": ctx.request_id,
    }


def _build_reason(
    amount_passed: bool,
    quote_count_passed: bool,
    by_name: dict[str, dict[str, Any]],
) -> str:
    """Render the reason string as a pure function of the conditions.

    Three branches; no datetime, no uuid, no timestamp — so N=10 calls byte-equal.
    """
    amount = by_name["amount_gte_threshold"]["actual"]
    threshold = by_name["amount_gte_threshold"]["threshold"]
    quote_count = by_name["quote_count_lt_required"]["actual"]
    if amount_passed and quote_count_passed:
        return (
            f"金额 {amount:,} ≥ {threshold:,} 且仅 {quote_count} 家报价"
            f"（需 {REQUIRED_QUOTES} 家）→ 需人工复核"
        )
    if not amount_passed:
        return f"金额 {amount:,} < {threshold:,} → 免比价"
    return (
        f"金额 {amount:,} ≥ {threshold:,} 且已 {quote_count} 家报价"
        f"（≥{REQUIRED_QUOTES}）→ 自动通过"
    )


# cut-042: pack self-registration via the ece.demo rule registry. The original
# S3 function `evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)` keeps its
# signature (locked by tests/unit/test_v0_rule_and_decision.py); we adapt it
# to the generic `(ctx, params) -> conditions` registry contract by partial
# application over the params dict. No behavioral change to the rule itself.
#
# This import is a runtime side-effect, not a static top-of-file import — the
# `from ece.demo.registry import register_rule` is delayed to module bottom so
# pack modules don't form an import cycle with the engine.
def _register_for_demo() -> None:
    from ece.demo.registry import register_rule

    def _evaluate_via_params(ctx: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
        # params keys mirror the rule's original signature: amount, quote_count.
        # Fall back to ctx-derived values when params omit them — keeps the
        # generic loop callable without scenario-specific wiring.
        amount = int(params.get("amount") or 0)
        quote_count = int(params.get("quote_count") or 0)
        return evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)

    register_rule(
        RULE_ID,
        decision_key=DECISION_KEY,
        evaluate_fn=_evaluate_via_params,
        build_decision_fn=build_decision,
    )


_register_for_demo()
