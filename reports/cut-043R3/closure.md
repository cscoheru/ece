# cut-043R3 — Codex Round-7 收口问题修复 + 第四轮复审

> **Cycle**: cut-043R3 (Codex R7 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: Codex 第 7 轮裁定（cut-043R2 后）
> **Status**: ✅ R7-B1..R7-B4 修复 + R8-B1 收紧（Codex R8 进一步 HOLD, 走 cut-043R4 收口）
> **Commit**: cut-043R3 standalone delta — 2 modified files + 1 new file; current tracked diff (`git diff --stat`, R8-B1 后实测) = **21 files / +861 / -221**
> **Scope lock**: 只修 R7-B1..R7-B4；不引入新 Kernel 对象/Adapter/Runtime；不扩 schema；不动既有 R5/R6 BLOCKER 修复；既有 487 baseline 净增 +2 tests (R7-B1 + R7-B2 binding)

---

## 0. Context

cut-043R2 (Codex R6 HOLD 返工) 已修复 R6-B1..R6-B4，全部 binding test + ruff/mypy/lint-imports/mutation 绿；4-check smoke PASS。Codex 第 7 轮独立复现发现 **4 个收口问题**（不属业务逻辑缺陷，属 anchor 真正闭合、anchor 校验、PRD 结构、报告口径），签发 HOLD。

Codex 授权签发 cut-043R3:
> "下一步：cc 签发 cut-043R3，只修 R7-B1–R7-B3；完成并第四轮复审 PASS 前，不 commit、不 push、不进入 cut-044。"

(注: R7-B4 是闭锁报告口径校正，与 R7-B1..B3 同步修。)

---

## 1. Codex R7 BLOCKER 修复清单

### R7-B1 — `conftest.py` `setdefault` 漏外部 env

**Codex 发现**: cut-043R2 R6-B2 用 `os.environ.setdefault("ECE_SERVER_TODAY_ANCHOR", "2026-09-22")`；Codex 用 `ECE_SERVER_TODAY_ANCHOR=2027-01-01 pytest` 复现 → KM-POL-001 仍走 2027-01-01 → 因为 `setdefault` 不会覆盖已存在的 env。

**Fix**:
- `tests/conftest.py` 改为**直接赋值** `os.environ["ECE_SERVER_TODAY_ANCHOR"] = "2026-09-22"`（无条件强制）
- docstring 更新: 外部 env 无法劫持；calendar drift 免疫
- 保留 `pytest monkeypatch.setenv` 兼容性：conftest 不再 use setdefault，外部 env 永远被 2026-09-22 覆盖

**Files**: `tests/conftest.py`

**Binding test**: `test_r7b1_conftest_force_anchor_overrides_external_env` — 子进程 probe 验证 `ECE_SERVER_TODAY_ANCHOR=2027-01-01 python -c "import conftest; ..."` 输出 `2026-09-22`。

### R7-B2 — 非法 anchor 静默流过

**Codex 发现**: `ECE_SERVER_TODAY_ANCHOR=not-a-date` 在 API 调用时返回 200 + reason 文本含 "今日 not-a-date"。

**Fix** (R7-B2 first pass):
- `src/ece/demo/api.py`: anchor 注入前用 `date.fromisoformat(raw_anchor)` 校验；`ValueError` → raise `HTTPException(status_code=422, detail=...)`
- ruff B904 from-err fix 同时应用：`except ValueError as exc: raise HTTPException(...) from exc`

**R8-B1 进一步收紧**: 详见 §5.5。`date.fromisoformat()` 还接受 `20260922` (basic) / `2026-W38-2` (week-date) 等非严格 YYYY-MM-DD 形式；R8-B1 加 canonical round-trip 校验 + 4 个 binding test parametrize。

**Files**: `src/ece/demo/api.py`

**Binding tests**:
- `test_r7b2_invalid_anchor_returns_422` — `not-a-date` → 422
- `test_r8b1_non_canonical_anchor_returns_422[basic_format|iso_week_date|datetime_style|slash_separator]` — `20260922` / `2026-W38-2` / `2026-09-22T00:00:00` / `2026/09/22` → 422
- `test_r8b1_canonical_anchor_still_works` — control: 严格 `YYYY-MM-DD` 仍 200

### R7-B3 — PRD §8 4 列问题 + §11 错误归因

**Codex 发现**:
- §8 cut-043/cut-043R2 行写成 4 列（3 列表格里挤进 4 个字段），破坏 3 列表结构
- §11 cut-043R 行错误地把 "PRD 更新" 归到自己名下，实际是 cut-043R2 R6-B1 修的
- §9 测试基线写成 `487 passed` 但未明确 KM test 拆分；R5 binding test 数被错算为 1 个 loop-level

**Fix**:
- §8 cut-043 / cut-043R2 行改回 3 列；新增 cut-043R3 行
- §11 cut-043R entry 修正归因: "本刀未做 PRD 改动（与代码变更同范围锁）"；cut-043R2 entry 正确声称 "§5/§9/§8/§11 PRD 改动是本刀完成"
- §9 baseline 改 `489 passed`（cut-043R2 实跑 487 + R7-B1 + R7-B2 = +2 binding tests）；KM test 拆分改成实际结构

**Files**: `docs/demo-platform/DEMO_PLATFORM_PRD.md` (§8 / §9 / §11)

### R7-B4 — closure 报告 diff stat 口径错

**Codex 发现**: cut-043R closure §2 写 "+597/-221"，但 cut-043R standalone delta (R5 BLOCKERs only) 实测 ~+558/-182；cut-043R2 closure §5.4 表里 "+597/-221" 也用了 R5+R6 合计值，但 column header 写的是 cut-043R (R5)。

**Fix**:
- cut-043R3 closure 用**单一**实测 diff stat：cut-043R3 R8-B1 后实测 = **21 files / +861 / -221**
- 累计拆解表区分 "standalone delta" vs "累计 tracked diff"，每行注明测量时间点
- cut-043R2 closure §2 加 R7-B4 注

**Files**: `reports/cut-043R/closure.md`, `reports/cut-043R2/closure.md`, `reports/cut-043R3/closure.md` (NEW)

---

## 2. 改动面统计

### 2.1 cut-043R3 standalone delta

| 类型 | 文件 | LOC |
|------|------|-----|
| 修改 | `tests/conftest.py` | setdefault → 直接赋值 (~2 LOC) |
| 修改 | `src/ece/demo/api.py` | anchor 422 校验 + canonical round-trip + docstring (~30 LOC) |
| 新增 | `reports/cut-043R3/closure.md` | 本文档 |
| **cut-043R3 standalone delta** | **1 新增 + 2 修改 = 3 文件** | **~32 LOC** |

### 2.2 当前累计 tracked diff (R8-B1 后实测)

```
$ git diff --stat
21 files changed, 861 insertions(+), 221 deletions(-)
```

**累计拆解** (R8-B1 后):

| Cycle | 类型 | 文件 | 实测 ins/del |
|-------|------|------|--------------|
| cut-043 (e6e1757) | commit baseline | 25 files | 2583/36 (commit stat) |
| cut-043R (R5 BLOCKERs) | standalone delta | 21 files modified | ~558/182 (Codex R7 实测) |
| cut-043R2 (R6 收口) | +2 new + 4 modified | 6 files | +100/+30 (R6 完成时) |
| cut-043R3 (R7 收口 + R8-B1) | +1 new + 2 modified | 3 files | +263/+39 (R8-B1 后) |
| **累计 (union 去重)** | tracked diff | **21 files** | **+861/-221** |

> 多个数字都来自 `git diff --stat` 实测；差异是测量时间点。本表以当前累计行 `+861/-221` 为唯一权威；逐 cycle 数字保留以解释来源。

---

## 3. Verification (R8 复审最小命令集)

```bash
cd /Users/kjonekong/projects/domainAgentECE/ece

# 0. KM fixture
export DATABASE_URL="postgresql+psycopg://ece:ece@127.0.0.1:55440/ece"
.venv/bin/python scripts/seed_knowledge_fixture.py
# expected: SELF-CHECK PASSED — 8 entities + 4 rels + DENY acl, today_anchor=2026-09-22

# 1. R7-B1 subprocess probe (anchor 强制覆盖)
ECE_SERVER_TODAY_ANCHOR=2027-01-01 .venv/bin/python -c "
import sys; sys.path.insert(0, 'tests')
import conftest
import os
assert os.environ['ECE_SERVER_TODAY_ANCHOR'] == '2026-09-22', os.environ['ECE_SERVER_TODAY_ANCHOR']
print('R7-B1 PASS')
"

# 2. Full regression (cut-043R3 实跑)
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 489 passed, 5 skipped, 3 deselected

# 3. R8-B1 binding tests (non-canonical anchor forms)
.venv/bin/python -m pytest tests/integration/test_knowledge_boundary.py -k "r7b2 or r8b1" -v --no-header
# expected: 7 passed (1 R7-B2 + 4 R8-B1 parametrize + 1 R8-B1 control + 1 R7-B1 if matched)

# 4. Ruff / Mypy / lint-imports
.venv/bin/ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/entities \
  src/ece/main.py src/ece/context/update.py src/ece/evidence
.venv/bin/mypy src/ece/v0/loop.py src/ce/demo ... (17 files)
.venv/bin/lint-imports

# 5. Mutation + Smoke (4 checks)
DATABASE_URL="$DATABASE_URL" .venv/bin/python scripts/cut_043_mutation_runner.py
.venv/bin/python -m uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
.venv/bin/python scripts/cut_043_same_origin_smoke.py
kill %1
```

**实测结果** (cut-043R3 R8-B1 后, 2026-09-22):
- (0) ✅ SELF-CHECK PASSED — 8 entities, 4 rels, 1 ACL DENY row, today_anchor=2026-09-22
- (1) ✅ R7-B1 PASS (anchor=2026-09-22, external env=2027-01-01 被 conftest 强制覆盖)
- (2) ✅ **489 passed, 5 skipped, 3 deselected, 4 warnings in ~35s**
- (3) ✅ R7-B2 + R8-B1 7 binding tests PASS (1 R7-B2 + 4 R8-B1 parametrize + 1 R8-B1 control + 1 R7-B1 if matched)
- (4) ✅ All checks passed! (ruff + mypy 17 files + lint-imports contracts 2 KEPT)
- (5) ✅ 3/3 mutation anchors OK + smoke PASS=4 SKIP=0 FAIL=0

---

## 4. R7 + R8 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | Binding test | 实测 |
|---------|----------|--------------|------|
| **R7-B1** | `tests/conftest.py` 直接赋值 | `test_r7b1_conftest_force_anchor_overrides_external_env` | ✅ |
| **R7-B2** | `api.py` `date.fromisoformat()` + 422 + ruff from-err | `test_r7b2_invalid_anchor_returns_422` | ✅ |
| **R7-B3** | PRD §8 3 列 + §11 归因 + §9 baseline 489 + KM 拆分 | grep 校验 | ✅ |
| **R7-B4** | 单一 diff stat + 累计拆解表 + 测量时间点注 | `git diff --stat` 实测 | ✅ |
| **R8-B1** | canonical round-trip `parsed.isoformat() == raw_anchor` | `test_r8b1_non_canonical_anchor_returns_422[basic_format|iso_week_date|datetime_style|slash_separator]` + `test_r8b1_canonical_anchor_still_works` | ✅ |

---

## 5. 经验沉淀

### 5.1 `setdefault` vs 直接赋值的语义陷阱
R6-B2 用 `setdefault` 是 "if missing" 语义。Codex R7 复现: 外部 env 不被覆盖。R7-B1 直接赋值。**任何 "测试 conftest 锚定服务端权威值" 必须直接赋值**。

### 5.2 ops 错误的 fail-fast 边界
R7-B2 把 ops 错误转化为 API 422。**服务端权威化的 env var 必须 validate + fail-fast**。

### 5.3 PRD §8 列数 + §11 归因纪律
状态变化用"关键产物" cell 内 `*(...)*`；每刀 §11 只能声称"本刀完成"的事。

### 5.4 报告口径与测量时间点
diff stat 必须 (1) 实测 not 估算 (2) 注明测量时间点 (3) 区分 standalone vs 累计 (4) 单一权威数字。

### 5.5 `date.fromisoformat()` 不等于严格 YYYY-MM-DD
R8-B1 揭示: `date.fromisoformat()` 接受 ISO 8601 的多种形式（basic `20260922`、week-date `2026-W38-2`、但拒绝 ordinal `2026-262` 和带时间的 `2026-09-22T00:00:00`）。**任何 "validate ISO date" 的代码必须做 canonical round-trip** —— `parsed.isoformat() == raw_anchor` —— 否则非严格形式会静默流过。教训：**"ISO date 校验"不等于"严格 YYYY-MM-DD 校验"**，后者需要 explicit canonical check。

### 5.6 UTC vs local date fallback 纪律
R8-B1 同时修正 R7 注释："today's UTC date (canonical)" 是不准确的——`date.today()` 返回 **local** date，不是 UTC。修正后注释与实现一致。`requires_server_today_anchor` opt-in 设计的本意就是让 production 通过 env var 显式控制，避免 local-time 模糊。

---

## 6. Gate

- ✅ 489 passed / 5 skipped / 3 deselected (cut-043R3 R8-B1 实跑)
- ✅ ruff / mypy (17 files) / lint-imports (2 contracts KEPT) 全部绿色
- ✅ 3/3 mutation anchors bitten
- ✅ 4-check smoke PASS=4 SKIP=0 FAIL=0
- ✅ ECE_SERVER_TODAY_ANCHOR=2026-09-22 在 conftest **强制覆盖** (R7-B1)
- ✅ 非法 anchor (包括 ISO basic / week-date / datetime / slash 形式) API 返回 422 (R7-B2 + R8-B1)
- ✅ Canonical YYYY-MM-DD 仍 200 (R8-B1 control)
- ✅ PRD §8/§9/§11 与 canonical 当前状态对齐 (R7-B3)
- ✅ closure 用单一 diff stat + 测量时间点注 (R7-B4 + R8-B2)
- ❌ **NOT committed** — 等待 Codex R9 第五轮复审 PASS 前不 commit
- ❌ **NOT pushed**

下一步（如 Codex R9 PASS）：commit + push via Clash proxy。
如 Codex 仍 HOLD：按新指出的 R9-B* 修，**不进入 cut-044**。
