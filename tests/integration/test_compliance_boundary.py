"""cut-044 — Compliance Pack boundary matrix tests.

Aligned with cut-043R/KM contract patterns (mirror the per-pack boundary
truth-table):

  - 4-case truth table (control_id × user_id × expected decision_value):
      COMP-CTL-001 + comp-alice → evidence_package_sufficient, 2 evidence
        (3 evidence packages, all 3 systems covered, both conditions pass)
      COMP-CTL-002 + comp-alice → gap_list,                  0 evidence
        (2 evidence packages from erp only, count + coverage both fail,
         on zero_evidence_decisions allowlist)
      COMP-CTL-003 + comp-alice → gap_list,                  1 evidence
        (3 evidence packages: 1 erp + 2 hr, count passes but coverage
         incomplete — only count condition emits evidence)
      COMP-CTL-001 + comp-eve   → no_permission (denied pre-rule), 0 evidence

  - 4-case 422 zero-write (path traversal / empty control_id / slash
    separator / space in identifier), mirroring R4-B1 binding invariant.

  - All 200 cases assert: decision_value + evidence count + reason keyword +
    DB relationship count stable. All 422 cases assert: pre/post snapshots
    byte-equal (attrs / relationships / evidence_rows).

cut-044 design (inverted from initial draft): evidence_packages are inlined
into control.attrs.evidence_packages (NOT a separate entity + relation type).
This avoids needing a second outbound edge from control and keeps the rule
module pure (no relationship traversal in the rule layer). All three
controls declare `required_systems=[erp-system, hr-system, finance-system]`,
so each control's REQUIRES_SYSTEM count is exactly 3 (the gap is in
EVIDENCE, not in requirements).

User decision (cut-044 plan §1 row 1): decision_value ∈ English constants
`evidence_package_sufficient` / `gap_list`; demo mapper NOT touched (fall-through).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.db import get_engine
from ece.main import app

COMP_SOURCE_SYSTEM = "comp:v0-compliance-fixture"
SERVER_TODAY = "2026-09-22"  # inside every audit-period window in the fixture


# ---------------------------------------------------------------------------
# helpers — direct DB reads, no mock, no in-memory shortcuts
# ---------------------------------------------------------------------------


def _display_id_for(source_id: str) -> str:
    """Resolve (source_id, source_system) → entities.display_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": source_id, "s": COMP_SOURCE_SYSTEM},
        ).first()
    return str(row[0]) if row else ""


def _count_relationships_from_root(root_display_id: str, relation: str) -> int:
    """Direct SQL count of relationships from a given root display_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*) FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE s.display_id = :did AND r.relation = :rel
                  AND r.source_system = :sys
            """),
            {"did": root_display_id, "rel": relation, "sys": COMP_SOURCE_SYSTEM},
        ).first()
    return int(row[0]) if row else 0


def _count_evidence_rows() -> int:
    """R4-B1-style zero-write check: count evidence_records for the COMP fixture."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM evidence_records WHERE source_system = :sys"),
            {"sys": COMP_SOURCE_SYSTEM},
        ).first()
    return int(row[0]) if row else 0


def _read_root_attrs(root_source_id: str) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": root_source_id, "s": COMP_SOURCE_SYSTEM},
        ).first()
    return dict(row[0]) if row and row[0] else {}


def _restore_root_attrs(root_source_id: str, snapshot: dict) -> None:
    """Restore attrs after a parametrized case (mirrors procurement/KM pattern)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE entities SET attributes = CAST(:a AS jsonb)
                WHERE source_id = :sid AND source_system = :s
            """),
            {"a": json.dumps(snapshot), "sid": root_source_id, "s": COMP_SOURCE_SYSTEM},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_attrs() -> None:
    """Snapshot/restore each control's attrs around parametrized cases.

    Each case may mutate control attrs (e.g. required_systems) via seeder
    patterns, so we restore the baseline attributes after each call to keep
    tests independent.
    """
    snapshots = {
        sid: _read_root_attrs(sid)
        for sid in ("COMP-CTL-001", "COMP-CTL-002", "COMP-CTL-003")
    }
    yield
    for sid, snap in snapshots.items():
        _restore_root_attrs(sid, snap)


# ---------------------------------------------------------------------------
# 4-case truth table — cut-044 binding invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("control_id", "user_id", "expected_value", "expected_evidence_count",
     "expected_keyword", "request_period"),
    [
        # COMP-CTL-001 + comp-alice: 3 evidence packages covering all 3 systems
        # + request period overlaps evidence period → both conditions pass
        # → evidence_package_sufficient, 2 evidence rows.
        ("COMP-CTL-001", "comp-alice", "evidence_package_sufficient", 2, "无缺口",
         ("2026-07-01", "2026-09-30")),
        # COMP-CTL-002 + comp-alice: 2 evidence packages (both from erp only)
        # → count=2 < 3 fail, coverage={erp} ⊄ {erp,hr,finance} fail → both fail
        # → 0 evidence rows → gap_list (zero_evidence_decisions allowlist).
        ("COMP-CTL-002", "comp-alice", "gap_list", 0, "存在缺口",
         ("2026-07-01", "2026-09-30")),
        # COMP-CTL-003 + comp-alice: 3 evidence packages (1 erp + 2 hr),
        # coverage={erp,hr} ⊄ {erp,hr,finance} (missing finance)
        # → count passes, coverage fails → 1 evidence row (count only).
        ("COMP-CTL-003", "comp-alice", "gap_list", 1, "存在缺口",
         ("2026-07-01", "2026-09-30")),
        # COMP-CTL-001 + comp-eve: DENIED pre-rule (PRD §7 纪律 #2)
        ("COMP-CTL-001", "comp-eve", "no_permission", 0, "无权访问",
         ("2026-07-01", "2026-09-30")),
        # R1-B1 cut-044R1: request period FULLY BEFORE evidence period
        # → no intersection → 0 evidence → gap_list (allowlist)
        ("COMP-CTL-001", "comp-alice", "gap_list", 0, "存在缺口",
         ("2026-01-01", "2026-06-30")),
        # R1-B1 cut-044R1: request period FULLY AFTER evidence period
        # → no intersection → 0 evidence → gap_list (allowlist)
        ("COMP-CTL-001", "comp-alice", "gap_list", 0, "存在缺口",
         ("2026-10-01", "2026-12-31")),
        # R1-B1 cut-044R1: request period PARTIAL INTERSECTION with evidence
        # period → all 3 evidence still overlap → sufficient
        ("COMP-CTL-001", "comp-alice", "evidence_package_sufficient", 2, "无缺口",
         ("2026-08-15", "2026-09-15")),
    ],
    ids=[
        "ctl001_alice_full_coverage_sufficient",
        "ctl002_alice_count_and_coverage_fail_gap_list",
        "ctl003_alice_coverage_only_fails_gap_list",
        "ctl001_eve_denied_pre_rule_no_permission",
        "R1_B1_request_before_evidence_gap_list",
        "R1_B1_request_after_evidence_gap_list",
        "R1_B1_request_partial_intersection_sufficient",
    ],
)
def test_compliance_boundary_truth_table(
    client: TestClient,
    control_id: str,
    user_id: str,
    expected_value: str,
    expected_evidence_count: int,
    expected_keyword: str,
    request_period: tuple[str, str],
) -> None:
    """cut-044 binding invariant + cut-044R1 R1-B1 audit-period semantics.

    Each 200 case asserts:
      1. `decision_value == expected_value`
      2. `len(evidence) == expected_evidence_count`
      3. `reason contains expected_keyword`
      4. DB relationship counts stable (REQUIRES_SYSTEM unchanged for the control)

    R5-B1 conformance (compliance is NOT requires_server_today_anchor): today
    is caller-supplied via params (caller chooses the audit period); we
    pass SERVER_TODAY to land inside the audit windows in the fixture.

    R1-B1 conformance: filter uses request-period ∩ evidence-period
    intersection. Cases 5/6 prove 0-intersection → 0 evidence → gap_list;
    case 7 proves partial intersection still preserves sufficient.
    """
    period_start, period_end = request_period
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": user_id},
        json={
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": control_id,
                "period_start": period_start,
                "period_end": period_end,
                "today": SERVER_TODAY,
            },
        },
    )
    assert resp.status_code == 200, (
        f"control_id={control_id} user_id={user_id} period=({period_start}..{period_end}): "
        f"expected 200, got {resp.status_code}; body={resp.text[:300]}"
    )
    body = resp.json()

    # 1. decision_value — mapper.to_business flattens `decision` to top-level
    #    `conclusion` / `conclusion_label` (cut-042R F4 API shape). English
    #    constants fall through (decision §1 row 1: mapper not touched).
    decision_value = body.get("decision_value") or body.get("conclusion")
    assert decision_value == expected_value, (
        f"control_id={control_id} user_id={user_id} period=({period_start}..{period_end}): "
        f"decision_value={decision_value!r} != expected={expected_value!r}"
    )

    # 2. evidence count (cut-044 plan: gap_list on zero_evidence_decisions allowlist)
    evidence = body.get("evidence", [])
    assert len(evidence) == expected_evidence_count, (
        f"control_id={control_id} user_id={user_id} period=({period_start}..{period_end}): "
        f"evidence count={len(evidence)} != expected={expected_evidence_count}; "
        f"evidence={evidence!r}"
    )

    # 3. reason keyword (business-language probe, no technical terms)
    reason = body.get("reason", "")
    assert expected_keyword in reason, (
        f"control_id={control_id} user_id={user_id} period=({period_start}..{period_end}): "
        f"reason {reason!r} does not contain expected keyword {expected_keyword!r}"
    )

    # 4. DB relationship count stable (compliance has no materializer)
    db_rs_count = _count_relationships_from_root(
        _display_id_for(control_id), "REQUIRES_SYSTEM"
    )
    # All 3 controls declare required_systems=[erp-system, hr-system,
    # finance-system], so each control's REQUIRES_SYSTEM count is exactly 3.
    # The gap is in EVIDENCE, not in requirements — this proves compliance
    # has no materializer mutating relationship counts.
    assert db_rs_count == 3, (
        f"{control_id}: REQUIRES_SYSTEM={db_rs_count} != 3"
    )


# ---------------------------------------------------------------------------
# 422 zero-write binding (R4-B1-style pattern, mirrored from KM)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected_status_substring"),
    [
        # Path-traversal attempt (loader rejects BEFORE materializer runs)
        ({"control_id": "../etc"}, "control_id"),
        # Empty / missing required field → 422 at API boundary
        ({"control_id": ""}, "control_id"),
        # Slash separator → unsafe identifier (KM pattern, parallel)
        ({"control_id": "comp/ctl-001"}, "control_id"),
        # Space in identifier → fails _SAFE_IDENTIFIER regex
        ({"control_id": "COMP CTL 001"}, "control_id"),
        # R1-B1: empty period_start → 422 at API boundary
        ({"control_id": "COMP-CTL-001", "period_start": "", "period_end": "2026-09-30",
          "today": SERVER_TODAY}, "period_start"),
        # R1-B1: malformed period_start → 422 (canonical round-trip)
        ({"control_id": "COMP-CTL-001", "period_start": "banana",
          "period_end": "2026-09-30", "today": SERVER_TODAY}, "period_start"),
        # R1-B1: reversed period → 422
        ({"control_id": "COMP-CTL-001", "period_start": "2026-09-30",
          "period_end": "2026-07-01", "today": SERVER_TODAY}, "period_start"),
        # R1-B1: non-canonical ISO form (basic `20260922`) → 422
        ({"control_id": "COMP-CTL-001", "period_start": "20260922",
          "period_end": "2026-09-30", "today": SERVER_TODAY}, "period_start"),
    ],
    ids=[
        "path_traversal_422",
        "empty_control_id_422",
        "slash_separator_422",
        "space_in_identifier_422",
        "R1_B1_empty_period_start_422",
        "R1_B1_malformed_period_start_422",
        "R1_B1_reversed_period_422",
        "R1_B1_non_canonical_iso_period_422",
    ],
)
def test_compliance_boundary_422_zero_write(
    client: TestClient,
    params: dict,
    expected_status_substring: str,
) -> None:
    """R4-B1-style 422 zero-write binding for compliance pack.

    Pre/post snapshot proves the API boundary is genuinely zero-write:
      - root.attrs byte-equal
      - REQUIRES_SYSTEM count byte-equal
      - evidence_records count byte-equal

    R1-B1 cut-044R1: 4 audit-period 422 cases verify strict YYYY-MM-DD
    canonical round-trip + period_start <= period_end at the API boundary.
    """
    before_attrs_001 = _read_root_attrs("COMP-CTL-001")
    before_rs_001 = _count_relationships_from_root(
        _display_id_for("COMP-CTL-001"), "REQUIRES_SYSTEM"
    )
    before_evidence_count = _count_evidence_rows()

    # If user_id missing, default to comp-alice (the seed fixture allows her).
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "comp-alice"},
        json={
            "domain": "compliance",
            "scenario": "default",
            "params": params,
        },
    )
    assert resp.status_code == 422, (
        f"params={params}: expected 422, got {resp.status_code}; body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert expected_status_substring in detail, (
        f"params={params}: 422 detail must mention {expected_status_substring}, "
        f"got: {detail!r}"
    )

    # Zero-write binding (post snapshots must be byte-equal to pre)
    after_attrs_001 = _read_root_attrs("COMP-CTL-001")
    after_rs_001 = _count_relationships_from_root(
        _display_id_for("COMP-CTL-001"), "REQUIRES_SYSTEM"
    )
    after_evidence_count = _count_evidence_rows()

    assert after_attrs_001 == before_attrs_001, (
        f"R4-B1: 422 must NOT modify root.attrs; "
        f"before={before_attrs_001!r} after={after_attrs_001!r}"
    )
    assert after_rs_001 == before_rs_001, (
        f"R4-B1: 422 must NOT modify REQUIRES_SYSTEM count; "
        f"before={before_rs_001} after={after_rs_001}"
    )
    assert after_evidence_count == before_evidence_count, (
        f"R4-B1: 422 must NOT add evidence rows; "
        f"before={before_evidence_count} after={after_evidence_count}"
    )
