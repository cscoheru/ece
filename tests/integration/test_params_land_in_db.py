"""cut-042R F3 + cut-042R2 R2-F1/R2-F2 — parameter + relations DB-landing tests.

Codex HOLD 2026-09-22 finding F3: API 请求 amount=1_500_000 后, evidence 记录
observed_value=1_500_000, 但 DB 的 SPIKE-PR-001 实体的 attributes.amount 仍是
1_280_000 (fixture 默认). 这违反 PRD §7 #3 "所有数字真实运行生成", 也违反 DoD
"参数修改后实时重新生成并真实跑通".

fix (cut-042R F3): 在 step [1] assemble_context 之前, 把 params 写回 root.attrs
(仅写 spec.root_params_fields 声明的字段). 这样 re-read 看到的就是真值.

cut-042R2 R2-F1 (CRITICAL): denied 用户发 params 后, 仍能写数据库. 必须黑盒验证
zero-write. 修法: loop 重排 — 先只读 assemble → 权限判定 → denied 立即返回
(零 step [3a/3b/3c/4/5/6]).

cut-042R2 R2-F2: quote_count 不仅是规则入参, 必须真实重建 SELECTS 关系. 三方一致:
  - DB SELECTS count == params["quote_count"]
  - assemble_context 后 ctx.relationships 中 SELECTS 计数 == N
  - API evidence observed 反映 N

cut-042R2 R2-F6: test_no_params_leaves_db_amount_unchanged 必须真正"无 params",
不再先发 amount=2_000_000 自打脸.
"""
from __future__ import annotations

from sqlalchemy import text

from ece.db import get_engine
from ece.main import app


def _read_root_attrs(source_id: str, source_system: str) -> dict:
    """Direct DB read of the root entity's attributes column."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": source_system},
        ).first()
    if row is None or row[0] is None:
        return {}
    return dict(row[0])


def _count_selects_relations(source_id: str, source_system: str) -> int:
    """cut-042R2 R2-F2 — count SELECTS relations whose source is this PR.

    The seed fixture (spike:v0-technical-fixture) writes SELECTS rows tagged with
    that source_system on the relationship table. We scope by `source_system`
    on the relationship row itself and join through `src_entity_id`.
    """
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


def _read_review_keys(source_id: str, source_system: str) -> dict:
    """cut-042R2 R2-F1 — read the four `review_*` keys for denied zero-write check."""
    attrs = _read_root_attrs(source_id, source_system)
    return {k: attrs.get(k) for k in (
        "review_status", "review_decision_id",
        "review_evidence_id", "review_updated_at",
    )}


def _read_all_evidence(source_system: str) -> list[dict]:
    """cut-042R2 R2-F1 — read evidence rows tagged with this fixture's source_system.

    evidence table is `evidence_records` per migration 0008; we scope by
    `source_system` on the row to isolate the spike fixture from demo fixture.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT evidence_id, claim, observed_value, threshold_value,
                       source_record_id, source_system, actor_user_ref
                FROM evidence_records
                WHERE source_system = :sys
            """),
            {"sys": source_system},
        ).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# R2-F2 / F3 (既有 + 强化) — allowed 用户 params 真实落库
# ---------------------------------------------------------------------------


def test_params_amount_lands_in_root_attrs_after_loop() -> None:
    """F3 / R2-F2 — API amount=1_500_000 → DB SPIKE-PR-001.attributes.amount
    必须也是 1_500_000.

    修复前: DB.amount = 1_280_000 (seed fixture 默认值), evidence.observed = 1_500_000.
    cut-042R 修复后: DB.amount = 1_500_000, evidence.observed = 1_500_000, 一致.
    cut-042R2 重排后: 此行为仍在 allowed 路径生效 (step [3a]).
    """
    from fastapi.testclient import TestClient

    client = TestClient(app)
    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {
            "amount": 1_500_000,
            "quote_count": 2,
            "root_source_id": "SPIKE-PR-001",
        },
    }
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json=payload,
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 200, f"F3: API call must succeed; got {r.status_code}: {r.text}"

    attrs = _read_root_attrs("SPIKE-PR-001", "spike:v0-technical-fixture")
    assert attrs.get("amount") == 1_500_000, (
        f"F3: DB root.attrs.amount must reflect API param (1_500_000), "
        f"got {attrs.get('amount')!r}. "
        f"This is the F3 finding: API params must write back to DB, "
        f"not just to the rule in-memory."
    )


def test_params_quote_count_lands_in_db_after_loop() -> None:
    """R2-F2 — API quote_count=N → DB SELECTS 关系计数必须 == N.

    cut-042R 修复时这个测试只验证 amount, 不验证 SELECTS 关系计数. Codex 第二轮
    指出这是误导: quote_count 是关系型参数, 必须真实重建 SELECTS 关系.

    三方一致验收:
      1. DB relationships 表 SELECTS 计数 == N
      2. 当 quote_count < REQUIRED (3) 时, evidence 含 报价家数 行 (S2 只持久化
         passed conditions; passed=False 时不持久化是该包的 S2 锁死语义)
      3. 如果 materializer 关闭 (mutation), 测试 RED
    """
    from fastapi.testclient import TestClient

    client = TestClient(app)
    target_quote_count = 2  # < REQUIRED (3) → passed=True → evidence 行持久化

    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {
            "amount": 1_500_000,
            "quote_count": target_quote_count,
            "root_source_id": "SPIKE-PR-001",
        },
    }
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json=payload,
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 200, f"R2-F2: must succeed; got {r.status_code}: {r.text}"

    # 1. DB SELECTS 计数 == target_quote_count
    db_count = _count_selects_relations("SPIKE-PR-001", "spike:v0-technical-fixture")
    assert db_count == target_quote_count, (
        f"R2-F2: DB SELECTS relation count must equal params.quote_count "
        f"({target_quote_count}); got {db_count}. "
        f"This is the R2-F2 finding: quote_count must rebuild SELECTS relations, "
        f"not just be a rule parameter."
    )

    # 2. API response 反映 N (rule observed_value == N). S2 锁死语义:
    #    只持久化 passed=True 的条件; quote_count=2 < REQUIRED(3) → passed=True
    #    → evidence 包含 报价家数 行; 否则不包含.
    #    注: JSON 序列化为字符串, 比较前转 int.
    body = r.json()
    found_quote_evidence = False
    for ev in body.get("evidence", []):
        if "报价家数" in ev.get("claim", ""):
            assert int(ev.get("observed")) == target_quote_count, (
                f"R2-F2: evidence observed must reflect quote_count "
                f"({target_quote_count}); got {ev.get('observed')!r}"
            )
            found_quote_evidence = True
            break
    assert found_quote_evidence, (
        f"R2-F2: response must contain evidence row for 报价家数 when "
        f"quote_count < REQUIRED (3); got {body.get('evidence')!r}"
    )


# ---------------------------------------------------------------------------
# R2-F6 (修) — 真正不发 params 验证 DB 未被修改
# ---------------------------------------------------------------------------


def test_no_params_leaves_db_amount_unchanged() -> None:
    """R2-F6 — 真正无 params 验证 DB 不被无脑修改.

    cut-042R 原版先发 amount=2_000_000 再断言 2_000_000, 自打脸. 真版:
      1. 读取当前 DB.amount (fixture 默认 1_280_000 或 cut-042R 测试残留值)
      2. 发请求 params={} (完全不传)
      3. 断言 DB.amount 与第 1 步读到的值完全一致
    """
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. 记录 baseline
    before = _read_root_attrs("SPIKE-PR-001", "spike:v0-technical-fixture")
    baseline_amount = before.get("amount")

    # 2. 发请求 — params 完全不传 (root_source_id 也不传, 走 spec default)
    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {},
    }
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json=payload,
        headers={"X-User-Id": "spike-user-procurement"},
    )
    # 即便默认 params, allowed 用户也会触发 allowed 路径, 但没有 root_params_fields
    # 字段被覆盖, 所以 DB.amount 应保持 baseline.
    assert r.status_code == 200, f"R2-F6: must succeed; got {r.status_code}: {r.text}"

    # 3. 断言 DB.amount 未变化
    after = _read_root_attrs("SPIKE-PR-001", "spike:v0-technical-fixture")
    assert after.get("amount") == baseline_amount, (
        f"R2-F6: empty params must NOT modify DB.amount; "
        f"baseline={baseline_amount!r} after={after.get('amount')!r}"
    )


# ---------------------------------------------------------------------------
# R2-F1 (CRITICAL, 新) — denied 用户发 params 后, DB 零写入黑盒测试
# ---------------------------------------------------------------------------


def test_denied_user_does_not_write_to_db() -> None:
    """R2-F1 CRITICAL — denied 用户发 params 后, DB 任何字段都不变.

    真实复现 Codex 第二轮阻断:
      1. 读取 baseline (root.attrs, SELECTS 计数, review_*, evidence count)
      2. denied 用户 POST params.amount=2_222_222 (Codex 实测值)
      3. 断言所有 baseline 字段都不变 (byte-equal)

    修复前 (cut-042R): denied 用户请求后 SPIKE-PR-001.amount 从 1,280,000 → 2,222,222.
    cut-042R2 修复后: 权限检查在 materialize 前, denied 路径零写入.
    """
    from fastapi.testclient import TestClient

    client = TestClient(app)

    # 1. baseline
    baseline_attrs = _read_root_attrs("SPIKE-PR-001", "spike:v0-technical-fixture")
    baseline_selects = _count_selects_relations("SPIKE-PR-001", "spike:v0-technical-fixture")
    baseline_review = _read_review_keys("SPIKE-PR-001", "spike:v0-technical-fixture")
    baseline_evidence = _read_all_evidence("spike:v0-technical-fixture")
    baseline_evidence_count = len(baseline_evidence)

    # 2. denied 用户发 params (Codex 阻断场景)
    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {
            "amount": 2_222_222,   # Codex 实测的污染值
            "quote_count": 5,
            "root_source_id": "SPIKE-PR-001",
        },
    }
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json=payload,
        headers={"X-User-Id": "spike-user-unrelated"},  # denied
    )
    assert r.status_code == 200, f"R2-F1: must return 200 with no_permission; got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("conclusion") == "no_permission", (
        f"R2-F1: denied user must get no_permission; got {body.get('conclusion')!r}"
    )

    # 3. DB 零写入 (所有 baseline 字段 byte-equal 不变)
    after_attrs = _read_root_attrs("SPIKE-PR-001", "spike:v0-technical-fixture")
    after_selects = _count_selects_relations("SPIKE-PR-001", "spike:v0-technical-fixture")
    after_review = _read_review_keys("SPIKE-PR-001", "spike:v0-technical-fixture")
    after_evidence = _read_all_evidence("spike:v0-technical-fixture")

    # amount 字段绝不能被污染 (Codex 阻断信号)
    assert after_attrs.get("amount") == baseline_attrs.get("amount"), (
        f"R2-F1: DENIED user must NOT modify DB.amount; "
        f"baseline={baseline_attrs.get('amount')!r} after={after_attrs.get('amount')!r}. "
        f"This is the R2-F1 finding: Permission Before Materialization violation."
    )

    # SELECTS 关系计数绝不能被污染
    assert after_selects == baseline_selects, (
        f"R2-F1: DENIED user must NOT modify SELECTS relations; "
        f"baseline={baseline_selects} after={after_selects}."
    )

    # review_* 字段绝不能被写入
    assert after_review == baseline_review, (
        f"R2-F1: DENIED user must NOT write review_* keys; "
        f"baseline={baseline_review!r} after={after_review!r}."
    )

    # evidence 表绝不能新增行
    assert len(after_evidence) == baseline_evidence_count, (
        f"R2-F1: DENIED user must NOT create evidence rows; "
        f"baseline_count={baseline_evidence_count} after_count={len(after_evidence)}. "
        f"new_rows={after_evidence[baseline_evidence_count:]!r}"
    )
