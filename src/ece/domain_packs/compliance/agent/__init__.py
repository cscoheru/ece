"""Compliance domain agent (cut-044).

Per ECE/CLAUDE.md 铁律 4: `src/domain_packs/compliance/agent/` contains the
compliance-specific rules + agent functions. Engine Core (`src/ece/`) does NOT
import this module (per ADR-004 + iron rule 4 domain pack isolation).

This module re-exports `v0_rules` for the cut-042 discovery / registry pattern.
The actual rule body lives in `v0_rules.py` to keep `build_decision.py`-equivalent
separation (mirrors `knowledge/agent/__init__.py`).
"""
from .v0_rules import (
    DECISION_ID_PREFIX,
    DECISION_KEY,
    RULE_ID,
    build_decision,
    evaluate_rule_R_COMP_AUDIT,
)

__all__ = [
    "DECISION_ID_PREFIX",
    "DECISION_KEY",
    "RULE_ID",
    "build_decision",
    "evaluate_rule_R_COMP_AUDIT",
]
