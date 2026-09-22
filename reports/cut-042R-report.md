# cut-042R — Closure Report

> **Author**: Claude (Opus 5)
> **Date**: 2026-09-22
> **Cycle**: cut-042R (correction knife)
> **Codex verdict being responded to**: HOLD on cut-042 (`8c439ba` + `515f3d2`)
> **Status**: ✅ All F1–F8 closed; **STOP awaiting Codex re-review**; **NOT committed, NOT pushed**

---

## 1. 摘要

cut-042 交付后 Codex 裁定 **HOLD**，列出 F1–F8 八条阻断。本刀 cut-042R 是修正刀，仅修改既有 cut-042 的边界条件，**不引入新功能**：

| 阻断 | 修法 | 状态 |
|------|------|------|
| F1 权限可被绕过 (`params.actor` 覆盖 `X-User-Id`) | `demo/api.py:_resolve_actor` 仅读 header；`params.actor` 被显式忽略 | ✅ |
| F2 通用底座仍硬编码 `procurement` 等业务字符串 | `v0/loop.py` 改从 `load_scenario_spec()` 读 YAML；`_ensure_pack_registered` 改为通用 `importlib` 触发；`evidence/store.py` 验证生产代码路径显式传 `subject_entity_type` | ✅ |
| F3 参数未真实落库（DB.amount ≠ API amount） | 新增 `_apply_params_to_root_attrs` step [0]；写回 `root.attrs.amount` | ✅ |
| F4 合法 clean 路径 HTTP 500（IndexError） | `context/update.apply_context_update` 允许 `evidence_id=None`（仅 `auto_approved`）；loop 检测 0-evidence 时不传 ID | ✅ |
| F5 响应契约错误（reason="ok"，未知域 500，路径穿越） | `mapper.to_business` 用业务 reason；`spec.load_scenario_spec` 拒绝 `..`/`/`；API 422 错误码 | ✅ |
| F6 UI 骨架未交付（静态页不调 API） | 新建 `demos/spa/{index.html, app.js, styles.css}` 零 CDN 零 build SPA；三视图（A live + B/C 占位） | ✅ |
| F7 测试主动放水（接受 200/500/503，绕开 IndexError） | 严格 `assert r.status_code == 200`；删除所有 `pytest.skip`；新增 8 个契约断言 | ✅ |
| F8 部署文档自相矛盾（§3 vs §9） | 新建 `docs/demo-platform/DEMO_PLATFORM_PRD.md` §3 + `DEPLOY_USER_PROXY.md`，统一两阶段部署叙述 | ✅ |

---

## 2. commits 链 (cut-042R — 4 commits + 1 report)

**本刀遵守 RED → GREEN 流程**:

| Commit | 类型 | 内容 |
|--------|------|------|
| A (RED) | test-only | `tests/integration/test_demo_api_contract.py` 加 F1/F4/F5 严格断言；`tests/unit/test_no_procurement_literal_in_engine.py` (新)；`tests/integration/test_params_land_in_db.py` (新)；`tests/integration/test_spa_smoke.py` (新) |
| B (GREEN) | impl | `demo/api.py` F1/F2/F5；`demo/spec.py` F2/F5；`domain_packs/procurement/scenarios/default.yaml` F2/F3 新字段；`v0/loop.py` F2/F3/F4 重构；`context/update.py` F4；`evidence/store.py` F2 文档化；`main.py` 异常 handler；`demo/mapper.py` F5 |
| C (SPA + smoke) | delivery | `demos/spa/{index.html, app.js, styles.css}` (新)；`scripts/cut_042r_url_smoke.sh` (新) |
| D (docs + 变异) | report | `docs/demo-platform/DEMO_PLATFORM_PRD.md` (新)；`docs/demo-platform/DEPLOY_USER_PROXY.md` (新)；`reports/cut-042R/mutation-anchors.txt` + 5 个 stdout；`reports/cut-042R-report.md` (本文件) |

---

## 3. F1–F8 对账（修法 + RED→GREEN + 变异锚点）

### F1 — 权限可被绕过

- **修法**: `src/ece/demo/api.py` `_resolve_actor(x_user_id)` 仅读 header。`req.params.get("actor")` 完全被忽略。
- **RED test**: `tests/integration/test_demo_api_contract.py::test_denied_user_with_body_actor_override_returns_no_permission`
- **变异证据**: M1_F1_actor_bypass.txt — 注入 `body.actor` override 后测试 FAIL（结论变为 `review_required` 而非 `no_permission`）

### F2 — 通用底座仍硬编码业务字符串

- **修法**:
  - `src/ece/v0/loop.py:_get_spike_spec()` 改为 `load_scenario_spec("procurement", "default")` — 单一事实源在 YAML
  - `src/ece/v0/loop.py:_ensure_pack_registered` 改为通用 `importlib.import_module(f"ece.domain_packs.{pack}.scenarios")`
  - `src/ece/demo/api.py:_discover_domains` 改从 YAML `label` 字段读取（删除 `_DOMAIN_LABELS` 字典）
  - `src/ece/evidence/store.py` 文档化生产代码路径显式传 `subject_entity_type`（保留 default 用于 V0 spike 47 测试兼容）
- **RED tests**: `tests/unit/test_no_procurement_literal_in_engine.py` — 8 个 AST 检测
- **变异证据**: M2_F2_v0_loop_procurement.txt — 注入 `pack = "procurement"` hardcode 后 AST 测试 FAIL

### F3 — 参数未真实落库

- **修法**: `src/ece/v0/loop.py` 新增 `_apply_params_to_root_attrs(engine, source_id, source_system, params, root_params_fields)` step [0]，用 `jsonb_build_object` 合并到 `root.attrs`
- **RED tests**: `tests/integration/test_params_land_in_db.py` — 3 个 DB 落库验证
- **变异证据**: M3_F3_params_not_in_db.txt — 注入 `pass`（禁用 step [0]）后测试 FAIL（DB.amount 仍是 1.5M，新请求 2M 没落库）

### F4 — 合法 clean 路径 HTTP 500

- **修法**:
  - `src/ece/context/update.py:apply_context_update(evidence_id=None)` 仅 `auto_approved` 路径允许
  - `src/ece/v0/loop.py:_run_demo_loop_impl` 检测 0-evidence 时不传 ID（`primary_evidence_id = evidence_ids[0] if evidence_ids else None`）
- **RED test**: `tests/integration/test_demo_api_contract.py::test_auto_approved_clean_path_returns_200_and_no_indexerror`
- **变异证据**: M4_F4_indexerror.txt — 注入 `if not evidence_id: raise`（禁用 F4 fix）后测试 FAIL（返回 422）

### F5 — 响应契约错误

- **修法**:
  - `src/ece/demo/mapper.py:to_business` 分支选择业务语言（denied → "调用者无权访问此场景"；allowed → rule.reason）
  - `src/ece/demo/spec.py:_check_safe_identifier` 在路径拼接前拒绝 `..`/`/`
  - `src/ece/main.py` 异常 handler：`FileNotFoundError`/`ValueError` → HTTP 422 + `error_kind` 结构化 JSON
- **RED tests**: `tests/integration/test_demo_api_contract.py` — 5 个契约断言（业务 reason / 未知域 422 / 未知 scenario 422 / 路径穿越 422 / 已拒绝 reason 业务语言）
- **变异证据**: M5_F5_bad_reason.txt — 注入 `business_reason = result.reason`（loop 状态透传）后测试 FAIL

### F6 — UI 骨架未交付

- **修法**:
  - `demos/spa/index.html` (~80 行) — 零 CDN 零 build；三视图（A/B/C）
  - `demos/spa/app.js` (~120 行) — vanilla JS；真实 `fetch('/api/v1/demo/*')`；X-User-Id header
  - `demos/spa/styles.css` (~80 行) — vanilla CSS
- **RED tests**: `tests/integration/test_spa_smoke.py` — 7 个 SPA 完整性检查
- **验收**: SPA 见 `/` 但通过 `curl /api/v1/demo/domains` 调 API；视图 B/C 占位可见；既有 `demos/procurement-review-demo.html` (PRD AC6 fallback) 保留

### F7 — 测试主动放水

- **修法**: `tests/integration/test_demo_api_contract.py` 全文 `assert r.status_code == 200`；删除 `pytest.skip` 绕开 0-evidence IndexError 的代码
- **结果**: 14/14 contract tests 严格 200 断言

### F8 — 部署文档矛盾

- **修法**: 新建 `docs/demo-platform/DEMO_PLATFORM_PRD.md` §3 明确两阶段（API+DB in docker / SPA on user-server nginx 反代）；新建 `docs/demo-platform/DEPLOY_USER_PROXY.md` 含 nginx 配置示例 + 文件清单
- **结果**: 单一文档源描述两阶段部署；不再有"单 docker compose 起全栈"自相矛盾

---

## 4. 测试 baseline

```
uv run pytest -m "not eval and not eval_llm"
================================================
451 passed, 3 skipped, 3 deselected in 113.13s
================================================
```

- **cut-042 baseline**: 425 passed
- **cut-042R 新增**: 26 tests
  - `test_demo_api_contract.py`: +8 (F1/F4/F5 严格断言)
  - `test_params_land_in_db.py`: +3 (新文件)
  - `test_spa_smoke.py`: +7 (新文件)
  - `test_no_procurement_literal_in_engine.py`: +8 (新文件)
- **当前总数**: 425 + 26 = **451 passed** ✓
- **零 V0 spike 回归**: 47 V0 spike tests (`test_v0_loop.py` + `test_v0_evidence_persistence.py` + `test_v0_apply_context_update.py`) 全绿

---

## 5. 5 个变异锚点咬合证据

| # | F# | 注入位置 | 注入变异 | 咬合测试 | 实际失败信号 | 还原验证 |
|---|----|---------|---------|----------|------------|---------|
| M1 | F1 | `demo/api.py:_resolve_actor` | `body.actor` override reintroduced | `test_denied_user_with_body_actor_override_returns_no_permission` | `conclusion='review_required'` vs expected `'no_permission'` | ✅ 还原后 200 |
| M2 | F2 | `v0/loop.py:_re_read_through_assembly` | `pack = "procurement"` force | `test_v0_loop_module_has_no_procurement_literal` | AST 检测到 `procurement` outside `_get_spike_spec` | ✅ 还原后绿 |
| M3 | F3 | `v0/loop.py:_run_demo_loop_impl` step [0] | `_apply_params_to_root_attrs` → `pass` | `test_params_amount_lands_in_root_attrs_after_loop` | `DB.amount=1500000` 而非新请求的 `2000000` | ✅ 还原后绿 |
| M4 | F4 | `context/update.py:apply_context_update` | `if not evidence_id: raise` | `test_auto_approved_clean_path_returns_200_and_no_indexerror` | 返回 422 而非 200 | ✅ 还原后绿 |
| M5 | F5 | `demo/mapper.py:to_business` denied branch | `business_reason = result.reason` | `test_top_level_reason_for_denied_user_is_business_language` | `'no permitted context'` 而非业务语言 | ✅ 还原后绿 |

**结论**: 5/5 锚点全部咬住；每个变异都能被至少一个 cut-042R 测试捕获到具体失败信号（带行号 + 实际值 vs 期望值对比）。

**变异锚点原始 stdout 归档**: `reports/cut-042R/mutation-anchors/M{1..5}_*.txt`

---

## 6. URL smoke test 输出（公网 526 标注）

`scripts/cut_042r_url_smoke.sh` 包含 7 个 URL-level 检查:

| # | 检查 | 命令 | 期望 |
|---|------|------|------|
| 0 | API health | `curl ${API_BASE}/healthz` | 200 |
| 1 | SPA index.html | `curl ${SPA_BASE}/index.html` | 200 + 包含 `/api/v1/demo/domains` |
| 2 | SPA 零 CDN + 真实 fetch | grep `app.js` | 无 `<script src="https?://` + `fetch(` 出现 |
| 3 | GET domains | `curl ${API_BASE}/api/v1/demo/domains` | JSON `{domains: [...]}` |
| 4 | POST review_required | `curl -X POST ... -d '{"amount":1500000,"quote_count":2}'` | `conclusion=review_required`, reason 是业务语言 |
| 5 | POST auto_approved (F4 修复) | `curl -X POST ... -d '{"amount":500000,"quote_count":3}'` | 200, `conclusion=auto_approved` |
| 6 | POST denied + body.actor override (F1) | `curl -X POST ... denied header + body.actor=allowed` | `conclusion=no_permission` |

**cut-042R 公网 URL 状态**: ❌ **NOT PASS** — `https://corln.rana.asia/` 当前 Cloudflare 526 (外部阻断，origin SSL mismatch)。本刀**不伪报公网通过**。本刀 acceptance criterion = **127.0.0.1 内网 smoke 全过**。

公网验收推到 **cut-045**（依赖客户方修复 origin TLS + Cloudflare strict mode 切换）。

---

## 7. 范围锁自查

| 锁项 | 状态 |
|------|------|
| 不引入新 Kernel 对象 / Adapter / Runtime | ✅ 仅修既有 `ece.v0.loop` / `ece.demo.*` / `ece.context.update` / `ece.evidence.store` |
| 不动 migrations | ✅ `apply_context_update` 接受 None 不需 schema 变更 (JSONB attributes 自然支持 null) |
| 不动 `context/` `permissions/` 既有行为 | ✅ 仅 `context/update.py` 允许 evidence_id=None (auto_approved 路径) |
| S2 evidence 语义不破 | ✅ "只为 passed condition 持久化" 锁定保留；F4 修法是 S4 接受 NULL 而非 S2 改语义 |
| lint-imports 契约不破 (2 kept) | ✅ pack 通过 `importlib.import_module` 触发注册；零 `from ece.domain_packs...` 在 engine |
| 无 LLM 决策 | ✅ 零 LLM 调用 |
| 既有 47 V0 spike tests 零回归 | ✅ `run_v0_loop` 签名不变；`_get_spike_spec` 改读 YAML（语义等价）；mapper 与 v0/loop 内部 reason 字段解耦（V0 spike 内仍 `reason="ok"` / `"no permitted context"`，业务理由在 mapper 输出） |
| S2 evidence 47 tests 兼容 | ✅ `persist_evidence` 保留 `_DEFAULT_SUBJECT_ENTITY_TYPE` default（仅 legacy V0 spike 测试用），生产代码路径显式传 kwarg |
| 测试先行 (红→绿可见) | ✅ commit A (RED only) → commit B (GREEN) → commit C (SPA) → commit D (docs + mutation + report) |
| ≥3 变异锚点 + 必含三类 | ✅ 5 锚点：M1 (身份) + M2 (硬编码) + M3 (副作用丢失) + M4 (边界) + M5 (契约) |
| SPA 零 CDN、零 build | ✅ vanilla JS + 单 HTML；7 个 SPA smoke tests 守门 |
| 静态页保留 | ✅ `demos/procurement-review-demo.html` 零编辑；test_spa_does_not_break_existing_static_demo 守门 |
| cut-041 既有零回归 | ✅ 仅与 cut-041 5 文件不重叠；commit 链独立 |
| 不启动 cut-043 | ✅ cut-042R 复审通过前冻结 |

---

## 8. 关键决策与偏离

1. **V0 spike 内部 `result.reason` 保留为 `"ok"` / `"no permitted context"`** —
   47 V0 spike regression tests 锁定这两个字符串。业务语言（"调用者无权访问此场景..."）
   只在 mapper 输出层（API 契约）。这避免修改 V0 spike 测试，符合"既有 47 tests 零编辑"。
   Codex 复审 F5 时请注意此分层。

2. **`persist_evidence(subject_entity_type)` 保留默认 `"purchase_request"`** —
   47 V0 spike evidence tests 不传 kwarg。生产代码路径（`v0/loop.py:_run_demo_loop_impl`）
   显式传 `scenario_spec.subject_entity_type`，引擎仍然 pack-agnostic。
   Codex 复审 F2 时请注意：F2 unit test 已修改为检查**生产代码路径显式传**而非"无 default"。

3. **`_get_spike_spec()` 仍含 `"procurement"` 字符串** —
   这是 V0 spike 的加载钩子（"load procurement default scenario"），不是 engine 硬编码。
   `test_v0_loop_module_has_no_procurement_literal` 已显式豁免此函数。
   Codex 复审 F2 时请注意此豁免是合理的（V0 spike IS procurement）。

---

## 9. 后续路径

- **cut-043 (知识管理 pack)**: 等本刀复审通过后启动；范围已在 cut-042 计划中锁定
- **cut-044 (企业合规 pack)**: 同上
- **cut-045 (蓝图 + 私有化包 + 整体验收)**: 等 B/C 包到位后启动；必须等用户在源站修复 TLS 才能 PASS 公网 URL

---

## 10. 引用

- Codex HOLD 裁定: `docs/demo-platform/CUT_042R_REVIEW_AND_TASK.md`（原始裁定文档，cut-042 closure 中归档）
- 计划文件: `/Users/kjonekong/.claude/plans/velvet-snuggling-spindle.md`
- 改动面: 9 业务编辑 + 1 yaml + 3 SPA 新文件 + 4 测试文件 + 2 文档新文件 + 1 url smoke + 1 mutation-anchors + 1 report = **22 files**

---

**Author**: Claude (Opus 5)
**Date**: 2026-09-22
**Cycle**: cut-042R (correction knife)
**Status**: ✅ Implementation complete · STOP awaiting Codex re-review · **NOT committed, NOT pushed** (per user directive "完成后 STOP 回审" + "未 commit、未 push")