"""Knowledge Management domain agent (cut-043).

Per ECE/CLAUDE.md 铁律 4: `src/domain_packs/knowledge/agent/` contains the
KM-specific rules + agent functions. Engine Core (`src/ece/`) does NOT import
this module (per ADR-004 + iron rule 4 domain pack isolation).

This module re-exports `v0_rules` for the cut-042 discovery / registry pattern.
The actual rule body lives in `v0_rules.py` to keep `build_decision.py`-equivalent
separation (mirrors `procurement/agent/v0_rules.py`).
"""
from .v0_rules import (
    DECISION_ID_PREFIX,
    DECISION_KEY,
    RULE_ID,
    build_decision,
    evaluate_rule_R_KM_ACCESS,
)

__all__ = [
    "DECISION_ID_PREFIX",
    "DECISION_KEY",
    "RULE_ID",
    "build_decision",
    "evaluate_rule_R_KM_ACCESS",
]
