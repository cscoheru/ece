# Mutation Anchor M6 — R2-F2 materializer disabled

**Codex 第二轮阻断**: R2-F2 — quote_count 是规则入参, 但未真实重建 SELECTS 关系.

**变异方式**: 在 `src/ece/v0/loop.py` 的 step [3b] 处, 跳过 `materialize_fn` 调用:

```python
# 原始 (GREEN)
if descriptor.materialize_fn is not None and scenario_spec.relations_fields:
    for _field in scenario_spec.relations_fields:
        descriptor.materialize_fn(engine, root_source_id, effective_params)

# 变异 (RED)
# if descriptor.materialize_fn is not None and scenario_spec.relations_fields:
#     for _field in scenario_spec.relations_fields:
#         descriptor.materialize_fn(engine, root_source_id, effective_params)
```

或更细: 把 `descriptor.materialize_fn` 设为 `None`:

```python
# 变异 (RED)
descriptor.materialize_fn = None
```

**期望 RED 测试**: `tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop`

变异后:
- DB SELECTS 关系计数 = 1 (fixture 默认值, SPIKE-PR-001 -SELECTS-> SPIKE-SUP-A)
- 变异期望 `db_count == 2` (params.quote_count=2)
- assert 失败 → RED

**RED 链路**: `test_params_quote_count_lands_in_db_after_loop` 之所以"咬住"这个变异, 是因为:
1. 它是黑盒: 直接读 DB SELECTS 计数, 不依赖 in-memory rule observed_value
2. 它是三方一致 (DB / ctx / evidence): 即使 materializer 关闭让 in-memory 一致, DB 不一致也会被这条测试咬住

**应用**: cut-042R2 R2-F2 验收. 任何"修材料器但忘了调"或"调了但参数没传对"的回归, 这条变异都能抓住.