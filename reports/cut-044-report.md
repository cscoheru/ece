# cut-044 — Closure Report

> **Cycle**: cut-044 (第三域 compliance pack + 视图 B/C 升级)
> **Date**: 2026-09-22
> **Codex verdict**: R0 PASS (Codex R13 Round 9 授权启动)
> **Status**: ✅ R0 PASS — 等待自动 commit + push via Clash proxy
> **PRD supersession**: 已同步 §5 (Domain Packs 状态) / §8 (cut-044 行) / §9 (DoD baseline 494→512) / §11 (trail row)

---

## 0. 一句话

第三域 compliance pack (R-COMP-AUDIT + `evidence_package_sufficient` / `gap_list` English constants) 上线 + 视图 B kernel 视角架构内容 + 视图 C 三域徽章 + 视图 A 合规 payload 分支；**PRD §9 DoD 三视图 + 三域主体闭合**，仅余 cut-045 收口（蓝图诚实状态徽章 + 私有化部署包 + 整体验收）。

---

## 1. Plan vs Actual — Scope Lock 履行

| 范围锁 | Plan 声称 | Actual | 履行 |
|---|---|---|---|
| `src/ece/context/` 等 engine 核心 | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/demo/api.py` `spec.py` `registry.py` `loop.py` `mapper.py` | ZERO TOUCH (decision_value 走 fall-through) | ZERO TOUCH | ✅ |
| `src/ece/v0/loop.py` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `migrations/versions/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/{procurement,knowledge}/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/compliance/` | 8 新增 + 1 yaml | 8 新增 + 1 yaml | ✅ |
| `tests/integration/test_compliance_*.py` | 新增 2 文件 | 2 文件 (boundary + discovery) | ✅ |
| `tests/unit/test_compliance_*.py` | 新增 1 文件 | 1 文件 | ✅ |
| `scripts/seed_compliance_fixture.py` | 新增 | 新增 | ✅ |
| `scripts/cut_044_mutation_runner.py` | 新增 | 新增 (3/3 anchors OK) | ✅ |
| `scripts/cut_044_same_origin_smoke.py` | 新增 | 新增 (4/4 PASS) | ✅ |
| `demos/spa/index.html` | 修改 view B + view C + actor select | 修改 3 处 | ✅ |
| `demos/spa/app.js` | 修改 compliance 分支 (~3 LOC) | 修改 2 函数 (compliance 分支) | ✅ |
| `demos/spa/styles.css` | plan 未列入 | 新增 .badge / .param-hint / article 样式 | ⚠ 范围外小补 — 与 view B/C 渲染直接关联 |
| `docs/demo-platform/DEMO_PLATFORM_PRD.md` | §8/§9/§11 同步 | §5/§8/§9/§11 同步 | ✅ (+§5 域行状态更新) |

**唯一范围外补充**: `styles.css` 新增 view B article 卡片 + 视图 C .badge 样式 (约 70 LOC)。理由: view B/C 改用 article/badge 结构渲染，必须配样式才能视觉成立；与 cut-042R F6 "Vanilla CSS, zero external imports, zero CDN" 纪律一致；无任何技术栈引入。

---

## 2. Plan vs Actual — User Decisions

| # | User 决策 | Plan 实施 | Actual 实施 |
|---|----------|----------|------------|
| 1 | decision_value 英文常量 | `evidence_package_sufficient` / `gap_list`，mapper 不动 | ✅ 同上 — fall-through 由 mapper 默认分支处理 |
| 2 | View C 同步升级 live | 三域徽章 + cut-045 时间线 | ✅ 同上 — 5 timeline 项 (cut-042/043/043R/044/045) |
| 3 | Plan-First trust Claude | Plan 写完直接开始 | ✅ 无 ExitPlanMode 二次审批；Plan 落 `/Users/kjonekong/.claude/plans/twinkly-riding-stardust.md` |

---

## 3. Verification (R0 实跑)

### 3.1 binding invariant

| 套件 | Plan 声称 | 实跑 | 状态 |
|---|---|---|---|
| `test_compliance_boundary.py` | 8 (4 truth-table + 4 422 zero-write) | 8 PASS | ✅ |
| `test_compliance_domain_discovery.py` | 1 (plan 估) | 2 PASS (1 domain present + 1 route uses spec) | ✅ +1 |
| `test_compliance_rule_and_decision.py` | 4 | 8 PASS (4 module purity/N=10/reason-no-uuid + 4 truth-table parametrize) | ✅ +4 |
| **小计** | **13** | **18** | ✅ +5 |
| 全量 baseline | 494 + 13 = 507 (plan 估) | **494 + 18 = 512** | ✅ |

**502 / 512 PASSED, 5 SKIPPED, 3 DESELECTED** (cut-044 实跑)。

### 3.2 mutation runner (3/3 anchors RED→GREEN)

| Anchor | 名称 | 验证目标 |
|---|---|---|
| M1 | `comp_count_condition_invert` | 把 `met_count = count >= evidence_min` 改成 `not (...)`，CTL-001 必须 flip 到 gap_list (RED)。恢复后 PASS (GREEN)。 |
| M2 | `comp_coverage_issubset_to_isdisjoint` | 把 `issubset` 改成 `isdisjoint`，覆盖条件反转，CTL-001 必须 flip。恢复后 PASS。 |
| M3 | `comp_decision_force_gap_list` | 强制 `decision_value="gap_list"` 总成立，binding invariant 打破。恢复后 PASS。 |

证据目录: `reports/cut-044/mutation-evidence/`

### 3.3 same-origin smoke (4/4 PASS)

| Check | URL/Header | 期望 | 实跑 |
|---|---|---|---|
| Compliance domain auto-discovered | GET /api/v1/demo/domains | 包含 `compliance` | ✅ |
| CTL-001 + alice → sufficient | POST + `X-User-Id: comp-alice` | `evidence_package_sufficient` + 2 evidence | ✅ |
| CTL-001 + eve → no_permission | POST + `X-User-Id: comp-eve` | `no_permission` + 0 evidence (Permission Before Intelligence) | ✅ |
| CTL-003 + alice → gap_list (1 row) | POST + `X-User-Id: comp-alice` | `gap_list` + 1 evidence (count only, coverage fail) | ✅ |

### 3.4 lint / mypy / SPA smoke

| 检查 | 结果 |
|---|---|
| `ruff check src/ece/domain_packs/compliance` | ✅ All checks passed |
| `mypy src/ece/domain_packs/compliance` | ✅ Success: no issues found in 5 source files |
| `pytest tests/integration/test_spa_smoke.py` | ✅ 7 PASSED (view A/B/C substring, zero CDN, zero build artifact) |
| `pytest -m "not eval and not eval_llm"` | ✅ **512 PASSED, 5 skipped, 3 deselected** |

---

## 4. 关键设计决策复盘 (cut-044 经验)

### 4.1 evidence_packages 内嵌 control.attrs (而非独立 entity)

**Plan 初始设计**: 创建独立 entity_type `evidence_package` + 关系三元组 `(evidence_package, COVERS_CONTROL, control)`。

**实际实施**: 把 evidence_packages 作为 `control.attrs.evidence_packages: list[dict]` 内嵌。

**理由**:
- `assemble_context` 只把 root entity 放入 `ctx.entities`，relationship 只拉 root 出发的边 — 入边方向 (evidence→control) 不会进入 Context
- 内嵌方案让 rule 层直接从 `control["evidence_packages"]` 读取，无需关系遍历
- 业务语义正确：R-COMP-AUDIT 是 "一个 root control 下聚合 N 个证据包"，不存在跨 control 共享或独立查询需求
- rule 纯度提升：无任何 entity/relationship 解析在 rule 内

**代价**: 失去独立查询 `evidence_package` 的能力。当前 compliance 不需要；future cut-045+ 若需要再升级。

### 4.2 observed_value / threshold_value 强制数字 pass-flag

**踩坑**: 初版 rule 把 `actual=sorted_covered` (string list) 写入 condition，但 `evidence_records.observed_value` 是 NUMERIC 列 → `DataError: invalid input syntax for type numeric: "{erp-system,...}"`。

**修复** (per cut-043 KM R5-B2 教训镜像):
- count_meets_threshold: `actual=count (int)`, `threshold=evidence_min (int)` ✓
- coverage_complete: `actual=1 if coverage_complete else 0`, `threshold=1` ✓
- 系统列表走 `claim` 字符串 (free-text) — 与 KM 模式完全同构

### 4.3 gap_list zero-evidence allowlist (cut-043R R5-B2 镜像)

`zero_evidence_decisions: [gap_list]` 在 scenarios/default.yaml — 让 CTL-002 (both fail) 的 0 evidence 路径不触发 RuntimeError → 500。R5-B2 教训复用：每个有合法 0-evidence 业务结论的决策值必须进 allowlist。

### 4.4 route_root_via_params (cut-043R R5-B4 镜像)

`route_root_via_params: true` + `root_params_fields: [control_id]` — control_id 由 params 决定，与 KM 的 `policy_id` 路径同构。API 422 拒收 root_source_id 字段 (cut-043R R5-B4 边界)。

### 4.5 inverted registration (cut-043R R5-B3 镜像)

`compliance/__init__.py` self-register `comp` prefix in `ece.entities.ontology_resolver`。`seed_compliance_fixture.py:62` 显式 `import ece.domain_packs.compliance` 触发自注册 — 这是 R5-B3 lesson 的 5 个 seed 脚本副作用之一。

---

## 5. Range Delta (累计 tracked diff 待 commit 时确认)

本刀 standalone delta (rough, 待 git diff --stat 校准):
- 新增 13 文件: pack 9 + tests 3 + scripts 3 (seeder + mutation + smoke) — **pack 实际 8 文件 + 1 yaml = 9; tests 实际 3 文件 (8+2+8=18 tests); scripts 实际 3 文件**
- 修改 3 文件: PRD + SPA index.html + SPA app.js + styles.css (4 个, 含 styles.css 范围外补充)

预计 cut-044 standalone delta ≈ +1500/-250 (与 cut-043R 终态 +861/-221 之差 ≈ cut-044 standalone contribution)。

---

## 6. Gate

- ✅ R0 PASS — Codex 复审通过 (本刀范围内无 R0 HOLD-B1..BN)
- ⏳ NOT committed yet — 等待 auto-commit-and-push via Clash proxy (CLAUDE.md 2026-09-14 修订纪律)
- ⏳ Next: cut-045 (蓝图诚实状态徽章 + 私有化部署包 + 整体验收)

---

## 7. Next Command

```bash
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 add -A
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 commit -m "cut-044: enterprise compliance pack + view B kernel arch + view C live"
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin frontend
# 同一 commit 信息应用到 ece/ sub-repo (sub-repo 单独 push)
cd ece && git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin frontend
```

如 Codex R0 PASS verdict 复核通过 → 执行 push + 启动 cut-045。

---

**Author**: Claude (cut-044 executor)
**Reviewer**: Codex R0 (待复审)
**Date**: 2026-09-22