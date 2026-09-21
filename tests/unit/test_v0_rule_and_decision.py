"""S3 (V0 Technical Spike) — Rule R-SPIKE-REVIEW + Decision builder.

Per `docs/v0/V0_EXECUTION_SPEC.md` §5 (Rule) · §6 (Decision) · §9 step [3]/[4].
Per the binding acceptance criteria for S3 (审验者裁定, 2026-09-21).

This test file is the FIRST deliverable. The implementation in
`src/ece/domain_packs/procurement/agent/v0_rules.py` does not yet exist when this
file is checked in. The red→green→mutation sequence is recorded in
`docs/v0/S3_REPORT.md`.
"""
from __future__ import annotations

import re
import uuid

import pytest

from ece.context.assembly import ContextPackage
from ece.domain_packs.procurement.agent.rules import PRICE_COMPARISON_THRESHOLD
from ece.domain_packs.procurement.agent.v0_rules import (
    REQUIRED_QUOTES,
    build_decision,
    evaluate_rule_R_SPIKE_REVIEW,
)

RULE_ID = "R-SPIKE-REVIEW"
DECISION_KEY = "review_status"
CON_NAMES = ("amount_gte_threshold", "quote_count_lt_required")
EXPECTED_CON_KEYS = ("name", "expr", "actual", "threshold", "passed", "claim")

# Boundary values follow the constant so a future change to PRICE_COMPARISON_THRESHOLD
# keeps the boundary meaningful rather than precomputed.
AMOUNT_BELOW = PRICE_COMPARISON_THRESHOLD - 1
AMOUNT_AT = PRICE_COMPARISON_THRESHOLD
AMOUNT_ABOVE = PRICE_COMPARISON_THRESHOLD + 1

# expected decision_value matrix: review_required iff amount >= threshold AND quote_count < 3
def _expected_decision_value(amount: int, quote_count: int) -> str:
    if amount >= PRICE_COMPARISON_THRESHOLD and quote_count < REQUIRED_QUOTES:
        return "review_required"
    return "auto_approved"


_BOUNDARY_MATRIX: list[tuple[int, int]] = [
    (amount, qc)
    for amount in (AMOUNT_BELOW, AMOUNT_AT, AMOUNT_ABOVE)
    for qc in (0, 1, 2, 3, 4)
]


@pytest.mark.parametrize(("amount", "quote_count"), _BOUNDARY_MATRIX)
def test_boundary_matrix_decision_value(amount: int, quote_count: int) -> None:
    """Criterion 2: 15 cases, all four outputs verifiable."""
    conditions = evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)

    # The rule must always emit BOTH conditions (criterion 4) ...
    assert len(conditions) == 2
    assert {c["name"] for c in conditions} == set(CON_NAMES)
    # ... each with all six keys (criterion 4 + the S2 carryover)
    for cond in conditions:
        assert set(cond.keys()) == set(EXPECTED_CON_KEYS)

    ctx = _context()
    decision = build_decision(conditions, ctx)

    expected = _expected_decision_value(amount, quote_count)
    assert decision["decision_value"] == expected, (
        f"amount={amount:,} quote_count={quote_count} → expected {expected}, "
        f"got {decision['decision_value']}"
    )

    # `actual` of amount_gte_threshold must equal the amount; of quote_count_lt_required
    # must equal the quote_count. `threshold` must reference the constant, not a literal.
    by_name = {c["name"]: c for c in conditions}
    assert by_name["amount_gte_threshold"]["actual"] == amount
    assert by_name["amount_gte_threshold"]["threshold"] == PRICE_COMPARISON_THRESHOLD
    assert by_name["quote_count_lt_required"]["actual"] == quote_count
    assert by_name["quote_count_lt_required"]["threshold"] == REQUIRED_QUOTES


def test_decision_schema_keys(criterion_ctx: ContextPackage) -> None:
    """Criterion 6: all eight keys present with the right shapes."""
    decision = build_decision(
        evaluate_rule_R_SPIKE_REVIEW(AMOUNT_ABOVE, 1), criterion_ctx
    )
    expected = {
        "decision_id",
        "rule_id",
        "decision_key",
        "decision_value",
        "evaluated_conditions",
        "reason",
        "input_context_ref",
        "request_id",
    }
    assert set(decision.keys()) == expected
    assert decision["rule_id"] == RULE_ID
    assert decision["decision_key"] == DECISION_KEY
    assert decision["decision_value"] == "review_required"
    assert decision["input_context_ref"] == criterion_ctx.package_id
    assert decision["request_id"] == criterion_ctx.request_id
    assert decision["decision_id"].startswith("dec_")


@pytest.mark.parametrize("amount", [AMOUNT_BELOW, AMOUNT_AT, AMOUNT_ABOVE])
def test_reason_is_deterministic_and_free_of_timestamps(amount: int) -> None:
    """Criterion 3 implicitly: reason must not include time, so byte-equal across calls.

    Beyond N=10 we explicitly check the string never contains a time-like substring,
    which catches a hidden `datetime.now()` slipped into the reasoning text.
    """
    _time_pattern = re.compile(r"\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}|T\d{2}:")
    ctx = _context()
    conditions = evaluate_rule_R_SPIKE_REVIEW(amount, 1)
    reasons: set[str] = set()
    for _ in range(10):
        reasons.add(build_decision(conditions, ctx)["reason"])
    assert len(reasons) == 1, (
        f"reason is not a pure function of its inputs; got {len(reasons)} distinct values: "
        f"{sorted(reasons)}"
    )
    the_reason = next(iter(reasons))
    assert _time_pattern.search(the_reason) is None, (
        "reason contains a time-like substring; the rule is supposed to be deterministic: "
        f"{the_reason!r}"
    )


def test_n_10_determinism_excluding_decision_id(criterion_ctx: ContextPackage) -> None:
    """Criterion 3: same input 10× → decision_value, evaluated_conditions, reason match.
    decision_id is excluded because it is a fresh uuid per call.
    """
    amount, quote_count = AMOUNT_ABOVE, 1
    conditions = evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)
    decisions = [
        build_decision(conditions, criterion_ctx) for _ in range(10)
    ]

    # decision_value, evaluated_conditions, reason identical across all calls
    first = decisions[0]
    for d in decisions[1:]:
        assert d["decision_value"] == first["decision_value"]
        assert d["evaluated_conditions"] == first["evaluated_conditions"]
        assert d["reason"] == first["reason"]
        # Per the ruling: identical WITHOUT comparing decision_id.
        assert d["decision_id"] != first["decision_id"], (
            "this assertion is a positive control: every call must produce a new uuid"
        )


def test_both_conditions_always_present() -> None:
    """Criterion 4: amount_gte_threshold and quote_count_lt_required are always emitted,
    even when one fails. The Decision's review_required depends on BOTH failing's absence,
    so dropping one would corrupt the semantics.
    """
    cases = [(0, 0), (AMOUNT_AT, 1), (AMOUNT_ABOVE, REQUIRED_QUOTES), (AMOUNT_BELOW, REQUIRED_QUOTES + 1)]
    for amount, qc in cases:
        conds = evaluate_rule_R_SPIKE_REVIEW(amount, qc)
        names = [c["name"] for c in conds]
        assert names == ["amount_gte_threshold", "quote_count_lt_required"], (
            f"both conditions must always be present; amount={amount} qc={qc} gave {names}"
        )


def test_module_purity_no_sqlalchemy_no_engine() -> None:
    """Criterion 5: the rule module must not import sqlalchemy and must not hold an Engine."""
    import sys

    import ece.domain_packs.procurement.agent.v0_rules as mod

    with open(mod.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "sqlalchemy" not in src, (
        "the rule module is supposed to be a pure function; sqlalchemy would let it reach the DB"
    )
    assert "Engine" not in src, (
        "the rule module is supposed to hold no DB handle"
    )

    for name in list(sys.modules):
        if name.endswith("v0_rules"):
            for attr in ("engine", "Engine", "session", "Session"):
                assert not hasattr(mod, attr), (
                    f"the rule module must not hold a {attr}"
                )


def test_does_not_call_llm() -> None:
    """Criterion 5 + 7: the rule is deterministic and does not route through LLM."""
    import ece.domain_packs.procurement.agent.v0_rules as mod

    with open(mod.__file__, encoding="utf-8") as fh:
        src = fh.read()
    for forbidden in ("openai", "anthropic", "provider", "LLM"):
        assert forbidden.lower() not in src.lower(), (
            f"the rule must not call into an LLM; found {forbidden!r}"
        )


# ---------- fixtures / helpers ----------

def _context() -> ContextPackage:
    """A minimal ContextPackage shaped like the real one (assembly.py:43-...).

    Hand-built so the rule test is independent of the spike fixture. The real package
    wiring is S5/S6's job.
    """
    return ContextPackage(
        package_id="ctx_000000000000000000000001",
        request_id=str(uuid.uuid4()),
        task={"intent": "evaluate_purchase_request", "spec_version": 1},
        user={"id": "spike-user-procurement", "display_id": "U-SYNTHETIC",
              "name": "", "department": "procurement", "roles": ["buyer"], "is_management": False},
        entities=[],
        relationships=[],
        denied=[],
        sources=[],
        metadata={},
    )


@pytest.fixture()
def criterion_ctx() -> ContextPackage:
    return _context()
