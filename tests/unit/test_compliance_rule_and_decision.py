"""cut-044 — Compliance rule pure-function unit tests (no DB, no API).

Mirrors `tests/unit/test_knowledge_rule_and_decision.py` (KM S3 criterion)
to lock the R-COMP-AUDIT contract at the unit level. The binding contract
for compliance rule's two gates — pure functions, fixed condition order,
six keys per condition, deterministic reason string.

R-COMP-AUDIT conditions:
  0. evidence_count_meets_threshold   — passes iff count(evidence_set in period) >= control.evidence_min
  1. system_coverage_complete         — passes iff control.required_systems ⊆ covered_systems

decision_value:
  both passed     → "evidence_package_sufficient"
  any failed      → "gap_list"  (allowlisted zero-evidence)
"""
from __future__ import annotations

import re
import uuid

import pytest

from ece.context.assembly import ContextPackage
from ece.domain_packs.compliance.agent.v0_rules import (
    DECISION_ID_PREFIX,
    DECISION_KEY,
    RULE_ID,
    build_decision,
    evaluate_rule_R_COMP_AUDIT,
)

EXPECTED_CON_KEYS = ("name", "expr", "actual", "threshold", "passed", "claim")
CON_NAMES = ("evidence_count_meets_threshold", "system_coverage_complete")


def _context() -> ContextPackage:
    """Minimal ContextPackage stub for `build_decision`.

    The rule body does NOT touch `ctx` itself; only `build_decision` reads
    `package_id` and `request_id`. A stub keeps the unit test purely about
    the rule.
    """
    return ContextPackage(
        package_id=f"ctx_{uuid.uuid4()}",
        request_id=str(uuid.uuid4()),
        task={"intent": "evaluate_audit_question"},
        user={"id": "comp-alice", "display_id": "comp-alice", "roles": ["compliance_auditor"]},
    )


# ---------------------------------------------------------------------------
# Criterion 4: rule always emits BOTH conditions, in fixed order, with 6 keys
# ---------------------------------------------------------------------------


def test_rule_emits_two_conditions_with_six_keys_each() -> None:
    conditions = evaluate_rule_R_COMP_AUDIT(
        control={
            "id": "COMP-CTL-001",
            "required_systems": ["erp-system", "hr-system", "finance-system"],
            "evidence_min": 3,
        },
        evidence_set=[
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        request_period_start="2026-07-01",
        request_period_end="2026-09-30",
        today="2026-09-22",
    )

    assert len(conditions) == 2, f"expected 2 conditions, got {len(conditions)}"
    assert tuple(c["name"] for c in conditions) == CON_NAMES, (
        f"condition order is fixed: {CON_NAMES}; got {[c['name'] for c in conditions]}"
    )
    for cond in conditions:
        assert set(cond.keys()) == set(EXPECTED_CON_KEYS), (
            f"condition must have exactly 6 keys {EXPECTED_CON_KEYS}; got {set(cond.keys())}"
        )


# ---------------------------------------------------------------------------
# Criterion 5: module purity — no sqlalchemy / Engine imports
# ---------------------------------------------------------------------------


def test_module_purity_no_sqlalchemy_no_engine() -> None:
    """S3 criterion 5 — rule module MUST NOT import DB-driver."""
    import ece.domain_packs.compliance.agent.v0_rules as mod

    with open(mod.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert "import sqlalchemy" not in src and "from sqlalchemy" not in src, (
        "rule module must be pure (no sqlalchemy import); see S3 criterion 5"
    )
    assert "Engine(" not in src, "rule module must not hold a DB handle"


# ---------------------------------------------------------------------------
# Determinism: N=10 calls produce byte-equal output
# ---------------------------------------------------------------------------


def test_rule_byte_equal_across_10_calls() -> None:
    """S3 determinism contract — the rule must be pure across N=10 calls."""
    control = {
        "id": "COMP-CTL-001",
        "required_systems": ["erp-system", "hr-system", "finance-system"],
        "evidence_min": 3,
    }
    evidence_set = [
        {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
    ]
    today = "2026-09-22"

    first = evaluate_rule_R_COMP_AUDIT(control, evidence_set, "2026-07-01", "2026-09-30", today)
    for _ in range(9):
        again = evaluate_rule_R_COMP_AUDIT(control, evidence_set, "2026-07-01", "2026-09-30", today)
        assert again == first, (
            "rule must be deterministic across calls; got non-equal output"
        )

    # decision_id is generated by build_decision; assert it's fresh each time
    # but contains the expected prefix.
    decision = build_decision(first, _context())
    assert decision["decision_id"].startswith(DECISION_ID_PREFIX), (
        f"decision_id must start with {DECISION_ID_PREFIX!r}; got {decision['decision_id']!r}"
    )


# ---------------------------------------------------------------------------
# Boundary matrix: truth-table completeness (8 cases — cut-044R1 R1-B1)
# ---------------------------------------------------------------------------
#
# cut-044R1 R1-B1: rule now filters evidence by **request audit-period
# intersection** with evidence period. `today` is still in signature
# (reserved for future staleness checks) but does NOT participate in
# filtering — see `evaluate_rule_R_COMP_AUDIT` docstring.
#
# Cases:
#   1. canonical_full_coverage              → sufficient, 3 evidence
#   2. ctl002_missing_finance                → gap_list, 2 evidence (both fail)
#   3. ctl003_missing_hr_and_finance        → gap_list, 2 evidence (count ok, coverage fail)
#   4. request_before_evidence              → gap_list, 0 evidence (no intersection)
#   5. request_after_evidence               → gap_list, 0 evidence (no intersection)
#   6. request_partial_intersection         → sufficient, 3 evidence (all 3 still overlap)
#   7. request_full_containment             → sufficient, 3 evidence (request ⊇ evidence)
#   8. today_after_request_period_end       → sufficient, 3 evidence (today reserved-only)


_BOUNDARY_MATRIX: list[tuple[str, list[str], int, str, str, str, list[dict], str, str]] = [
    # (control_id, required_systems, evidence_min,
    #  request_period_start, request_period_end, today,
    #  expected_value, evidence_set, expected_keyword)
    # 1. canonical — full coverage, canonical period overlaps evidence period fully
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-07-01", "2026-09-30",
        "2026-09-22",
        "evidence_package_sufficient",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "无缺口",
    ),
    # 2. CTL-002 missing finance → gap_list (count=2<3, coverage missing finance)
    (
        "COMP-CTL-002",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-07-01", "2026-09-30",
        "2026-09-22",
        "gap_list",
        [
            {"system": "erp-system", "control_id": "COMP-CTL-002", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",  "control_id": "COMP-CTL-002", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "存在缺口",
    ),
    # 3. CTL-003 missing hr and finance → gap_list (count ok=2, coverage missing hr+finance)
    (
        "COMP-CTL-003",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-07-01", "2026-09-30",
        "2026-09-22",
        "gap_list",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-003", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-003", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "存在缺口",
    ),
    # 4. Request period FULLY BEFORE evidence period → no intersection → 0 evidence
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-01-01", "2026-06-30",  # request fully before evidence 2026-07-01..2026-09-30
        "2026-09-22",
        "gap_list",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "存在缺口",
    ),
    # 5. Request period FULLY AFTER evidence period → no intersection → 0 evidence
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-10-01", "2026-12-31",  # request fully after evidence 2026-07-01..2026-09-30
        "2026-09-22",
        "gap_list",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "存在缺口",
    ),
    # 6. Request period PARTIAL INTERSECTION with evidence period
    #    request=2026-08-15..2026-09-15 overlaps evidence 2026-07-01..2026-09-30
    #    → all 3 evidence packages still overlap → sufficient
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-08-15", "2026-09-15",  # partial intersection
        "2026-09-22",
        "evidence_package_sufficient",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "无缺口",
    ),
    # 7. Request period FULL CONTAINMENT of evidence period
    #    request=2026-06-01..2026-12-31 ⊇ evidence 2026-07-01..2026-09-30 → sufficient
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-06-01", "2026-12-31",  # full containment
        "2026-09-22",
        "evidence_package_sufficient",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "无缺口",
    ),
    # 8. today AFTER request_period_end (today no longer used for filtering —
    #    reserved for future staleness checks). All evidence still in
    #    intersection → sufficient.
    (
        "COMP-CTL-001",
        ["erp-system", "hr-system", "finance-system"],
        3,
        "2026-07-01", "2026-08-31",  # request period ends before today
        "2026-09-22",  # today > request_period_end → still allowed
        "evidence_package_sufficient",
        [
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        "无缺口",
    ),
]


@pytest.mark.parametrize(
    (
        "control_id",
        "required_systems",
        "evidence_min",
        "request_period_start",
        "request_period_end",
        "today",
        "expected_value",
        "evidence_set",
        "expected_keyword",
    ),
    _BOUNDARY_MATRIX,
)
def test_rule_truth_table_decision_value(
    control_id: str,
    required_systems: list[str],
    evidence_min: int,
    request_period_start: str,
    request_period_end: str,
    today: str,
    expected_value: str,
    evidence_set: list[dict],
    expected_keyword: str,
) -> None:
    """Criterion 2: 8 cases covering rule's request-period intersection logic.

    cut-044R1 R1-B1: filter is by request-period ∩ evidence-period
    intersection (not by today coverage). `today` is reserved for future
    staleness checks but currently does NOT participate in filtering.
    """
    conditions = evaluate_rule_R_COMP_AUDIT(
        control={
            "id": control_id,
            "required_systems": required_systems,
            "evidence_min": evidence_min,
        },
        evidence_set=evidence_set,
        request_period_start=request_period_start,
        request_period_end=request_period_end,
        today=today,
    )
    decision = build_decision(conditions, _context())
    assert decision["decision_value"] == expected_value, (
        f"control_id={control_id} request=({request_period_start}..{request_period_end}) "
        f"today={today}: expected {expected_value}, got {decision['decision_value']!r}"
    )
    assert decision["rule_id"] == RULE_ID
    assert decision["decision_key"] == DECISION_KEY
    reason = decision["reason"]
    assert expected_keyword in reason, (
        f"control_id={control_id} request=({request_period_start}..{request_period_end}) "
        f"today={today}: reason {reason!r} does not contain {expected_keyword!r}"
    )


# ---------------------------------------------------------------------------
# Reason string is byte-equal across calls and free of time/UUID leakage
# ---------------------------------------------------------------------------


def test_reason_string_is_pure_and_free_of_time_uuid() -> None:
    conditions = evaluate_rule_R_COMP_AUDIT(
        control={
            "id": "COMP-CTL-001",
            "required_systems": ["erp-system", "hr-system", "finance-system"],
            "evidence_min": 3,
        },
        evidence_set=[
            {"system": "erp-system",    "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "hr-system",     "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
            {"system": "finance-system", "control_id": "COMP-CTL-001", "period_start": "2026-07-01", "period_end": "2026-09-30"},
        ],
        request_period_start="2026-07-01",
        request_period_end="2026-09-30",
        today="2026-09-22",
    )
    decision = build_decision(conditions, _context())
    reason = decision["reason"]

    # Pure: no datetime / uuid / timestamp substrings.
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", reason), (
        f"reason leaked datetime; got: {reason!r}"
    )
    assert "uuid" not in reason.lower(), f"reason leaked uuid word; got: {reason!r}"
