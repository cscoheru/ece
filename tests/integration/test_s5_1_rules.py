"""S5.1 — Domain rules tests.

Verifies pure-Python rules (no LLM dependency):
- price_comparison_threshold (100万)
- price_deviation (current vs historical)
- approval_chain (3 roles for ≥100万)
- find_policy_matches (keyword overlap)
- apply_domain_rules (orchestrator)
"""

from ece.domain_packs.procurement.agent.rules import (
    apply_domain_rules,
    calculate_price_deviation,
    check_approval_chain,
    check_price_comparison_required,
    find_policy_matches,
)


def test_price_comparison_at_threshold_1m() -> None:
    needs, msg = check_price_comparison_required(1_000_000)
    assert needs is True
    assert "100万" in msg


def test_price_comparison_over_threshold_2m() -> None:
    needs, msg = check_price_comparison_required(2_000_000)
    assert needs is True
    assert "2,000,000" in msg


def test_price_comparison_under_threshold_500k() -> None:
    needs, msg = check_price_comparison_required(500_000)
    assert needs is False
    assert "无需比价" in msg


def test_price_deviation_high_above_threshold() -> None:
    result = calculate_price_deviation(120_000, 100_000)
    assert result is not None
    assert result["deviation_pct"] == 20.0
    assert result["is_high"] is True


def test_price_deviation_low_under_threshold() -> None:
    result = calculate_price_deviation(105_000, 100_000)
    assert result is not None
    assert result["deviation_pct"] == 5.0
    assert result["is_high"] is False


def test_price_deviation_no_history_returns_none() -> None:
    assert calculate_price_deviation(100_000, None) is None
    assert calculate_price_deviation(100_000, 0) is None


def test_approval_chain_all_three_ok() -> None:
    approvals = [
        {"role": "department_manager", "approved": True},
        {"role": "finance_director", "approved": True},
        {"role": "ceo", "approved": True},
    ]
    ok, missing = check_approval_chain(approvals)
    assert ok is True
    assert missing == []


def test_approval_chain_missing_ceo() -> None:
    approvals = [
        {"role": "department_manager", "approved": True},
        {"role": "finance_director", "approved": True},
    ]
    ok, missing = check_approval_chain(approvals)
    assert ok is False
    assert "ceo" in missing


def test_approval_chain_unapproved_role_not_counted() -> None:
    """unapproved=True entries should not satisfy the role."""
    approvals = [
        {"role": "department_manager", "approved": False},
        {"role": "finance_director", "approved": True},
        {"role": "ceo", "approved": True},
    ]
    ok, missing = check_approval_chain(approvals)
    assert ok is False
    assert "department_manager" in missing


def test_find_policy_matches_keyword_overlap() -> None:
    text = "采购金额超过100万需要三家比价"
    matched = find_policy_matches(["100", "三家比价", "无关"], text)
    assert "100" in matched
    assert "三家比价" in matched
    assert "无关" not in matched


def test_find_policy_matches_empty_keywords() -> None:
    assert find_policy_matches([], "anything") == []


def test_apply_domain_rules_finds_threshold_and_chain() -> None:
    ctx = {
        "entities": [
            {
                "type": "purchase_request",
                "ref": "PR999",
                "attrs": {"amount": 1_500_000, "approvals": []},
            }
        ],
    }
    findings = apply_domain_rules(ctx, "test question")
    rule_names = {f["rule"] for f in findings}
    assert "price_comparison_threshold" in rule_names
    assert "approval_chain" in rule_names
    # Threshold violated (1.5M ≥ 1M)
    threshold = next(f for f in findings if f["rule"] == "price_comparison_threshold")
    assert threshold["status"] == "violated"
    # Approval chain violated (empty)
    chain = next(f for f in findings if f["rule"] == "approval_chain")
    assert chain["status"] == "violated"
    assert "ceo" in chain["message"]


def test_apply_domain_rules_no_pr() -> None:
    """No PR entity → empty findings (graceful)."""
    ctx: dict = {"entities": []}
    findings = apply_domain_rules(ctx, "test")
    assert findings == []


def test_apply_domain_rules_under_threshold_ok() -> None:
    """< 1M PR → threshold ok, no chain violation if approved."""
    ctx = {
        "entities": [
            {
                "type": "purchase_request",
                "ref": "PR100",
                "attrs": {
                    "amount": 500_000,
                    "approvals": [
                        {"role": "department_manager", "approved": True},
                    ],
                },
            }
        ],
    }
    findings = apply_domain_rules(ctx, "test")
    threshold = next(f for f in findings if f["rule"] == "price_comparison_threshold")
    assert threshold["status"] == "ok"
    # Under 1M → approval_chain rule NOT applied (only applies for ≥1M)
    rule_names = {f["rule"] for f in findings}
    assert "approval_chain" not in rule_names
