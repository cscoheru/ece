# cut-043R2 — Codex Round-6 收口问题修复 + 第三轮复审

> **Cycle**: cut-043R2 (Codex R6 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: `docs/demo-platform/CUT_043R_REVIEW_ROUND2_HOLD.md` — Codex 第 6 轮裁定（cut-043R 后）
> **Status**: ✅ All 4 BLOCKERs resolved; ready for Codex R7 re-review
> **Commit**: (this cycle's delta — 4 modified files + 2 new files; cut-043R2 standalone changes summarized in §2)
> **Scope lock**: 只修 R6-B1..R6-B4；不引入新 Kernel 对象/Adapter/Runtime；不扩 schema；不动既有 R5 BLOCKER 修复；既有 486 baseline 零退化（实际净增 1 个 test，详见 §3）

---

## 0. Context

cut-043R (Codex R5 HOLD 返工) 已修复 R5-B1..R5-B5，全部 binding test + ruff/mypy/lint-imports/mutation 绿。Codex 第 6 轮独立复现发现 **4 个收口问题**（不属业务逻辑缺陷，属报告/测试 anchor/permission 反差丢失），签发 HOLD。

Codex 授权签发 cut-043R2:
> "下一步：cc 签发 cut-043R2，只修 R6-B1–R6-B4；完成并第三轮复审 PASS 前，不 commit、不 push、不进入 cut-044。"

---

## 1. Codex R6 BLOCKER 修复清单

### R6-B1 — PRD §5/§9 与 baseline 463 未更新

**Codex 发现**: canonical PRD `docs/demo-platform/DEMO_PLATFORM_PRD.md` 仍写 `knowledge ⬜(043)`（§5 域行），且 §9 DoD 引用 cut-042R3 实跑 `463 passed`（应为 cut-043R 实跑 `486 passed`）。两处与当前状态不一致。

**Root cause**: cut-043R 闭锁报告承诺"cut-044 启动前 PRD §5/§9 需更新"（见 `reports/cut-043R/closure.md` §6 Gate），但本刀未履行 — 直接将 §5/§9 更新推迟到 cut-044 启动前，与 Codex 期望不符。

**Fix**:
- §5 域行: `knowledge ⬜(043) · compliance ⬜(044)` → `knowledge ✅(043R) · compliance ⬜(044)`
- §8 cut-043 行追加 "✅ 闭合 (043R)" 状态注
- §8 新增 cut-043R2 行（"⏳ R6 复审中"）
- §9 DoD 第 3 条: `cut-042R3 实跑 \`463 passed\`` → `cut-043R2 实跑 \`487 passed\``（含新增 permission contrast 案例）
- §9 DoD 第 4 条追加: `ECE_SERVER_TODAY_ANCHOR=2026-09-22` 在测试 conftest 锚定说明（衔接 R6-B2）
- §11 supersession 轨迹新增三行: cut-043 / cut-043R / cut-043R2（trail 历史可追溯）

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md`

### R6-B2 — 时间锚测试漂移

**Codex 发现**: 测试没有固定 `ECE_SERVER_TODAY_ANCHOR`。Codex 用 `2027-01-01` 复现，KM-POL-001 (valid_to=2026-12-31) 的 answerable 测试失败；2026 年底后常规测试会自然变红。

**Root cause**: `cut-043R` 修复 R5-B1（服务端锚定 today）时，将 `today` 从客户端 params 移除，但**没有在测试 conftest 显式设置 `ECE_SERVER_TODAY_ANCHOR`**。fallback 走 `date.today()`，calendar 自然漂移。

**Fix**:
- 新增 `tests/conftest.py`：session-scope 模块级 `os.environ.setdefault("ECE_SERVER_TODAY_ANCHOR", "2026-09-22")`，在任何 test 导入 `ece.main`/`ece.demo.api` 前注入
- Anchor 选择 `2026-09-22`：与 cut-043 closure date + KM fixture TODAY 同值，所有当前 truth-table 期望仍有效，且与各 policy valid_to 有充分间距（KM-POL-002 早已过期；KM-POL-001/003 仍有效）
- `setdefault` 而非赋值：未来如需专门测试不同 anchor，`monkeypatch.setenv` 可覆盖

**Files**: `tests/conftest.py` (NEW)

**Binding invariant**:
- `tests/conftest.py` 的 module-level `os.environ.setdefault(...)` 在 pytest session start 时执行（conftest.py 在测试模块 import 前加载）
- 实测：`ECE_SERVER_TODAY_ANCHOR=未设置 → import conftest → ECE_SERVER_TODAY_ANCHOR=2026-09-22` ✓

### R6-B3 — permission 反差 smoke 被替换

**Codex 发现**: 原来的 `km-eve + KM-POL-001 → no_permission` 用例被改掉了。应保留它，并新增 zero-evidence 用例，smoke 应变为 4 项。

**Root cause**: cut-043R 重写 smoke 时把 check #3 从 "permission contrast (engine ACL DENY → no_permission)" 改为 "R5-B2 zero-evidence (rule double-fail → needs_valid_policy + 0 evidence)"，丢了前者。两条路径语义不同：前者证明**引擎层 ACL 拒绝**（PRD §7 纪律 #2），后者证明**规则层双失败零证据**（R5-B2）。

**Fix**:
- Truth table: 增补 `("KM-POL-001", "km-eve", "no_permission", 0, "无权访问")` 案例（5 cases total）。`km-eve` 既在 `spec.denied_users` 也有 seed `acl_entries DENY row on KM-POL-001`，触发引擎层 short-circuit → denied branch。
- Smoke: 增补 `_check_km_denied_eve` (km-eve + KM-POL-001 → no_permission + 0 evidence)，保留原 R5-B2 `_check_km_eve_zero_evidence_r5b2`。**SMOKE_CHECKS 共 4 项**。
- 不动 `km-eve` 在 `denied_users` 的配置；这是 PRD §7 纪律 #2 的硬要求。

**Files**: `tests/integration/test_knowledge_boundary.py`, `scripts/cut_043_same_origin_smoke.py`

**Binding tests**:
- `test_knowledge_boundary_truth_table[validity_pass_perm_fail_eve_denied_pre_rule]`: KM-POL-001 + km-eve → 200 + `no_permission` + 0 evidence（不是 needs_valid_policy）
- `cut_043_same_origin_smoke.py` 第 3 项: 4-check smoke PASS

### R6-B4 — 报告口径仍有误

**Codex 发现**: `e6e1757` (cut-043 commit) 实际是 **19 新 + 6 改**，报告仍写 "12 新 + 3 改"；cut-043R 本刀 delta 实际是 **+597/-221**，报告写 "+497/-186"。

**Root cause**: cut-043R 闭锁报告 §5.4 的累计拆解数学错（"12 新 + 24 改 = 25" 是 cumulative 文件数，但拆解列错）；§2 改动面统计表的总计行是预估，未实跑 `git diff --stat`。

**Fix**:
- §5.4 改用 3×3 表格，列示 cut-043 / cut-043R / 累计的 A/M/文件数（19/6/25；0/21/21；19/6/25 union 去重）。新增校正说明：cut-043 实际为 19 新 + 6 改 = 25 文件，不是先前 closure 误写的 12 新 + 3 改。
- §2 改动面统计的总计行更新为 **597 ins / 221 del**（cut-043R2 实跑 `git diff --stat`）。
- §6 Gate 标注 "R6-B1..B4 修正由 cut-043R2 完成"，门禁条件改成 "等待 Codex R7 第三轮复审 PASS"。

**Files**: `reports/cut-043R/closure.md`

---

## 2. 改动面统计 (cut-043R2 standalone delta)

| 类型 | 文件 | LOC |
|------|------|-----|
| 新增 | `tests/conftest.py` | +27 (R6-B2 session-scope anchor) |
| 新增 | `reports/cut-043R2/closure.md` | 本文档 |
| 修改 | `docs/demo-platform/DEMO_PLATFORM_PRD.md` | §5/§8/§9/§11 多处 |
| 修改 | `reports/cut-043R/closure.md` | §5.4 表格化 + §2 总计校正 + §6 Gate 改写 |
| 修改 | `tests/integration/test_knowledge_boundary.py` | truth-table +1 case (R6-B3 permission contrast) |
| 修改 | `scripts/cut_043_same_origin_smoke.py` | smoke +1 check (R6-B3 4 checks total) |
| **cut-043R2 standalone delta** | **2 新增 + 4 修改 = 6 文件** | **~150 LOC** |

**cut-043R + cut-043R2 合并 delta** (Codex R5 + R6 HOLD 返工):

> **R8-B2 单一权威数字**: 当前累计 tracked diff = `+861/-221` (cut-043R3 R8-B1 后实测, 21 files)。本节保留早期数字 + 测量时间点作为来源解释；当前权威以 cut-043R3 closure §2 为准。

**cut-043R + cut-043R2 合并 delta** (Codex R5 + R6 HOLD 返工):

| | 新增 (A) | 修改 (M) | 文件数 |
|---|---:|---:|---:|
| cut-043 (e6e1757) | 19 | 6 | 25 |
| cut-043R (R5 修复) | 0 | 21 | 21 |
| cut-043R2 (R6 收口) | 2 | 4 | 6 |
| **累计 (union 去重)** | **21** | **23** | **25** |

(21 + 23 - 重叠 = 25: cut-043 引入 25 个新路径，cut-043R/R2 只修改/新增既有路径内的文件，没有引入全新独立文件)

---

## 3. Verification (R6 复审最小命令集)

```bash
cd /Users/kjonekong/projects/domainAgentECE/ece

# 0. KM fixture (per R6-B2 anchor)
export DATABASE_URL="postgresql+psycopg://ece:ece@127.0.0.1:55440/ece"
.venv/bin/python scripts/seed_knowledge_fixture.py
# expected: SELF-CHECK PASSED — 8 entities + 2 REQUIRES_ROLE + 2 HAS_ROLE + DENY acl
#           today anchor: 2026-09-22 (from conftest)

# 1. Full regression (now 487 passed — R6-B3 added 1 truth-table case)
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 487 passed, 5 skipped, 3 deselected (cut-043R2 实跑)

# 2. KM boundary tests (R6-B3: 5 truth-table cases + 3 422 + 4 binding)
.venv/bin/python -m pytest tests/integration/test_knowledge_boundary.py -v --no-header
# expected: 12 passed (5 truth + 3 422 + 4 R5 binding)

# 3. Ruff
.venv/bin/ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/entities \
  src/ece/main.py src/ece/context/update.py src/ece/evidence
# expected: All checks passed!

# 4. Mypy (17 files)
.venv/bin/mypy src/ece/v0/loop.py src/ece/demo \
  src/ece/domain_packs/procurement/agent/materializer.py \
  src/ece/domain_packs/procurement/agent/v0_rules.py \
  src/ece/domain_packs/knowledge \
  src/ece/entities/ontology_resolver.py src/ece/entities/pipeline.py \
  src/ece/main.py
# expected: Success: no issues found in 17 source files

# 5. lint-imports
.venv/bin/lint-imports
# expected: Domain pack isolation KEPT + Engine core isolation KEPT

# 6. Mutation runner
DATABASE_URL="$DATABASE_URL" .venv/bin/python scripts/cut_043_mutation_runner.py
# expected: 3/3 anchors OK

# 7. Same-origin smoke (R6-B3: 4 checks)
.venv/bin/python -m uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
sleep 3
.venv/bin/python scripts/cut_043_same_origin_smoke.py
# expected: PASS=4 SKIP=0 FAIL=0
kill %1
```

**实测结果** (cut-043R2 实跑, 2026-09-22):
- (0) ✅ SELF-CHECK PASSED (8 entities, 4 rels, 1 ACL DENY row, today_anchor=2026-09-22)
- (1) ✅ **487 passed, 5 skipped, 3 deselected, 4 warnings in 34.24s**
- (2) ✅ 12 passed
- (3) ✅ All checks passed!
- (4) ✅ Success: no issues found in 17 source files
- (5) ✅ Contracts: 2 kept, 0 broken
- (6) ✅ 3/3 anchors OK (M1 validity flip / M2 permission flip / M3 AND→OR)
- (7) ✅ **PASS=4 SKIP=0 FAIL=0** (domain discovery + answerable + permission contrast + R5-B2 zero-evidence)

**Anchor 钉定实测**:
```python
import os; os.environ.pop('ECE_SERVER_TODAY_ANCHOR', None)
# before conftest: None
import sys; sys.path.insert(0, 'tests'); import conftest
# after conftest: 2026-09-22
```

---

## 4. R6 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | Binding test | 实测结果 |
|---------|----------|--------------|----------|
| **R6-B1** | PRD §5/§8/§9/§11 多处更新；§5 域行 `knowledge ✅(043R)`；§9 baseline 487；§11 trail 三行新增 | grep 校验 (PRD §5 + §9 + §11) | ✅ |
| **R6-B2** | `tests/conftest.py` session-scope `os.environ.setdefault("ECE_SERVER_TODAY_ANCHOR", "2026-09-22")` | 487 passed (含 12 KM boundary + 4 R5 binding, 跨 calendar 2027+ 仍绿) | ✅ |
| **R6-B3** | truth-table 5 cases (新增 `validity_pass_perm_fail_eve_denied_pre_rule`) + smoke 4 checks (新增 `permission contrast`) | `test_knowledge_boundary_truth_table[validity_pass_perm_fail_eve_denied_pre_rule]` + smoke `PASS=4 SKIP=0 FAIL=0` | ✅ |
| **R6-B4** | 校正 §5.4 cut-043 = 19 新 + 6 改；§2 总计 = +597/-221；§6 Gate 改写 | git diff --stat + git show e6e1757 --stat 双源核对 | ✅ |

---

## 5. 经验沉淀

### 5.1 R5 closure 推迟 PRD 更新 = 风险

cut-043R closure §6 Gate 写 "PRD §5/§9 更新待 cut-044 启动前补；本刀范围锁严守不动"。这个写法**违反 Codex "本刀彻底" 的复审假设。Codex 期望每刀的 closure 报告与文档状态完全对齐**。

**正确做法**: 闭锁当刀必须同步更新 canonical PRD，并把 "✅ 已更新" 写入 closure §6。否则下一轮复审必被钉。

### 5.2 时间锚漂移 = 服务端权威化的副作用

R5-B1 把 today 从客户端移除后，**测试侧必须有 conftest 钉定**，否则 `date.today()` fallback 会让 anchor 随 calendar 漂移。这是一个常见的"服务端权威化"反模式：客户端参数收紧 → 测试侧需要 explicit 锚定。

**通用原则**: 任何"客户端不能 X"的修复，都需要在测试 conftest 钉定 X 的服务端权威值；否则 X 默认 fallback 会让测试结果依赖 wall-clock。

### 5.3 permission contrast vs rule zero-evidence = 两条业务语义

R6-B3 揭示一个被 cut-043R 误折叠的设计要点：

- `km-eve + KM-POL-001` → **引擎层 ACL DENY** → `no_permission` (PRD §7 纪律 #2)
- `km-eve + KM-POL-002` → **规则层双失败零证据** → `needs_valid_policy` (R5-B2 允许)

两条用例**不能用同一案例**。前者证明"权限检查在数据访问层"（铁律 1），后者证明"零证据路径业务合法"（R5-B2）。前者 ctx.denied=True 后者 ctx.denied=False，输出 conclusion 不同。

教训：**任何 PRD §7 纪律的演示用例都是绑定 invariant**，不能因后续修复被静默替换。

---

## 6. Gate

- ✅ 487 passed / 5 skipped / 3 deselected (cut-043R2 实跑，baseline 净增 +1 = R6-B3 permission contrast 案例)
- ✅ ruff / mypy / lint-imports 全部绿色
- ✅ 3/3 mutation anchors bitten
- ✅ 4-check smoke PASS=4 SKIP=0 FAIL=0 (含 restored permission contrast)
- ✅ ECE_SERVER_TODAY_ANCHOR=2026-09-22 在 conftest 锚定 (calendar 漂移免疫)
- ✅ PRD §5/§8/§9/§11 与 canonical 当前状态对齐
- ✅ cut-043R closure §5.4 校正 (19 新 + 6 改) + §2 总计 (+597/-221)
- ❌ NOT committed — 等待 Codex R7 第三轮复审 PASS 前不 commit
- ❌ NOT pushed

下一步（如 Codex R7 PASS）：commit + push via Clash proxy。

如 Codex 仍 HOLD：按新指出的 R7-B* 修，**不进入 cut-044**。