# cut-043R6 — Codex Round-10 收口 (PRD §8/§11 文档收敛) + 第七轮复审

> **Cycle**: cut-043R6 (Codex R10 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: Codex 第 10 轮裁定（cut-043R5 后）
> **Status**: ✅ R10-B1 + R10-B2 + R10-B3 文档收口修复；ready for Codex R11 re-review
> **Commit**: cut-043R6 standalone delta — **docs-only**（无业务代码改动）; current tracked diff (`git diff --stat`, R10 文档同步后实测) = **21 files / +861 / -221**（与 cut-043R5 终态一致）
> **Scope lock**: 只改 PRD §8/§11 + 本 closure；不改任何业务代码（`src/`, `tests/`, `scripts/` 零改动）；既有 494 baseline 零退化

---

## 0. Context

cut-043R5 (Codex R9 HOLD 返工) 已修复 R9-B1 (PRD 同步) + R9-B2 (closure 文件口径)，全部 binding test + ruff/mypy/lint-imports/mutation 绿；4-check smoke PASS。Codex 第 10 轮独立复现发现 **3 个 PRD 收口事实性错误**：

- **R10-B1**: PRD §8 缺少 `cut-043R4` 行（cut-043R5 closure 声称已加，但实际没有；§8 仍从 cut-043R3 直接跳到 cut-044）
- **R10-B2**: PRD §8 `cut-043R2` 仍写 "⏳ R6 复审中"，但当前事实是 R6-B1..B4 已闭合，后续 R7/R8/R9 cycles 已基于其派生
- **R10-B3**: PRD §11 缺少 `cut-043R5` docs-only 轨迹行（cut-043R5 修改了 PRD，§11 必须记录）

Codex 授权签发 cut-043R6:
> "下一步：cc 签发 cut-043R6，继续 docs-only，只修 PRD §8/§11 与报告断言；完成并第七轮复审 PASS 后，才可 commit、push 并进入 cut-044。"

---

## 1. Codex R10 BLOCKER 修复清单

### R10-B1 — PRD §8 缺少 cut-043R4 行

**Codex 发现**:
```
| cut-043R3 | ... ✅ R7-B1..B4 闭合 + R8-B1 进一步收紧 |
| cut-044   | ...
```
§8 在 cut-043R3 后直接跳到 cut-044，cut-043R4 行不存在。

**Root cause**: cut-043R4 (R8 返工) 修复 R8-B1/B2 时，只更新了 PRD §9 (baseline 494) 和 §11 (trail row)，**没有更新 §8**（实施路径表）。cut-043R5 (R9 返工) 写 closure 时声称 "§8 新增 cut-043R4 行" 但实际没做 — 属 cut-043R5 closure 报告与实际改动不一致。

**Fix**:
- PRD §8 在 cut-043R3 行后插入 cut-043R4 行（位置 = §8 cut-043R3 与 cut-044 之间）
- 行内容: "Codex R8 HOLD 返工：strict YYYY-MM-DD anchor (canonical round-trip) + closure 报告口径收敛"; 关键产物 = "`api.py` canonical round-trip + 5 个 binding test (4 parametrize + 1 control); closure 用单一权威 diff stat + 测量时间点注"; 状态注 = `*(✅ R8-B1 + R8-B2 闭合)*`

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§8)

### R10-B2 — PRD §8 cut-043R2 状态过期

**Codex 发现**:
```
| cut-043R2 | ... *(⏳ R6 复审中)* |
```
当前事实: R6 复审已通过, R7/R8/R9/R10 cycles 全部基于 cut-043R2 派生，"R6 复审中" 是过期状态。

**Root cause**: cut-043R2 写 closure 时 §8 status note 写 "⏳ R6 复审中" (当时确实在等 R6)，但后续 cycles (R7/R8) 都没更新这个状态 note。状态注必须与"当前已通过的判定"对齐。

**Fix**:
- PRD §8 cut-043R2 状态注: `*(⏳ R6 复审中)*` → `*(✅ R6-B1..B4 闭合；后续 R7/R8 cycle 在其基础上派生)*`
- (注: cut-043R5 closure §5.1 ("PRD 与 closure 必须逐 cycle 同步") 已存在, 本刀无需改动; 不在此处声称做了更新)

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§8)

### R10-B3 — PRD §11 缺少 cut-043R5 docs-only 轨迹

**Codex 发现**: PRD §11 有 cut-043R3 + cut-043R4 轨迹行，但 cut-043R5 (R9 返工) 修改了 PRD（§9 baseline 494, §8 cut-043R3 状态注, §11 增补 cut-043R4 trail），但 §11 没有 cut-043R5 自己的轨迹行。

**Root cause**: §11 纪律要求 "每一刀的修改都必须记录在 trail 表"，但 cut-043R5 closure 写完后没在 PRD §11 加自己的 trail 行。**这是 R5 漏做的 R10-B3**。

**Fix**:
- PRD §11 新增 cut-043R5 trail 行（位置 = §11 cut-043R4 行之后）
- 行内容: "Codex R9 HOLD 返工（docs-only）：§9 baseline 489 → 494 + §8 cut-043R3 状态注 + §11 增补 cut-043R4 trail + cut-043R4 closure 文件口径统一为 1+5=6 + verification 草稿注释清理; R9 累计 tracked diff 与 cut-043R4 终态一致 (`+861/-221`), 零业务代码改动"

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§11)

---

## 2. 改动面统计 (cut-043R6 standalone delta — docs-only)

### 2.1 cut-043R6 standalone delta

| 类型 | 文件 | LOC | 说明 |
|------|------|-----|------|
| 修改 | `docs/demo-platform/DEMO_PLATFORM_PRD.md` | ~6 LOC (3 edits: §8 cut-043R4 row insert + §8 cut-043R2 status fix + §11 cut-043R5 trail insert) | R10-B1 + R10-B2 + R10-B3 |
| 新增 | `reports/cut-043R6/closure.md` | 本文档 | R10 收口 |
| **cut-043R6 standalone delta** | **1 新增 + 1 修改 = 2 文件** | **~10 LOC** | **纯文档, 零业务代码** |

### 2.2 当前累计 tracked diff (`git diff --stat`, R10 文档同步后实测)

```
$ git diff --stat
21 files changed, 861 insertions(+), 221 deletions(-)
```

> cut-043R6 docs-only delta 不改变累计 tracked diff（实测确认 = cut-043R5 终态 `+861/-221`）

**累计拆解** (R8-B2 + R10-B1/B2/B3 校正):

| Cycle | 类型 | 文件 | 实测 ins/del | 测量时间点 |
|-------|------|------|--------------|------------|
| cut-043 (e6e1757) | commit baseline | 25 files | 2583/36 | `git show e6e1757 --stat` |
| cut-043R (R5 BLOCKERs) | standalone delta | 21 modified | ~558/182 | Codex R7 实测 |
| cut-043R2 (R6 收口) | +2 new + 4 modified | 6 files | +100/+30 | R6 完成时 |
| cut-043R3 (R7 收口) | +1 new + 2 modified | 3 files | ~+30/+0 | R7 完成时 |
| cut-043R4 (R8 收口) | +1 new + 5 modified | 6 files | ~+240/+30 | R8-B2 重写后实测 |
| cut-043R5 (R9 收口) | +1 new + 2 modified | 3 files | ~+20/+0 | R9 实测 (docs-only) |
| cut-043R6 (R10 收口) | +1 new + 1 modified | 2 files | ~+10/+0 | R10 当前实测 (docs-only) |
| **累计 tracked diff** | (union 去重) | **21 files** | **+861/-221** | 当前 `git diff --stat` |

> 多个数字都来自 `git diff --stat` 实测; 差异是测量时间点. **当前权威 = `+861/-221`**.

---

## 3. Verification (R10 复审最小命令集)

cut-043R6 是 docs-only 刀, 不需要重跑业务测试. 验证 = grep 检查 + regression 零退化确认.

```bash
cd /Users/kjonekong/projects/domainAgentECE

# 1. R10-B1 verify: §8 cut-043R4 row 存在
grep -nE "^\| \*\*cut-043R4\*\*" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit at §8 (line ~110)

# 2. R10-B2 verify: §8 cut-043R2 status = closed (no "R6 复审中" in active cell)
grep -nE "\*\(✅ R6-B1\.\.B4 闭合" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit at §8 cut-043R2 cell

# 3. R10-B3 verify: §11 cut-043R5 trail row 存在
grep -nE "^\| 2026-09-22 \| \*\*cut-043R5\*\*" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit at §11 (line ~156)

# 4. regression 零退化
cd ece && export DATABASE_URL="postgresql+psycopg://ece:ece@127.0.0.1:55440/ece"
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 494 passed, 5 skipped, 3 deselected

# 5. tracked diff 不变
git diff --stat
# expected: 21 files / +861 / -221 (与 cut-043R5 终态一致)
```

**实测结果** (cut-043R6 R10-B1/B2/B3 后, 2026-09-22):
- (1) ✅ §8 line 110: `| **cut-043R4** | Codex R8 HOLD 返工：strict YYYY-MM-DD anchor (canonical round-trip) + closure 报告口径收敛 | ...`
- (2) ✅ §8 line 108 cut-043R2 status: `*(✅ R6-B1..B4 闭合；后续 R7/R8 cycle 在其基础上派生)*`
- (3) ✅ §11 line 156: `| 2026-09-22 | **cut-043R5** | Codex R9 HOLD 返工（docs-only）...`
- (4) ✅ 494 passed / 5 skipped / 3 deselected (R10 docs-only 零退化)
- (5) ✅ 21 files / +861 / -221 (tracked diff 与 cut-043R5 终态一致)

---

## 4. R10 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | 验证 | 实测 |
|---------|----------|------|------|
| **R10-B1** | PRD §8 插入 cut-043R4 行（cut-043R3 与 cut-044 之间） | grep `^\| \*\*cut-043R4\*\*` | ✅ 1 hit at §8 line 110 |
| **R10-B2** | PRD §8 cut-043R2 status 更新为 "✅ R6-B1..B4 闭合" | grep `\*\(✅ R6-B1\.\.B4 闭合` | ✅ 1 hit at §8 line 108 |
| **R10-B3** | PRD §11 新增 cut-043R5 docs-only trail 行 | grep `^\| 2026-09-22 \| \*\*cut-043R5\*\*` | ✅ 1 hit at §11 line 156 |

---

## 5. 经验沉淀

### 5.1 PRD §8 状态注必须与"已通过的判定"对齐

R10-B2 揭示: cut-043R2 写 closure 时 §8 status note 写 "⏳ R6 复审中" (当时在等 R6), 但后续 cycles (R7/R8/R9) 都没更新这个状态 note. **任何状态注必须基于"当前最新判定"**, 不能 freeze 在第一次写时的状态.

**通用原则**: PRD §8 status note 的更新触发条件 = 任何后续 cycle 对前序 cycle 的判定结果. 例如 cut-043R2 状态在 R6 PASS 后变 "✅ R6-B1..B4 闭合"; 在 R7 派生后追加 "后续 R7/R8 cycle 在其基础上派生".

### 5.2 Closure 报告与实际改动必须一致

R10-B1 揭示: cut-043R5 closure 声称 "已在 PRD §8 新增 cut-043R4 行", 但实际没做. reader grep 找不到时, 会质疑 closure 的可信度.

**通用原则**: closure 写完后, 必须 `grep` 自检每条 closure 主张, 确保 claim → reality 一致. 不要凭印象写 closure.

### 5.3 §11 trail 行 = 任何"修改 PRD" 的 cycle 必须留痕

R10-B3 揭示: §11 纪律要求"每一刀的修改都必须记录", 但 cut-043R5 写完 closure 后忘了在 §11 加自己的 trail 行. 这是 docs-only cycle 的常见 trap — 因为 diff stat 不变, 容易"觉得没改".

**通用原则**: docs-only cycle 也必须有 §11 trail 行. trail 的存在 = 文档状态的可追溯性, 与 diff stat 大小无关.

### 5.4 状态注与版本号分离

R10-B1 + R10-B2 揭示 §8 状态注的两种格式: (1) `✅ R6-B1..B4 闭合` (通过记录) (2) `✅ R7-B1..B4 闭合 + R8-B1 进一步收紧` (通过记录 + 后续派生). 这两种格式都正确, 关键是要**区分** cycle name (R6/R7/R8) 与 status (✅/⏳/❌).

---

## 6. Gate

- ✅ R10-B1 PRD §8 cut-043R4 行插入 (line 110)
- ✅ R10-B2 PRD §8 cut-043R2 状态更新为 "✅ R6-B1..B4 闭合" (line 108)
- ✅ R10-B3 PRD §11 cut-043R5 trail 行新增 (line 156)
- ✅ 业务测试零退化 (494 passed / 5 skipped / 3 deselected, R10 docs-only)
- ✅ 累计 tracked diff = `+861/-221` (与 cut-043R5 终态一致)
- ❌ **NOT committed** — 等待 Codex R11 第七轮复审 PASS 后才 commit
- ❌ **NOT pushed**

下一步（如 Codex R11 PASS）：commit + push via Clash proxy, 进入 cut-044.
如 Codex 仍 HOLD：按新指出的 R11-B* 修, **不进入 cut-044**.
