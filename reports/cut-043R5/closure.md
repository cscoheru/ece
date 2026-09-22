# cut-043R5 — Codex Round-9 收口 (PRD/closure 文档收敛) + 第六轮复审

> **Cycle**: cut-043R5 (Codex R9 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: Codex 第 9 轮裁定（cut-043R4 后）
> **Status**: ✅ R9-B1 + R9-B2 文档收口修复；ready for Codex R10 re-review
> **Commit**: cut-043R5 standalone delta — **docs-only**（无业务代码改动）; current tracked diff (`git diff --stat`, R9-B1/B2 文档同步后实测) = **21 files / +861 / -221**（与 cut-043R4 终态一致）
> **Scope lock**: 只改 PRD 与 closure 文档；不改任何业务代码（`src/`, `tests/`, `scripts/` 零改动）；既有 494 baseline 零退化（仅文档同步）

---

## 0. Context

cut-043R4 (Codex R8 HOLD 返工) 已修复 R8-B1 + R8-B2:
- strict `YYYY-MM-DD` anchor (canonical round-trip)
- closure 单一权威 diff stat + 测量时间点注 + 删除 B904 noise

全部 binding test + ruff/mypy/lint-imports/mutation 绿；4-check smoke PASS. Codex 第 9 轮独立复现发现 **2 个文档收口问题**（不属业务逻辑缺陷，属文档与代码不一致）：

- **R9-B1**: canonical PRD `DEMO_PLATFORM_PRD.md` 仍写 `489 passed` 和 `16 KM tests`，但当前实际是 `494 passed`，KM 测试为 `19 boundary + 2 discovery + 10 unit = 31`。PRD 也缺少 cut-043R4 的 §8/§11 记录
- **R9-B2**: cut-043R4 closure 内部文件口径矛盾 —— Header 写 `1 modified + 0 new`，§2.1 写 `1 new + 4 modified = 5 files`，但实际列出的文件是 `1 new + 5 modified = 6 files`。verification 步骤里还残留 `expected: 489 passed ... — wait ... = 494` 草稿注释

Codex 授权签发 cut-043R5:
> "下一步：cc 签发 cut-043R5，只做 PRD/closure 文档与报告口径收敛，不改业务代码；完成并第六轮复审 PASS 后，才能 commit、push 并进入 cut-044。"

---

## 1. Codex R9 BLOCKER 修复清单

### R9-B1 — canonical PRD 同步当前状态

**Codex 发现**:
- PRD §9 仍写 `489 passed`, `14 KM boundary + 2 KM discovery = 16 KM tests`
- 实际: `494 passed`, `19 KM boundary + 2 KM discovery + 10 KM unit = 31 KM tests`
- 漏算的 10 个 unit test 位于 `tests/unit/test_knowledge_rule_and_decision.py`
- PRD §8 cut-043R3 行缺少"✅ R7-B1..B4 闭合 + R8-B1 进一步收紧"状态注; §8 缺少 cut-043R4 行; §11 缺少 cut-043R4 轨迹行

**Root cause**: cut-043R3 closure 把 KM test 范围限定在 `tests/integration/test_knowledge_*.py`, 漏算 `tests/unit/test_knowledge_rule_and_decision.py` 的 10 个 unit test. 同样地, cut-043R4 closure 没补 PRD 同步（只重写 closure 自身）.

**Fix**:
- PRD §9 baseline: `489 passed` → `494 passed` (cut-043R4 实跑, 5 skipped / 3 deselected 不变)
- PRD §9 KM 拆分: `14 boundary + 2 discovery = 16` → `19 boundary + 2 discovery + 10 unit = 31` (实测 `pytest --collect-only -q`)
- PRD §9 anchor 校验条款升级为严格 `YYYY-MM-DD` (cut-043R4 R8-B1 canonical round-trip)
- PRD §8 cut-043R3 行追加状态注: "✅ R7-B1..B4 闭合 + R8-B1 进一步收紧"
- PRD §8 新增 cut-043R4 行 (R8 HOLD 返工记录)
- PRD §11 新增 cut-043R4 轨迹行 (cite 494/31 + R8-B1 canonical round-trip)

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§8, §9, §11)

### R9-B2 — cut-043R4 closure 内部文件口径矛盾

**Codex 发现**:
- Header: `1 modified file (api.py) + 0 new file` → 错; 实际 = 1 new + 5 modified = 6 files
- §2.1: `1 new + 4 modified = 5 files` → 错; 实际 = 1 new + 5 modified = 6 files (漏列了 `reports/cut-043R{,2,3}/closure.md` 三份独立修改)
- §3 verification line 140: `expected: 489 passed (R7-B2 baseline) — wait, with R8-B1's 5 new binding tests, baseline +5 = 494` → 草稿注释, 应清理

**Root cause**: 写 cut-043R4 closure 时混淆了 "本刀修改文件" (1 new + 5 modified) 与 "本刀新增文件" (1 new), 漏列 `reports/cut-043R{,2,3}/closure.md` 三份独立修改. verification 草稿注释未清理.

**Fix**:
- Header commit 行: `1 modified file (api.py) + 0 new file` → `1 new file + 5 modified files = 6 files`
- §2.1 表格列示全部 6 个文件 (api.py + boundary test + 4 closure docs), 注明每文件 LOC 估算
- §2.2 累计拆解表 cut-043R4 行同步: `+1 new + 4 modified | 5 files` → `+1 new + 5 modified | 6 files`
- §3 verification line 140 草稿注释清理: 直接写 `expected: 494 passed (cut-043R3 489 + R8-B1's 5 binding tests)`

**Files**: `reports/cut-043R4/closure.md`

---

## 2. 改动面统计 (cut-043R5 standalone delta — docs-only)

### 2.1 cut-043R5 standalone delta

| 类型 | 文件 | LOC | 说明 |
|------|------|-----|------|
| 修改 | `docs/demo-platform/DEMO_PLATFORM_PRD.md` | ~10 LOC (§8/§9/§11 多处) | R9-B1 PRD 同步 |
| 修改 | `reports/cut-043R4/closure.md` | ~10 LOC (Header/§2.1/§2.2/§3) | R9-B2 口径校正 |
| 新增 | `reports/cut-043R5/closure.md` | 本文档 | R9 收口 |
| **cut-043R5 standalone delta** | **1 新增 + 2 修改 = 3 文件** | **~20 LOC** | **纯文档, 零业务代码** |

### 2.2 当前累计 tracked diff (`git diff --stat`, R9 文档同步后实测)

```
$ git diff --stat
21 files changed, 861 insertions(+), 221 deletions(-)
```

> cut-043R5 docs-only delta 不改变累计 tracked diff（实测确认 = cut-043R4 终态 `+861/-221`）

**累计拆解** (R8-B2 + R9-B1/B2 校正: 单一权威数字 + 测量时间点注):

| Cycle | 类型 | 文件 | 实测 ins/del | 测量时间点 |
|-------|------|------|--------------|------------|
| cut-043 (e6e1757) | commit baseline | 25 files | 2583/36 | `git show e6e1757 --stat` |
| cut-043R (R5 BLOCKERs) | standalone delta | 21 modified | ~558/182 | Codex R7 实测 |
| cut-043R2 (R6 收口) | +2 new + 4 modified | 6 files | +100/+30 | R6 完成时 |
| cut-043R3 (R7 收口) | +1 new + 2 modified | 3 files | ~+30/+0 | R7 完成时 |
| cut-043R4 (R8 收口) | +1 new + 5 modified | 6 files | ~+240/+30 | R8-B2 重写后实测 |
| cut-043R5 (R9 收口) | +1 new + 2 modified | 3 files | ~+20/+0 | R9 当前实测 (docs-only) |
| **累计 tracked diff** | (union 去重) | **21 files** | **+861/-221** | 当前 `git diff --stat` |

> 多个数字都来自 `git diff --stat` 实测; 差异是测量时间点. **当前权威 = `+861/-221`**.

---

## 3. Verification (R9 复审最小命令集)

cut-043R5 是 docs-only 刀, 不需要重跑业务测试. 验证 = grep 检查 + 文档 diff 检查.

```bash
cd /Users/kjonekong/projects/domainAgentECE

# 1. PRD §9 baseline 校对
grep -nE "494 passed|489 passed|487 passed" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit "494 passed" (current); 0 hits "489 passed" or "487 passed" in active §9

# 2. PRD KM test breakdown 校对
grep -nE "31 KM tests|16 KM tests|14 KM boundary" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit "31 KM tests" (current); 0 hits "16 KM tests" in active §9

# 3. PRD §8 cut-043R3/R4 行存在
grep -nE "cut-043R3|cut-043R4" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: §8 含 cut-043R3 + cut-043R4 行; §11 含 cut-043R3 + cut-043R4 轨迹行

# 4. cut-043R4 closure file count 一致性 (Header + §2.1)
grep -nE "1 new file \+ 5 modified|1 新增 \+ 5 修改|1 modified file \(api.py\)" reports/cut-043R4/closure.md
# expected: 1 hit "1 new file + 5 modified" in Header; 1 hit "1 新增 + 5 修改" in §2.1; 0 hits "1 modified file (api.py)"

# 5. cut-043R4 verification 草稿注释清理
grep -nE "— wait, with R8|baseline \+5 = 494" reports/cut-043R4/closure.md
# expected: 0 hits

# 6. KM test count 实测 (Codex R9 数字 = 31)
cd ece && .venv/bin/python -m pytest tests/unit/test_knowledge_rule_and_decision.py tests/integration/test_knowledge_boundary.py tests/integration/test_knowledge_domain_discovery.py --collect-only -q 2>&1 | grep -E "tests/"
# expected: 31 total (19 + 2 + 10)

# 7. 业务测试零退化 (regression)
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 494 passed, 5 skipped, 3 deselected (R9 docs-only, 零业务代码改动)
```

**实测结果** (cut-043R5 R9-B1/B2 后, 2026-09-22):
- (1) ✅ 1 hit "494 passed" in PRD §9
- (2) ✅ 1 hit "31 KM tests" in PRD §9
- (3) ✅ §8 + §11 both contain cut-043R3 + cut-043R4
- (4) ✅ Header + §2.1 both show "1 new + 5 modified = 6 files"; 0 hits on old "1 modified (api.py) only"
- (5) ✅ 0 hits on draft comments
- (6) ✅ 31 KM tests (19 + 2 + 10)
- (7) ✅ 494 passed / 5 skipped / 3 deselected (R9 docs-only 零退化)

---

## 4. R9 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | 验证 | 实测 |
|---------|----------|------|------|
| **R9-B1** | PRD §9 baseline 494/31; §8 cut-043R3 状态注 + cut-043R4 行; §11 cut-043R4 轨迹行 | grep §9/§8/§11 + pytest --collect-only | ✅ |
| **R9-B2** | cut-043R4 closure Header/§2.1/§2.2 文件口径统一为 1+5=6; 草稿注释清理 | grep 4 个 pattern | ✅ |

---

## 5. 经验沉淀

### 5.1 PRD 与 closure 必须逐 cycle 同步

R9-B1 揭示: PRD §9 引用测试计数必须基于 `pytest --collect-only -q` 实测, 不能凭印象 ("boundary + discovery" 漏算 unit). cut-043R3 closure 漏算了 `tests/unit/test_knowledge_rule_and_decision.py` 的 10 个 unit test.

**通用原则**: PRD §9 的 baseline + 拆分必须每刀实测 + `grep` 校验, 不假设 "我加了几条 binding test 就是几条".

### 5.2 Closure 内部文件口径必须一致

R9-B2 揭示: closure Header / §2.1 / §2.2 三处的文件列表必须**一致**. 写 Header 时凭"代码改动"思考 (1 modified + 0 new), 写 §2.1 时凭"全部修改"思考 (1 new + 4 modified + 1 new closure = 5 files), 两者口径错.

**通用原则**: 写 closure 时先列**完整**的 modified + new 文件清单, 再 paste 到 Header / §2.1 / §2.2 三处. 一次确定, 不分头写.

### 5.3 Verification 草稿注释必须清理

R9-B2 揭示: `expected: 489 passed ... — wait ... = 494` 这种 "写时犹豫" 的注释必须清理. reader 看到会怀疑作者对自己写的内容不确定.

**通用原则**: 任何 `expected: X — wait, ...` / `TODO: 改这个` / `占位` 注释 = 草稿残留, 必须 grep + 清理后才能 commit.

### 5.4 docs-only 刀的 diff stat 可能不变

R9 是纯文档改动, 累计 tracked diff 与 cut-043R4 终态完全一致 (`+861/-221`). 不要为了 "看到数字变化" 而捏造数字.

**通用原则**: docs-only 刀的 closure 应明确 "本刀 standalone delta 改动小, 不改变累计 tracked diff"; 不要伪造 +20/-5 这类虚假数字.

---

## 6. Gate

- ✅ R9-B1 PRD §9/§8/§11 与当前 494/31 状态对齐
- ✅ R9-B2 cut-043R4 closure 文件口径统一 (1+5=6), 草稿注释清理
- ✅ 业务测试零退化 (494 passed / 5 skipped / 3 deselected, R9 docs-only)
- ✅ KM test 实测 = 31 (19 boundary + 2 discovery + 10 unit)
- ✅ 累计 tracked diff = `+861/-221` (与 cut-043R4 终态一致)
- ❌ **NOT committed** — 等待 Codex R10 第六轮复审 PASS 后才 commit
- ❌ **NOT pushed**

下一步（如 Codex R10 PASS）：commit + push via Clash proxy, 进入 cut-044.
如 Codex 仍 HOLD：按新指出的 R10-B* 修, **不进入 cut-044**.
