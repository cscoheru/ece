"""cut-042R2 R2-F2 — pack-owned deterministic relations materializer tests.

Codex 第二轮 R2-F2 阻断: quote_count 仍是规则入参, 未真实重建 SELECTS 关系.
必须由 ScenarioSpec 声明 `relations_fields`, 引擎调用 pack 注册的
`materialize_fn(engine, root_source_id, params)` 重建 SELECTS 关系.

变异锚点 #6 (M6): 在 v0/loop 跳过 materializer 调用 (或 materializer 实现为空)
时, 这些测试必须 RED.
"""
from __future__ import annotations

from sqlalchemy import text

from ece.db import get_engine


SPIKE_PR = "SPIKE-PR-001"
SPIKE_SOURCE_SYSTEM = "spike:v0-technical-fixture"


def _count_selects_relations(source_id: str, source_system: str) -> int:
    """Count SELECTS relationships scoped by source_system and source PR."""
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


def _fetch_fixture_supplier_ids() -> list[str]:
    """Return fixture supplier display_ids in deterministic order.

    Materializer reads this list to assign SELECTS targets. We use the
    SPIKE source_system supplier pool (SPIKE-SUP-A/B/C) — the same pool
    the V0 spike fixture seeds, so materializer rebuilds SELECTS within
    the fixture's own supplier set.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'supplier'
                  AND source_system = :sys
                ORDER BY display_id
            """),
            {"sys": SPIKE_SOURCE_SYSTEM},
        ).all()
    return [r[0] for r in rows]


def test_materializer_rebuilds_selects_count_to_param_value() -> None:
    """R2-F2 #a — materializer 应将 SELECTS 计数重设为 params["quote_count"].

    变异 (materializer 关闭) 时: DB SELECTS 保持上一值, 测试 RED.

    注: V0 spike fixture 只有 3 suppliers (SPIKE-SUP-A/B/C). 我们用 target=2
    既能验证重建, 又不超出 fixture pool (clamp 行为由 test_materializer_clamps_to_fixture_supplier_pool
    覆盖).
    """
    from ece.demo.registry import get_rule

    rule = get_rule("R-SPIKE-REVIEW")
    assert rule.materialize_fn is not None, (
        "R2-F2: R-SPIKE-REVIEW must register materialize_fn (pack-owned "
        "deterministic materializer)."
    )

    target_count = 2
    rule.materialize_fn(
        get_engine(),
        SPIKE_PR,
        {"quote_count": target_count},
    )

    actual = _count_selects_relations(SPIKE_PR, SPIKE_SOURCE_SYSTEM)
    assert actual == target_count, (
        f"R2-F2 #a: materializer must rebuild SELECTS to {target_count}; "
        f"got {actual}"
    )


def test_materializer_handles_zero_quotes() -> None:
    """R2-F2 — quote_count=0 → DB SELECTS = 0 (delete all)."""
    from ece.demo.registry import get_rule

    rule = get_rule("R-SPIKE-REVIEW")
    assert rule.materialize_fn is not None
    rule.materialize_fn(get_engine(), SPIKE_PR, {"quote_count": 0})
    assert _count_selects_relations(SPIKE_PR, SPIKE_SOURCE_SYSTEM) == 0


def test_materializer_clamps_to_fixture_supplier_pool() -> None:
    """R2-F2 — quote_count 超出 supplier pool 大小应被 clamp, 不报错.

    演示页传 quote_count=999 不应破坏 materializer. clamp 到 fixture supplier 数量
    并记录 (warning log or 静默).
    """
    from ece.demo.registry import get_rule

    rule = get_rule("R-SPIKE-REVIEW")
    assert rule.materialize_fn is not None

    suppliers = _fetch_fixture_supplier_ids()
    pool_size = len(suppliers)
    assert pool_size > 0, "fixture supplier pool must be non-empty"

    rule.materialize_fn(get_engine(), SPIKE_PR, {"quote_count": 999})

    actual = _count_selects_relations(SPIKE_PR, SPIKE_SOURCE_SYSTEM)
    assert actual <= pool_size, (
        f"R2-F2: materializer must clamp to supplier pool ({pool_size}); "
        f"got {actual}"
    )


def test_materializer_is_pack_owned_not_loop_hardcoded() -> None:
    """R2-F2 — materializer 在 registry 注册 (pack-owned), 不在 v0/loop 硬编码.

    验证 get_rule('R-SPIKE-REVIEW').materialize_fn 是 procurement pack 注册的,
    不是循环 import 也不是空函数. materializer 物理文件必须在 procurement pack
    而不是 v0/loop.
    """
    import inspect
    from ece.demo.registry import get_rule

    rule = get_rule("R-SPIKE-REVIEW")
    assert rule.materialize_fn is not None, "R2-F2: materializer must be registered"
    src = inspect.getsourcefile(rule.materialize_fn)
    assert src is not None and "domain_packs/procurement" in src, (
        f"R2-F2: materializer must live in procurement pack, not v0/loop; "
        f"got source file: {src!r}"
    )
    # cut-042R2 进一步: materializer 不能和 rule 在同一个文件 (S3 纯度契约).
    assert "v0_rules.py" not in src, (
        f"R2-F2: materializer must be in a SEPARATE module from the rule "
        f"(S3 purity criterion 5); got {src!r}"
    )


def test_materializer_does_not_touch_non_selects_relations() -> None:
    """R2-F2 — materializer 只重建 SELECTS, 不影响 BELONGS_TO / SUBMITTED_BY / etc.

    防止 materializer 越界删除其他关系.
    """
    from sqlalchemy import text as sa_text

    from ece.db import get_engine
    from ece.demo.registry import get_rule

    engine = get_engine()

    # baseline: count of non-SELECTS relations for SPIKE-PR-001
    with engine.connect() as conn:
        baseline_other = conn.execute(
            sa_text("""
                SELECT COUNT(*) FROM relationships
                WHERE relation != 'SELECTS'
                  AND source_system = :sys
                  AND src_entity_id = (
                    SELECT id FROM entities
                    WHERE source_id = :sid AND source_system = :sys
                  )
            """),
            {"sid": SPIKE_PR, "sys": SPIKE_SOURCE_SYSTEM},
        ).scalar()

    rule = get_rule("R-SPIKE-REVIEW")
    rule.materialize_fn(engine, SPIKE_PR, {"quote_count": 2})

    with engine.connect() as conn:
        after_other = conn.execute(
            sa_text("""
                SELECT COUNT(*) FROM relationships
                WHERE relation != 'SELECTS'
                  AND source_system = :sys
                  AND src_entity_id = (
                    SELECT id FROM entities
                    WHERE source_id = :sid AND source_system = :sys
                  )
            """),
            {"sid": SPIKE_PR, "sys": SPIKE_SOURCE_SYSTEM},
        ).scalar()

    assert after_other == baseline_other, (
        f"R2-F2: materializer must NOT touch non-SELECTS relations; "
        f"baseline={baseline_other} after={after_other}"
    )
