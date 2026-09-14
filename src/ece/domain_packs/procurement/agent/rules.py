"""S5.1 — Domain rules library (pure Python, no LLM).

Per TASKS.md S5.1:
- 比价触发 (100万阈值)
- 价格偏离带 (vs 历史价/市场参考价)
- 审批链完整性
- 政策匹配

Each rule returns structured findings (action, risk, evidence).
Per ECE/CLAUDE.md: rules findings 注入 prompt before LLM call (per
docs/API.md §6).
"""
from __future__ import annotations

from typing import Any

# Rule thresholds (per PRD §21 采购制度)
PRICE_COMPARISON_THRESHOLD = 1_000_000  # 100万 人民币
PRICE_DEVIATION_THRESHOLD_PCT = 10.0  # >10% 触发额外审批


def check_price_comparison_required(amount: int) -> tuple[bool, str]:
    """比价触发：金额 ≥ 100万 需要三家比价 (per PRD §21)."""
    if amount >= PRICE_COMPARISON_THRESHOLD:
        return (
            True,
            f"金额 {amount:,} ≥ {PRICE_COMPARISON_THRESHOLD:,}（100万阈值），需三家比价",
        )
    return (
        False,
        f"金额 {amount:,} < {PRICE_COMPARISON_THRESHOLD:,}，无需比价",
    )


def calculate_price_deviation(
    current_price: int,
    historical_avg: int | None,
    threshold_pct: float = PRICE_DEVIATION_THRESHOLD_PCT,
) -> dict[str, Any] | None:
    """价格偏离带：current vs historical_avg (per PRD §21).

    Returns None if no historical data; otherwise returns dict with
    deviation_pct and is_high flag (>threshold_pct).
    """
    if historical_avg is None or historical_avg <= 0:
        return None
    deviation_pct = (current_price - historical_avg) / historical_avg * 100
    return {
        "current_price": current_price,
        "historical_avg": historical_avg,
        "deviation_pct": round(deviation_pct, 2),
        "threshold_pct": threshold_pct,
        "is_high": deviation_pct > threshold_pct,
    }


def check_approval_chain(approvals: list[dict]) -> tuple[bool, list[str]]:
    """审批链完整性：100万以上需 部门经理 + 财务总监 + CEO 三级 (per PRD §21).

    approvals: list of {"role": str, "approved": bool} dicts.
    Returns (ok, missing_roles).
    """
    required = ["department_manager", "finance_director", "ceo"]
    approved = {a.get("role") for a in approvals if a.get("approved")}
    missing = [r for r in required if r not in approved]
    return (len(missing) == 0, missing)


def find_policy_matches(
    spec_keywords: list[str],
    policy_text: str,
) -> list[str]:
    """政策匹配：spec 中 keywords 与 policy_text 关键词重叠 (per PRD §21).

    Case-insensitive substring match.
    """
    if not spec_keywords:
        return []
    policy_lower = policy_text.lower()
    return [k for k in spec_keywords if k.lower() in policy_lower]


def apply_domain_rules(
    context_package: dict,
    question: str,
) -> list[dict[str, Any]]:
    """Apply all rules to the context package, return list of findings.

    Each finding: {rule, status, message}
    - status: "ok" | "violated"
    - rule: one of "price_comparison_threshold", "approval_chain", etc.
    """
    findings: list[dict[str, Any]] = []

    # Extract PR data from entities
    entities = context_package.get("entities", [])
    pr_entity = next(
        (e for e in entities if e.get("type") == "purchase_request"),
        None,
    )

    if pr_entity:
        attrs = pr_entity.get("attrs") or {}
        amount = int(attrs.get("amount") or 0)
        needs_comparison, msg = check_price_comparison_required(amount)
        findings.append({
            "rule": "price_comparison_threshold",
            "status": "violated" if needs_comparison else "ok",
            "message": msg,
        })

        # Approval chain only required for amount >= 100万 (per PRD §21);
        # skip rule entirely below threshold to avoid noise.
        if amount >= PRICE_COMPARISON_THRESHOLD:
            approvals = attrs.get("approvals", [])
            chain_ok, missing = check_approval_chain(approvals)
            if not chain_ok:
                findings.append({
                    "rule": "approval_chain",
                    "status": "violated",
                    "message": f"审批链不完整，缺失: {', '.join(missing)}",
                })
            else:
                findings.append({
                    "rule": "approval_chain",
                    "status": "ok",
                    "message": "审批链完整",
                })

    return findings
