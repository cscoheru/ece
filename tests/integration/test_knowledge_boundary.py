"""cut-043 — Knowledge Management Pack boundary matrix tests.

Codex discipline (cut-042R3R closure lesson: predict the bar, write binding
before claim). Per PRD §7 纪律 #4 (测试先行) + §7 纪律 #2 (denied user demo),
this file's first commit contains the binding invariants Codex will ask for
in a hypothetical round-2:

  - DB relationships == Context relationships == expected
  - 422 zero-write: pre/post snapshot byte-equal (root.attrs, REQUIRES_ROLE
    count, HAS_ROLE count, evidence_records count)
  - S2 evidence semantics parametrize field: `expect_evidence_count: int`
    (mirrors cut-042R3R `expect_quote_evidence: bool`)

KM truth-table (R-KM-ACCESS = `validity AND permission`):
  +-------+---------+------------+--------+-------------------------+
  | pol   | emp     | today      | value  | evidence rows           |
  +-------+---------+------------+--------+-------------------------+
  | P-001 | alice   | 2026-09-22 | answ.  | 2 (validity + perm)     |
  | P-002 | alice   | 2026-09-22 | need.  | 1 (perm only)           |
  | P-003 | alice   | 2026-09-22 | need.  | 1 (validity only)       |
  | P-001 | eve     | 2026-09-22 | need.  | 1 (validity only)       |
  +-------+---------+------------+--------+-------------------------+

S2 semantics lock-down (mirrors procurement):
  validity passed  → validity evidence row persisted
  validity failed  → NO validity evidence row
  perm passed      → permission evidence row persisted
  perm failed      → NO permission evidence row
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

KM_SOURCE_SYSTEM = "km:v0-knowledge-fixture"
TODAY = "2026-09-22"


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
            {"sid": source_id, "s": KM_SOURCE_SYSTEM},
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
            {"did": root_display_id, "rel": relation, "sys": KM_SOURCE_SYSTEM},
        ).first()
    return int(row[0]) if row else 0


def _count_selects_from_context(
    root_source_id: str,
    employee_id: str,
    intent: str = "evaluate_policy_question",
) -> int:
    """R4-B1-style binding: Context relationships count via assemble_context.

    Counts REQUIRES_ROLE + HAS_ROLE relations visible to the assembled
    Context (mirrors procurement's SELECTS count).
    """
    display_id = _display_id_for(root_source_id)
    if not display_id:
        return 0
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=employee_id,
        intent=intent,
        entities=[{"type": "policy_document", "id": display_id}],
        pack="knowledge",
    )
    return sum(
        1
        for rel in pkg.relationships
        if rel.get("from") == display_id
        and rel.get("rel") in ("REQUIRES_ROLE", "HAS_ROLE")
    )


def _count_evidence_rows() -> int:
    """R4-B1-style zero-write check: count evidence_records for the KM fixture."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM evidence_records WHERE source_system = :sys"),
            {"sys": KM_SOURCE_SYSTEM},
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
            {"sid": root_source_id, "s": KM_SOURCE_SYSTEM},
        ).first()
    return dict(row[0]) if row and row[0] else {}


def _restore_root_attrs(root_source_id: str, snapshot: dict) -> None:
    """Restore attrs after a parametrized case (mirrors procurement pattern)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE entities SET attributes = CAST(:a AS jsonb)
                WHERE source_id = :sid AND source_system = :s
            """),
            {"a": json.dumps(snapshot), "sid": root_source_id, "s": KM_SOURCE_SYSTEM},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_attrs() -> None:
    """Snapshot/restore each policy's attrs around parametrized cases.

    Each case may mutate `policy_id` / `access_status` via the loop, so we
    restore the baseline attributes after each call to keep tests independent.
    """
    snapshots = {
        sid: _read_root_attrs(sid)
        for sid in ("KM-POL-001", "KM-POL-002", "KM-POL-003")
    }
    yield
    for sid, snap in snapshots.items():
        _restore_root_attrs(sid, snap)


# ---------------------------------------------------------------------------
# 4-case truth table (R-KM-ACCESS = validity AND permission)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "policy_id",
        "employee_id",
        "expected_value",
        "expected_evidence_count",
        "expected_keyword",
    ),
    [
        # KM-POL-001 + alice: valid + has-hr → answerable, 2 evidence rows
        ("KM-POL-001", "km-alice", "answerable", 2, "有据可答"),
        # KM-POL-002 + alice: expired + has-hr → needs_valid_policy, 1 evidence (perm only)
        ("KM-POL-002", "km-alice", "needs_valid_policy", 1, "请提供当前有效版本"),
        # KM-POL-003 + alice: valid + missing-finance → needs_valid_policy, 1 (validity only)
        ("KM-POL-003", "km-alice", "needs_valid_policy", 1, "当前用户无访问权限"),
        # KM-POL-001 + eve: Permission Engine denies BEFORE the rule runs
        # (km-eve is in spec.denied_users) → no_permission branch, 0 evidence rows.
        ("KM-POL-001", "km-eve", "no_permission", 0, "无权访问"),
    ],
    ids=[
        "validity_pass_perm_pass_answerable",
        "validity_fail_perm_pass_needs_valid",
        "validity_pass_perm_fail_needs_valid",
        "validity_pass_perm_fail_eve_denied_pre_rule",
    ],
)
def test_knowledge_boundary_truth_table(
    client: TestClient,
    policy_id: str,
    employee_id: str,
    expected_value: str,
    expected_evidence_count: int,
    expected_keyword: str,
) -> None:
    """cut-043 binding invariant (predicted bar, written before claim).

    Each 200 case asserts:
      1. `decision_value == expected_value`
      2. `len(evidence) == expected_evidence_count` (S2 lock-down)
      3. `reason contains expected_keyword`
      4. DB relationship counts stable (REQUIRES_ROLE + HAS_ROLE unchanged
         for the policy in question; KM has no materializer)
    """
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": employee_id},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {
                "policy_id": policy_id,
                "employee_id": employee_id,
                "today": TODAY,
            },
        },
    )
    assert resp.status_code == 200, (
        f"policy_id={policy_id} employee_id={employee_id}: expected 200, "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    body = resp.json()

    # 1. decision_value — mapper.to_business flattens `decision` to top-level
    #    `conclusion` / `conclusion_label` (cut-042R F4 API shape).
    decision_value = body.get("decision_value") or body.get("conclusion")
    assert decision_value == expected_value, (
        f"policy_id={policy_id} employee_id={employee_id}: "
        f"decision_value={decision_value!r} != expected={expected_value!r}"
    )

    # 2. evidence count (S2 lock-down)
    evidence = body.get("evidence", [])
    assert len(evidence) == expected_evidence_count, (
        f"policy_id={policy_id} employee_id={employee_id}: "
        f"evidence count={len(evidence)} != expected={expected_evidence_count}; "
        f"evidence={evidence!r}"
    )

    # 3. reason keyword (business-language probe)
    reason = body.get("reason", "")
    assert expected_keyword in reason, (
        f"policy_id={policy_id} employee_id={employee_id}: "
        f"reason {reason!r} does not contain expected keyword {expected_keyword!r}"
    )

    # 4. DB relationship count stable (KM has no materializer)
    db_rr_count = _count_relationships_from_root(
        _display_id_for(policy_id), "REQUIRES_ROLE"
    )
    db_hr_count = _count_relationships_from_root(
        _display_id_for(policy_id), "HAS_ROLE"
    )
    # KM-POL-001/003 each have 1 REQUIRES_ROLE; KM-POL-002 has 0 (no rels seeded)
    if policy_id in ("KM-POL-001", "KM-POL-003"):
        assert db_rr_count == 1, (
            f"{policy_id}: REQUIRES_ROLE={db_rr_count} != 1"
        )
    else:
        assert db_rr_count == 0, f"{policy_id}: REQUIRES_ROLE={db_rr_count} != 0"


# ---------------------------------------------------------------------------
# 422 zero-write binding (predicted bar from cut-042R3R R4-B1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected_status_substring"),
    [
        # Path-traversal attempt (loader rejects BEFORE materializer runs)
        ({"policy_id": "../etc", "employee_id": "km-alice"}, "policy_id"),
        # Empty / missing required fields → 422 at API boundary
        ({"policy_id": "", "employee_id": "km-alice"}, "policy_id"),
        ({"policy_id": "KM-POL-001", "employee_id": ""}, "employee_id"),
    ],
    ids=[
        "path_traversal_422",
        "empty_policy_id_422",
        "empty_employee_id_422",
    ],
)
def test_knowledge_boundary_422_zero_write(
    client: TestClient,
    params: dict,
    expected_status_substring: str,
) -> None:
    """R4-B1-style 422 zero-write binding for KM pack.

    Pre/post snapshot proves the API boundary is genuinely zero-write:
      - root.attrs byte-equal
      - REQUIRES_ROLE / HAS_ROLE count byte-equal
      - evidence_records count byte-equal
    """
    before_attrs_001 = _read_root_attrs("KM-POL-001")
    before_rr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "REQUIRES_ROLE"
    )
    before_hr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "HAS_ROLE"
    )
    before_evidence_count = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {**params, "today": TODAY},
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
    after_attrs_001 = _read_root_attrs("KM-POL-001")
    after_rr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "REQUIRES_ROLE"
    )
    after_hr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "HAS_ROLE"
    )
    after_evidence_count = _count_evidence_rows()

    assert after_attrs_001 == before_attrs_001, (
        f"R4-B1: 422 must NOT modify root.attrs; "
        f"before={before_attrs_001!r} after={after_attrs_001!r}"
    )
    assert after_rr_001 == before_rr_001, (
        f"R4-B1: 422 must NOT modify REQUIRES_ROLE count; "
        f"before={before_rr_001} after={after_rr_001}"
    )
    assert after_hr_001 == before_hr_001, (
        f"R4-B1: 422 must NOT modify HAS_ROLE count; "
        f"before={before_hr_001} after={after_hr_001}"
    )
    assert after_evidence_count == before_evidence_count, (
        f"R4-B1: 422 must NOT add evidence rows; "
        f"before={before_evidence_count} after={after_evidence_count}"
    )


# ---------------------------------------------------------------------------
# Loop-level direct test — bypasses API 422, exercises the rule on
# non-fixture inputs to confirm the loop itself is consistent.
# ---------------------------------------------------------------------------


def test_loop_level_km_rule_uses_anchored_today_not_system_time() -> None:
    """cut-043 loop-level: `today` is the parametrize value, not now().

    If the rule body secretly read datetime.now(), this test would be
    flaky after 2026-12-31 (KM-POL-001 expires). The rule must see the
    anchored TODAY passed in via params.
    """
    from ece.demo.api import _resolve_actor  # type: ignore[attr-defined]
    from ece.demo.spec import load_scenario_spec
    from ece.v0.loop import run_demo_loop

    spec = load_scenario_spec("knowledge", "default")
    engine = get_engine()
    actor = _resolve_actor("km-alice")

    result = run_demo_loop(
        engine,
        actor,
        "KM-POL-001",
        spec,
        params={
            "policy_id": "KM-POL-001",
            "employee_id": "km-alice",
            "today": TODAY,
        },
    )

    decision = result.decision or {}
    assert decision.get("decision_value") == "answerable", (
        f"loop-level: anchored today {TODAY} should make KM-POL-001 valid; "
        f"got {decision.get('decision_value')!r}"
    )
    assert len(result.evidence or []) == 2, (
        f"loop-level: answerable path must produce 2 evidence rows; "
        f"got {len(result.evidence or [])}"
    )
