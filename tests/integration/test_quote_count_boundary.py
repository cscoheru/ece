"""cut-042R3 + cut-042R3R — quote_count boundary matrix tests.

Codex 第三轮 HOLD (2026-09-22) finding R3-B1:
  API 输入 ``quote_count=999`` 时 DB SELECTS = 3 (materializer 静默 clamp),
  但 reason 仍写"999 家报价"; 输入 ``quote_count=-1`` 时 DB SELECTS = 0,
  evidence observed = -1。DB / Context / evidence / reason 四方不一致。

Codex 第四轮 HOLD (2026-09-22) findings:
  - R4-B1: 第三轮测试只断言 DB SELECTS, 不断言 Context SELECTS; 422 分支
    没有零写入快照。本轮把这两个 invariant 写入绑定测试。
  - R4-B2: 第三轮报告错误声称 ``3/4/999`` 有 quote evidence (observed=3),
    按 S2 证据语义 quote 条件未 passed → evidence 应当 ABSENT。本轮
    显式断言 absent。

修法 (cut-042R3):
  - ``v0/loop.py`` step [3c-refresh] 改为无条件从 re-read 刷新
    ``effective_params["quote_count"]`` 和 ``effective_params["amount"]``。
  - ``demo/api.py`` ``generate_scenario`` 入参校验 ``quote_count >= 0`` 且
    必须是 int (非 bool), 否则 422。

绑定 invariant (cut-042R3R):
  - ``DB SELECTS == Context SELECTS == expected_db_selects`` — 每个 200
    case 直接调用 ``assemble_context`` 验证, 不是 reviewer 黑盒。
  - 422 case: pre/post snapshot 验证 ``root.attrs``、SELECTS count、
    ``evidence_records`` count 三者全部 byte-equal。

S2 evidence 语义 (锁死):
  quote 条件 ``quote_count < REQUIRED(3)`` —
    - passed=True (quote_count ∈ {0, 1, 2}): quote evidence 行持久化,
      observed == DB SELECTS
    - passed=False (quote_count ∈ {3, 4, 999}): quote evidence 行
      **ABSENT**, decision_value ≠ auto_approved, reason 使用
      materialize 后的 count (3)

边界矩阵覆盖 ``quote_count ∈ {-1, 0, 1, 2, 3, 4, 999}``:

  - ``-1`` → 422, 零写入 (root.attrs / SELECTS / evidence count 不变)
  - ``0, 1, 2`` → quote condition passed, quote evidence present, observed == DB
  - ``3, 4, 999`` → quote condition not passed, quote evidence ABSENT,
    reason uses materialized count (3)

Fixture: V0 spike fixture ``spike:v0-technical-fixture`` (3 个 SPIKE-SUP 供应商),
与 production demo fixture (50 个 SUP 供应商) 隔离。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

FIXTURE_SYSTEM = "spike:v0-technical-fixture"
PR_SOURCE_ID = "SPIKE-PR-001"
ALLOWED_USER = "spike-user-procurement"
POOL_SIZE = 3  # spike fixture ships SPIKE-SUP-A/B/C


# ---------------------------------------------------------------------------
# helpers — direct DB reads, no mock, no in-memory shortcuts
# ---------------------------------------------------------------------------


def _count_selects_relations(source_id: str, source_system: str) -> int:
    """Cut-042R3 R3-B1 black-box: DB SELECTS count for this PR."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*) FROM relationships
                WHERE relation = 'SELECTS'
                  AND source_system = :sys
                  AND src_entity_id = (
                    SELECT id FROM entities
                    WHERE source_id = :sid AND source_system = :sys
                  )
            """),
            {"sid": source_id, "sys": source_system},
        ).first()
    return int(row[0]) if row else 0


def _restore_pr_attrs(snapshot: dict) -> None:
    """Snapshot/restore SPIKE-PR-001.attributes between parametrized cases.

    Each parametrize case may mutate ``amount`` / ``review_*`` via the loop,
    so we restore the baseline attributes after each call to keep tests
    independent (matches the cut-042R pattern in test_params_land_in_db.py).
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE entities SET attributes = CAST(:a AS jsonb)
                WHERE source_id = :sid AND source_system = :sys
            """),
            {"a": _jsonify(snapshot), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        )


def _read_pr_attrs_baseline() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).first()
    return dict(row[0]) if row and row[0] else {}


def _jsonify(d: dict) -> str:
    import json
    return json.dumps(d)


# ---------------------------------------------------------------------------
# R4-B1 / R4-B2 helpers — Context SELECTS via assemble_context + evidence count
# ---------------------------------------------------------------------------


def _resolve_display_id(source_id: str, source_system: str) -> str:
    """Resolve (source_id, source_system) → entities.display_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": source_system},
        ).first()
    return str(row[0]) if row else ""


def _count_selects_from_context(
    source_id: str, source_system: str, user_ref: str
) -> int:
    """R4-B1 — Context SELECTS count via assemble_context (in-package).

    The boundary matrix must call assemble_context directly (not just read
    the DB) so that ``DB SELECTS == Context SELECTS`` becomes a binding test
    invariant, not a reviewer blackbox check.
    """
    display_id = _resolve_display_id(source_id, source_system)
    if not display_id:
        return 0
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=user_ref,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": display_id}],
        pack="procurement",
    )
    return sum(
        1 for rel in pkg.relationships
        if rel.get("rel") == "SELECTS" and rel.get("from") == display_id
    )


def _count_evidence_rows(source_system: str) -> int:
    """R4-B1 — count evidence_records rows for the spike fixture (zero-write check)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM evidence_records WHERE source_system = :sys"),
            {"sys": source_system},
        ).first()
    return int(row[0]) if row else 0


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_pr() -> None:
    """Snapshot/restore SPIKE-PR-001.attributes around each parametrized case.

    Without this, case (4) leaves review_status='auto_approved' and amount=…
    in DB, leaking into case (5).
    """
    baseline = _read_pr_attrs_baseline()
    yield
    _restore_pr_attrs(baseline)


# ---------------------------------------------------------------------------
# 7-case boundary matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "client_qc, expected_db_selects, expect_quote_evidence, expected_status",
    [
        (-1, None, False, 422),       # 422 path: negative has no semantic meaning
        (0,  0,    True,  200),       # quote_count=0 < REQUIRED(3) → quote condition passes → evidence row present
        (1,  1,    True,  200),       # quote_count=1 < REQUIRED(3) → quote evidence observed=1
        (2,  2,    True,  200),       # quote_count=2 < REQUIRED(3) → quote evidence observed=2 (main path)
        (3,  3,    False, 200),       # quote_count=3 == REQUIRED → quote condition does NOT pass → evidence ABSENT (S2)
        (4,  3,    False, 200),       # clamped to 3 → quote condition does NOT pass → evidence ABSENT (S2)
        (999, 3,   False, 200),       # clamped to 3 → quote condition does NOT pass → evidence ABSENT (S2)
    ],
    ids=[
        "negative_422",
        "zero",
        "one",
        "two_main_path",
        "three_pool_full_no_quote_evidence",
        "four_clamped_no_quote_evidence",
        "huge_clamped_no_quote_evidence",
    ],
)
def test_quote_count_boundary_matrix(
    client: TestClient,
    client_qc: int,
    expected_db_selects: int | None,
    expect_quote_evidence: bool,
    expected_status: int,
) -> None:
    """R4-B1 / R4-B2 — DB / Context / evidence / reason four-way consistency.

    Binding invariants per case (no longer reviewer-blackbox):

      1. ``DB SELECTS == Context SELECTS`` — direct SQL row count vs.
         ``assemble_context`` in-package count.
      2. If quote condition passes (quote_count < REQUIRED(3)): a quote
         evidence row (``claim`` starts with ``报价家数``) MUST be present
         in the response, with ``observed == DB SELECTS``.
      3. If quote condition does NOT pass (quote_count >= REQUIRED(3)):
         quote evidence row MUST be ABSENT (S2 evidence semantics: only
         passed conditions are persisted). Reason MUST contain the
         materialized count ``expected_db_selects``.
      4. For HTTP 422 (negative): zero writes — ``root.attrs``,
         ``SELECTS`` count, and ``evidence_records`` row count all
         byte-equal before vs after the request.
    """
    # ----------------------------------------------------------------------
    # 422 path: snapshot/restore + zero-write assertion.
    # ----------------------------------------------------------------------
    if expected_status == 422:
        before_attrs = _read_pr_attrs_baseline()
        before_selects = _count_selects_relations(PR_SOURCE_ID, FIXTURE_SYSTEM)
        before_evidence_count = _count_evidence_rows(FIXTURE_SYSTEM)

        resp = client.post(
            "/api/v1/demo/scenarios/generate",
            headers={"X-User-Id": ALLOWED_USER},
            json={
                "domain": "procurement",
                "scenario": "default",
                "params": {"amount": 1_500_000, "quote_count": client_qc},
            },
        )
        assert resp.status_code == 422, (
            f"client_qc={client_qc}: expected 422, got {resp.status_code}; "
            f"body={resp.text[:300]}"
        )
        detail = resp.json().get("detail", "")
        assert "quote_count" in detail, (
            f"client_qc={client_qc}: 422 detail must mention quote_count, got: {detail!r}"
        )

        # Zero-write: all three baseline snapshots must be byte-equal.
        after_attrs = _read_pr_attrs_baseline()
        after_selects = _count_selects_relations(PR_SOURCE_ID, FIXTURE_SYSTEM)
        after_evidence_count = _count_evidence_rows(FIXTURE_SYSTEM)
        assert after_attrs == before_attrs, (
            f"R4-B1: 422 must NOT modify root.attrs; "
            f"before={before_attrs!r} after={after_attrs!r}"
        )
        assert after_selects == before_selects, (
            f"R4-B1: 422 must NOT modify SELECTS count; "
            f"before={before_selects} after={after_selects}"
        )
        assert after_evidence_count == before_evidence_count, (
            f"R4-B1: 422 must NOT add evidence rows; "
            f"before={before_evidence_count} after={after_evidence_count}"
        )
        return

    # ----------------------------------------------------------------------
    # 200 path: four-way consistency, all binding.
    # ----------------------------------------------------------------------
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": ALLOWED_USER},
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {"amount": 1_500_000, "quote_count": client_qc},
        },
    )
    assert resp.status_code == 200, (
        f"client_qc={client_qc}: expected 200, got {resp.status_code}; "
        f"body={resp.text[:300]}"
    )
    body = resp.json()

    # 1. DB SELECTS count (direct SQL).
    db_count = _count_selects_relations(PR_SOURCE_ID, FIXTURE_SYSTEM)
    assert db_count == expected_db_selects, (
        f"client_qc={client_qc}: DB SELECTS={db_count} != expected={expected_db_selects}"
    )

    # 2. Context SELECTS count via assemble_context (in-package). This is
    #    the binding assertion Codex R4-B1 demanded: "DB == Context" must be
    #    provable by the test, not by reviewer-blackbox.
    ctx_count = _count_selects_from_context(PR_SOURCE_ID, FIXTURE_SYSTEM, ALLOWED_USER)
    assert ctx_count == expected_db_selects, (
        f"client_qc={client_qc}: Context SELECTS={ctx_count} != expected={expected_db_selects}"
    )

    # 3. Explicit invariant: DB SELECTS == Context SELECTS.
    assert db_count == ctx_count, (
        f"R4-B1: DB SELECTS ({db_count}) must equal Context SELECTS ({ctx_count}) "
        f"for client_qc={client_qc}"
    )

    # 4. Evidence presence/absence per S2 lock-down semantics.
    evidence = body.get("evidence", [])
    quote_rows = [
        ev for ev in evidence if ev.get("claim", "").startswith("报价家数")
    ]
    if expect_quote_evidence:
        assert len(quote_rows) >= 1, (
            f"client_qc={client_qc}: expected quote evidence row (condition passed), "
            f"got evidence={evidence!r}"
        )
        # JSONB round-trips ints as strings, cast back.
        observed = int(quote_rows[0].get("observed"))  # type: ignore[arg-type]
        assert observed == expected_db_selects, (
            f"client_qc={client_qc}: quote evidence observed={observed} "
            f"!= DB SELECTS={expected_db_selects}"
        )
    else:
        assert len(quote_rows) == 0, (
            f"client_qc={client_qc}: quote evidence MUST be ABSENT "
            f"(S2 semantics: condition did not pass); got {quote_rows!r}"
        )

    # 5. Reason must reflect the materialized count.
    reason = body.get("reason", "")
    assert str(expected_db_selects) in reason, (
        f"client_qc={client_qc}: reason {reason!r} does not contain "
        f"{expected_db_selects} (the materialized truth)"
    )


# ---------------------------------------------------------------------------
# Direct loop-level test (bypasses the API 422 guard, confirms loop itself
# is consistent for non-negative inputs that exceed the pool)
# ---------------------------------------------------------------------------


def test_loop_level_quote_count_clamp_propagates_through_to_decision() -> None:
    """R4-B1 / R4-B2 loop-level: pass quote_count=999 directly to run_demo_loop
    and assert the resulting decision's reason and evidence use the clamped
    value (3), not the client-provided 999. Also asserts that quote evidence
    is ABSENT (S2 semantics: condition did not pass).
    """
    from ece.demo.api import _resolve_actor  # type: ignore[attr-defined]
    from ece.demo.spec import load_scenario_spec
    from ece.v0.loop import run_demo_loop

    spec = load_scenario_spec("procurement", "default")
    engine = get_engine()
    actor = _resolve_actor(ALLOWED_USER)

    result = run_demo_loop(
        engine, actor, PR_SOURCE_ID, spec,
        params={"amount": 1_500_000, "quote_count": 999},
    )

    # DB SELECTS = pool = 3 (clamped).
    assert _count_selects_relations(PR_SOURCE_ID, FIXTURE_SYSTEM) == 3

    # Context SELECTS == DB SELECTS (binding invariant, R4-B1).
    ctx_count = _count_selects_from_context(PR_SOURCE_ID, FIXTURE_SYSTEM, ALLOWED_USER)
    assert ctx_count == 3, f"R4-B1: Context SELECTS={ctx_count} != DB SELECTS=3"

    # Decision reason must NOT contain "999".
    decision = result.decision or {}
    reason = decision.get("reason", "")
    assert "999" not in reason, (
        f"reason leaked client value 999; got: {reason!r}"
    )
    # Decision reason must reflect 3 (the materialized count).
    assert "3" in reason, (
        f"reason should reflect materialized 3, got: {reason!r}"
    )

    # R4-B2: quote evidence must be ABSENT (condition did not pass per S2).
    evidence = result.evidence or []
    quote_rows = [
        ev for ev in evidence
        if isinstance(ev, dict) and str(ev.get("claim", "")).startswith("报价家数")
    ]
    assert len(quote_rows) == 0, (
        f"R4-B2: quote evidence MUST be ABSENT for quote_count=999 (clamped, "
        f"condition did not pass); got {quote_rows!r}"
    )
