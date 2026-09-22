# cut-043R7 — Codex Round-11 收口 (PRD §11 + R6 closure 校正) + 第八轮复审

> **Cycle**: cut-043R7 (Codex R11 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: Codex 第 11 轮裁定（cut-043R6 后）
> **Status**: ✅ R11-B1 + R11-B2 文档收口修复；ready for Codex R12 re-review
> **Commit**: cut-043R7 standalone delta — **docs-only**（无业务代码改动）; current tracked diff (`git diff --stat`, R11 文档同步后实测) = **21 files / +861 / -221**（与 cut-043R6 终态一致）
> **Scope lock**: 只改 PRD §11 + cut-043R6 closure §1 R10-B2 entry；不改任何业务代码（`src/`, `tests/`, `scripts/` 零改动）；既有 494 baseline 零退化

---

## 0. Context

cut-043R6 (Codex R10 HOLD 返工) 已修复 R10-B1 (PRD §8 cut-043R4 row) + R10-B2 (cut-043R2 status 闭合) + R10-B3 (PRD §11 cut-043R5 trail), 全部 binding test + ruff/mypy/lint-imports/mutation 绿; 4-check smoke PASS. Codex 第 11 轮独立复现发现 **2 个文档事实一致性问题**:

- **R11-B1**: cut-043R6 修改了 PRD (§8 cut-043R4 row + §8 cut-043R2 status + §11 cut-043R5 trail), 但 §11 没有 cut-043R6 trail row. 这违反 cut-043R6 closure 自己总结的 "docs-only cycle 也必须有 §11 trail row" 纪律. 此外, §11 cut-043R4 行仍声称 "(3) ... 新增 cut-043R4 行", 但 R6 closure 已确认该动作实际发生在 cut-043R6.
- **R11-B2**: cut-043R6 closure R10-B2 entry 声称 "同步更新 cut-043R5 closure §5.1", 但 cut-043R5 closure 没有对应修改; 实际只是引用了既有 §5.1 (R5 closure 原文已存在).

Codex 授权签发 cut-043R7:
> "下一步: cc 签发 cut-043R7, 继续 docs-only, 只修上述 R11-B1–R11-B2; 完成并第八轮复审 PASS 后, 才可 commit、push 并进入 cut-044."

---

## 1. Codex R11 BLOCKER 修复清单

### R11-B1 — cut-043R6 trail 缺失 + cut-043R4 §8 attribution 错

**Codex 发现**:
- PRD §11 缺少 cut-043R6 trail row (cut-043R6 自己修改了 PRD 但漏留痕)
- §11 cut-043R4 行第 (3) 点声称 "§8 新增 cut-043R4 行", 实际该动作由 cut-043R6 R10-B1 执行

**Root cause**:
- R6 closure 写完后没在 §11 加自己的 trail row (违反 R6 自己总结的 "docs-only cycle 也必须有 §11 trail row")
- R4 closure 错归因 (§8 R4 row 是 R6 做的, 不是 R4); R5 closure 没校正这个错归因 (R5 改 §11 cut-043R4 trail 行时继承了错文本); R6 closure 改了 §11 但没修正 cut-043R4 行的归因措辞

**Fix**:
- PRD §11 新增 cut-043R6 trail row (line 157): 明确记录 (1) §8 新增 cut-043R4 行 (R10-B1, R4 closure 错归因校正) (2) §8 cut-043R2 status 更新 (R10-B2) (3) §11 新增 cut-043R5 trail row (R10-B3, R5 closure 漏做收口)
- PRD §11 cut-043R4 行第 (3) 点改为归因校正注: "**注意**: cut-043R4 closure 曾声称'§8 新增 cut-043R4 行'——但实际该动作发生在 cut-043R6 R10-B1; cut-043R4 closure 这一笔归因错, 已由 cut-043R6 收口"

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§11)

### R11-B2 — R6 closure 改动断言与实际不一致

**Codex 发现**:
- cut-043R6 closure §1 R10-B2 entry "Fix" 段含 bullet: "同步更新 cut-043R5 closure §5.1 ('PRD 与 closure 必须逐 cycle 同步') 引用此教训"
- 实际 cut-043R5 closure §5.1 已存在 (R5 closure 原文), R6 没做任何修改
- 但 R6 §2.1 standalone delta file list 只列了 PRD.md + R6 closure.md (2 files), 与 R6 §1 R10-B2 声称的 "同步更新 cut-043R5 closure" 不一致

**Root cause**: R6 写 closure 时记错 — 把"引用了既有 §5.1" 当作"修改了 §5.1". 实际没修改任何 R5 closure 文件.

**Fix**:
- cut-043R6 closure §1 R10-B2 "Fix" 段删除 "同步更新 cut-043R5 closure §5.1" bullet, 替换为 "(注: cut-043R5 closure §5.1 ('PRD 与 closure 必须逐 cycle 同步') 已存在, 本刀无需改动; 不在此处声称做了更新)"
- §2.1 file list 保持原样 (PRD + R6 closure = 2 files), 与实际改动一致

**Files**: `reports/cut-043R6/closure.md` (§1 R10-B2)

---

## 2. 改动面统计 (cut-043R7 standalone delta — docs-only)

### 2.1 cut-043R7 standalone delta

| 类型 | 文件 | LOC | 说明 |
|------|------|-----|------|
| 修改 | `docs/demo-platform/DEMO_PLATFORM_PRD.md` | ~12 LOC (§11: cut-043R4 行归因校正注 + cut-043R6 trail row 新增) | R11-B1 |
| 修改 | `reports/cut-043R6/closure.md` | ~3 LOC (§1 R10-B2 "Fix" 段: 删 false claim + 替换为说明) | R11-B2 |
| 新增 | `reports/cut-043R7/closure.md` | 本文档 | R11 收口 |
| **cut-043R7 standalone delta** | **1 新增 + 2 修改 = 3 文件** | **~15 LOC** | **纯文档, 零业务代码** |

### 2.2 当前累计 tracked diff (`git diff --stat`, R11 文档同步后实测)

```
$ cd ece && git diff --stat
21 files changed, 861 insertions(+), 221 deletions(-)
```

> cut-043R7 docs-only delta 不改变累计 tracked diff（实测确认 = cut-043R6 终态 `+861/-221`）

**累计拆解** (R8-B2 + R11-B1/B2 校正):

| Cycle | 类型 | 文件 | 实测 ins/del | 测量时间点 |
|-------|------|------|--------------|------------|
| cut-043 (e6e1757) | commit baseline | 25 files | 2583/36 | `git show e6e1757 --stat` |
| cut-043R (R5 BLOCKERs) | standalone delta | 21 modified | ~558/182 | Codex R7 实测 |
| cut-043R2 (R6 收口) | +2 new + 4 modified | 6 files | +100/+30 | R6 完成时 |
| cut-043R3 (R7 收口) | +1 new + 2 modified | 3 files | ~+30/+0 | R7 完成时 |
| cut-043R4 (R8 收口) | +1 new + 5 modified | 6 files | ~+240/+30 | R8-B2 重写后实测 |
| cut-043R5 (R9 收口) | +1 new + 2 modified | 3 files | ~+20/+0 | R9 实测 (docs-only) |
| cut-043R6 (R10 收口) | +1 new + 1 modified | 2 files | ~+10/+0 | R10 实测 (docs-only) |
| cut-043R7 (R11 收口) | +1 new + 2 modified | 3 files | ~+15/+0 | R11 当前实测 (docs-only) |
| **累计 tracked diff** | (union 去重) | **21 files** | **+861/-221** | 当前 `git diff --stat` |

> 多个数字都来自 `git diff --stat` 实测; 差异是测量时间点. **当前权威 = `+861/-221`**.

---

## 3. Verification (R11 复审最小命令集)

cut-043R7 是 docs-only 刀, 不需要重跑业务测试. 验证 = grep 检查 + regression 零退化确认.

```bash
cd /Users/kjonekong/projects/domainAgentECE

# 1. R11-B1 verify: §11 cut-043R6 trail row 存在
grep -nE "^\| 2026-09-22 \| \*\*cut-043R6\*\*" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit at §11 (line ~157)

# 2. R11-B1 verify: §11 cut-043R4 归因校正
grep -nE "cut-043R4 closure 曾声称" docs/demo-platform/DEMO_PLATFORM_PRD.md
# expected: 1 hit at §11 cut-043R4 行

# 3. R11-B2 verify: R6 closure false claim removed
grep -nE "同步更新 cut-043R5 closure" ece/reports/cut-043R6/closure.md
# expected: 0 hits

# 4. regression 零退化
cd ece && export DATABASE_URL="postgresql+psycopg://ece:ece@127.0.0.1:55440/ece"
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 494 passed, 5 skipped, 3 deselected

# 5. tracked diff 不变
git diff --stat
# expected: 21 files / +861 / -221 (与 cut-043R6 终态一致)
```

**实测结果** (cut-043R7 R11-B1/B2 后, 2026-09-22):
- (1) ✅ §11 line 157: `| 2026-09-22 | **cut-043R6** | Codex R10 HOLD 返工（docs-only）...`
- (2) ✅ §11 line 155 cut-043R4 行: 含 "**注意**: cut-043R4 closure 曾声称'§8 新增 cut-043R4 行'——但实际该动作发生在 cut-043R6 R10-B1"
- (3) ✅ 0 hits on "同步更新 cut-043R5 closure" in R6 closure
- (4) ✅ 494 passed / 5 skipped / 3 deselected (R11 docs-only 零退化)
- (5) ✅ 21 files / +861 / -221 (tracked diff 与 cut-043R6 终态一致)

---

## 4. R11 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | 验证 | 实测 |
|---------|----------|------|------|
| **R11-B1** | PRD §11 新增 cut-043R6 trail row + §11 cut-043R4 行归因校正注 | grep `^\| 2026-09-22 \| \*\*cut-043R6\*\*` + grep `cut-043R4 closure 曾声称` | ✅ 2 hits |
| **R11-B2** | R6 closure §1 R10-B2 删 false claim "同步更新 cut-043R5 closure §5.1"; 替换为 "(注: ... 已存在, 本刀无需改动)" | grep `同步更新 cut-043R5 closure` | ✅ 0 hits |

---

## 5. 经验沉淀

### 5.1 Docs-only cycle 也必须有 §11 trail row

R11-B1 揭示: docs-only cycle (cut-043R6) 修改了 PRD 但忘了在 §11 加自己的 trail row. 这是 R6 closure 自己总结的 "docs-only cycle 也必须有 §11 trail row" 纪律被违反. **任何 cycle 修改了 PRD, 都必须在 §11 加 trail row, 与 diff stat 大小无关**.

**通用原则**: docs-only ≠ invisible. PRD 修改的可追溯性 = §11 trail; cycle 自己 = closure. 两者必须 1:1 配对.

### 5.2 Closure claim → reality 必须逐条 grep 闭环

R11-B1 + R11-B2 都属于 "closure 声称做了 X, 实际没做" 类问题. cut-043R4 closure 声称 "§8 新增 cut-043R4 行", cut-043R6 closure 声称 "同步更新 cut-043R5 closure §5.1" — 两个 claim 都不准确.

**通用原则**: closure 写完后, 每条 "Fix" / "claim" 都必须对应一个 grep 验证. 不准确的 claim 必须显式校正 (R11-B1 的 §11 cut-043R4 行加了 "**注意**" 注), 不能静默删除 (会丢失历史).

### 5.3 §11 trail 校正 = 显式记录, 不静默改

R11-B1 校正 §11 cut-043R4 行时, **没有删除原文本**, 而是追加 "**注意**: ...已由 cut-043R6 收口" 注. 这保留了 cut-043R4 当时写 closure 的视角, 同时标注了后续校正. 静默删除 = 丢失历史; 显式校正 = 历史可追溯.

**通用原则**: §11 trail 是 append-only log; 校正 = 追加注, 不删原文. reader 看到原文本 + 校正注 = 完整历史链.

### 5.4 "引用已有" ≠ "修改"

R11-B2 揭示: cut-043R6 closure §1 R10-B2 "Fix" 段写了 "同步更新 cut-043R5 closure §5.1 引用此教训", 但实际只是引用了既有 §5.1, 没做任何修改. "引用" 和 "修改" 是两个不同动作, closure 必须精确区分.

**通用原则**: closure "Fix" 段必须只列实际做的修改; 引用既有内容应在 "Context" 或 "Note" 段, 不在 "Fix". 把"引用"误写为"修改" = 触发 Codex 钉文件清单 vs claim 不一致.

---

## 6. Gate

- ✅ R11-B1 PRD §11 cut-043R6 trail row 新增 (line 157); §11 cut-043R4 行归因校正注 (line 155)
- ✅ R11-B2 cut-043R6 closure §1 R10-B2 false claim 移除; 替换为 "(注: 已存在, 本刀无需改动)"
- ✅ 业务测试零退化 (494 passed / 5 skipped / 3 deselected, R11 docs-only)
- ✅ 累计 tracked diff = `+861/-221` (与 cut-043R6 终态一致)
- ❌ **NOT committed** — 等待 Codex R12 第八轮复审 PASS 后才 commit
- ❌ **NOT pushed**

下一步（如 Codex R12 PASS）：commit + push via Clash proxy, 进入 cut-044.
如 Codex 仍 HOLD：按新指出的 R12-B* 修, **不进入 cut-044**.
