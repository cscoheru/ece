"""Procurement domain agent (Sprint 5: TASKS.md S5.1-S5.2).

Per ECE/CLAUDE.md: domain_packs/procurement/agent/ contains the
Procurement-specific rules + Agent function. Engine Core (src/ece/)
does NOT import this (per ADR-004 + iron rule 4 domain pack isolation).
"""
from .agent import build_agent_prompt, procurement_agent
from .rules import (
    apply_domain_rules,
    calculate_price_deviation,
    check_approval_chain,
    check_price_comparison_required,
    find_policy_matches,
)

__all__ = [
    "apply_domain_rules",
    "build_agent_prompt",
    "calculate_price_deviation",
    "check_approval_chain",
    "check_price_comparison_required",
    "find_policy_matches",
    "procurement_agent",
]
