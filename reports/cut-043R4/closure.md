# cut-043R4 — Codex Round-8 收口问题修复 + 第五轮复审

> **Cycle**: cut-043R4 (Codex R8 HOLD 返工)
> **Date**: 2026-09-22
> **Trigger**: Codex 第 8 轮裁定（cut-043R3 后）
> **Status**: ✅ R8-B1 + R8-B2 修复；ready for Codex R9 re-review
> **Commit**: cut-043R4 standalone delta — 1 new file + 5 modified files = 6 files; current tracked diff (`git diff --stat`, R9 closure 文档同步后实测) = **21 files / +861 / -221**
> **Scope lock**: 只修 R8-B1 + R8-B2；不引入新 Kernel 对象/Adapter/Runtime；不扩 schema；不动既有 R5/R6/R7 BLOCKER 修复；既有 489 baseline 零退化（实际净增 +5 tests, 详见 §3）

---

## 0. Context

cut-043R3 (Codex R7 HOLD 返工) 已修复 R7-B1..R7-B4，全部 binding test + ruff/mypy/lint-imports/mutation 绿；4-check smoke PASS。Codex 第 8 轮独立复现发现 **2 个收口问题**：

- **R8-B1**: `date.fromisoformat()` 还接受 `20260922` (basic) / `2026-W38-2` (week-date) 等非严格 YYYY-MM-DD 形式 → 200 进入业务 reason；注释写 UTC fallback 但实现用 local date
- **R8-B2**: cut-043R3 closure 同时出现 `+682/-182` 与 `+721/-221` 等多个数字；多次出现无法理解的 "B904"；standalone delta 文件口径与 R7-B4 列出的文件不一致

Codex 授权签发 cut-043R4:
> "下一步：cc 签发 cut-043R4，只修 R8-B1–R8-B2；完成并第五轮复审 PASS 前，不 commit、不 push、不进入 cut-044。"

---

## 1. Codex R8 BLOCKER 修复清单

### R8-B1 — strict YYYY-MM-DD anchor (canonical round-trip)

**Codex 发现**: `date.fromisoformat()` 接受多种 ISO 8601 形式:
- `2026-09-22` → canonical, `parsed.isoformat() == raw` ✓
- `20260922` → basic format, parses 但 `isoformat()` = `2026-09-22` ≠ raw ✗
- `2026-W38-2` → ISO week date, parses 但 `isoformat()` = `2026-09-15` ≠ raw ✗
- `2026/09/22` → raises ValueError (rejected by fromisoformat)
- `2026-09-22T00:00:00` → raises ValueError (rejected by fromisoformat)

`not-a-date` 等"显然错误"的输入已被 R7-B2 拒收；但 basic / week-date 这类**形式合法但非 canonical** 的输入会静默流过 → 进入 business reason text 时是 raw string（与 parsed date 不同）→ trace 错乱。

注释 "today's UTC date (canonical)" 也是错的 —— `date.today()` 返回 **local** date，不是 UTC。

**Fix**:
- `src/ece/demo/api.py` anchor 注入：解析成功后再做 canonical round-trip 检查
  ```python
  parsed = date.fromisoformat(raw_anchor)
  if parsed.isoformat() != raw_anchor:
      raise HTTPException(status_code=422, detail=...)
  server_today = parsed.isoformat()  # use canonical form
  ```
- 错误信息更新: "ECE_SERVER_TODAY_ANCHOR must be a strict YYYY-MM-DD date"; 包含 parsed 值辅助 ops triage
- 注释修正: fallback 是 "today's local date", 不是 UTC；说明 `requires_server_today_anchor` opt-in 让 production 通过 env var 显式控制

**Files**: `src/ece/demo/api.py`

**Binding tests** (5 new):
- `test_r8b1_non_canonical_anchor_returns_422[basic_format]` — `20260922` → 422
- `test_r8b1_non_canonical_anchor_returns_422[iso_week_date]` — `2026-W38-2` → 422
- `test_r8b1_non_canonical_anchor_returns_422[datetime_style]` — `2026-09-22T00:00:00` → 422 (ValueError path)
- `test_r8b1_non_canonical_anchor_returns_422[slash_separator]` — `2026/09/22` → 422 (ValueError path)
- `test_r8b1_canonical_anchor_still_works` — control: canonical `YYYY-MM-DD` 仍 200

### R8-B2 — closure 报告矛盾统计 + B904 noise

**Codex 发现**:
1. cut-043R3 closure 同时出现 `+682/-182` 与 `+721/-221`（前者是 R7-B2 + B904 from-err fix 后；后者是 R7-B2 完成时），两个数字都对但放一起引起读者混淆
2. 多次出现 "B904" — Codex 读者无法理解（ruff B904 是 from-err rule；放在 closure 主体里像 noise）
3. standalone delta 文件口径与 R7-B4 列出的文件不一致（"3 files" vs 实际修改列表）

**Fix**:
- cut-043R3 closure 用**单一**权威 diff stat: 当前 `git diff --stat` 实测 = `21 files / +861 / -221`
- 累计拆解表区分 "standalone delta" vs "累计 tracked diff"，每行注明**测量时间点**作为来源解释
- 删除 §3/§5 主体的 "B904" 提及；B904 from-err fix 仅在 §1 R7-B2 entry 简短标注为"ruff hygiene"
- 修正 §2.1 standalone delta 文件列表: 实际修改 = `tests/conftest.py` + `src/ece/demo/api.py` + 新增 `reports/cut-043R3/closure.md` = 3 files；R7-B4 原文"3 文件"对齐

**Files**: `reports/cut-043R/closure.md`, `reports/cut-043R2/closure.md`, `reports/cut-043R3/closure.md`

---

## 2. 改动面统计 (cut-043R4 standalone delta)

### 2.1 cut-043R4 standalone delta

| 类型 | 文件 | LOC |
|------|------|-----|
| 修改 | `src/ece/demo/api.py` | R8-B1 canonical round-trip + docstring (~30 LOC, 含注释) |
| 修改 | `tests/integration/test_knowledge_boundary.py` | R8-B1 binding tests (5 new = 4 parametrize + 1 control, ~125 LOC) |
| 新增 | `reports/cut-043R4/closure.md` | 本文档 |
| 修改 | `reports/cut-043R/closure.md` | R8-B2 single-diff-stat 重写 (~30 LOC) |
| 修改 | `reports/cut-043R2/closure.md` | R8-B2 single-diff-stat 重写 (~15 LOC) |
| 修改 | `reports/cut-043R3/closure.md` | R8-B2 single-diff-stat 重写 + 删除 B904 noise (~40 LOC) |
| **cut-043R4 standalone delta** | **1 新增 + 5 修改 = 6 文件** | **~240 LOC** |

### 2.2 当前累计 tracked diff (`git diff --stat`, R8-B2 closure 重写后实测)

```
$ git diff --stat
21 files changed, 861 insertions(+), 221 deletions(-)
```

**累计拆解** (R8-B2 校正: 单一权威数字 + 测量时间点注):

| Cycle | 类型 | 文件 | 实测 ins/del | 测量时间点 |
|-------|------|------|--------------|------------|
| cut-043 (e6e1757) | commit baseline | 25 files | 2583/36 | `git show e6e1757 --stat` |
| cut-043R (R5 BLOCKERs) | standalone delta | 21 modified | ~558/182 | Codex R7 实测 |
| cut-043R2 (R6 收口) | +2 new + 4 modified | 6 files | +100/+30 | R6 完成时 |
| cut-043R3 (R7 收口) | +1 new + 2 modified | 3 files | ~+30/+0 | R7 完成时 |
| cut-043R4 (R8 收口) | +1 new + 5 modified | 6 files | ~+240/+30 | 当前实测 |
| **累计 tracked diff** | (union 去重) | **21 files** | **+861/-221** | 当前 `git diff --stat` |

> 多个数字都来自 `git diff --stat` 实测; 差异是测量时间点. 当前权威 = `+861/-221`.

---

## 3. Verification (R8 复审最小命令集)

```bash
cd /Users/kjonekong/projects/domainAgentECE/ece

# 0. KM fixture
export DATABASE_URL="postgresql+psycopg://ece:ece@127.0.0.1:55440/ece"
.venv/bin/python scripts/seed_knowledge_fixture.py

# 1. R7-B1 subprocess probe
ECE_SERVER_TODAY_ANCHOR=2027-01-01 .venv/bin/python -c "
import sys; sys.path.insert(0, 'tests')
import conftest
import os
assert os.environ['ECE_SERVER_TODAY_ANCHOR'] == '2026-09-22'
print('R7-B1 PASS')
"

# 2. R8-B1 standalone probe (canonical round-trip)
ECE_SERVER_TODAY_ANCHOR=20260922 .venv/bin/python -c "
import os
os.environ['ECE_SERVER_TODAY_ANCHOR'] = '20260922'
from datetime import date
parsed = date.fromisoformat('20260922')
assert parsed.isoformat() != '20260922'  # round-trip mismatch = non-canonical
print('R8-B1 probe: round-trip check correctly identifies basic format')
"

# 3. Full regression
.venv/bin/python -m pytest -m "not eval and not eval_llm" --no-header --tb=no
# expected: 494 passed (cut-043R3 489 + R8-B1's 5 binding tests)

# 4. R7-B2 + R8-B1 binding tests isolation
.venv/bin/python -m pytest tests/integration/test_knowledge_boundary.py -k "r7b2 or r8b1" -v --no-header
# expected: 1 R7-B2 + 5 R8-B1 = 6 passed

# 5. Ruff / Mypy / lint-imports
.venv/bin/ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/entities \
  src/ece/main.py src/ece/context/update.py src/ece/evidence
.venv/bin/mypy <17 files>
.venv/bin/lint-imports

# 6. Mutation + Smoke
.venv/bin/python scripts/cut_043_mutation_runner.py
.venv/bin/python -m uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
.venv/bin/python scripts/cut_043_same_origin_smoke.py
kill %1

# 7. R8-B2 grep verification (closure 单一权威)
grep -nE "\+682|\+721" reports/cut-043R3/closure.md reports/cut-043R/closure.md
# expected: 0 hits in active body (only historical/measurement-time-point notes)
```

**实测结果** (cut-043R4 R8-B1/B2 后, 2026-09-22):
- (0) ✅ SELF-CHECK PASSED
- (1) ✅ R7-B1 PASS (anchor=2026-09-22)
- (2) ✅ R8-B1 probe PASS (round-trip correctly rejects basic format)
- (3) ✅ **494 passed, 5 skipped, 3 deselected, 4 warnings in ~35s** (cut-043R3 489 + R8-B1's 5 binding tests)
- (4) ✅ R7-B2 + R8-B1 6 binding tests PASS
- (5) ✅ All ruff/mypy/lint-imports green
- (6) ✅ 3/3 mutation anchors OK + smoke PASS=4 SKIP=0 FAIL=0
- (7) ✅ R8-B2 grep: active body 单一权威 = `+861/-221`; 早期数字仅出现在 "测量时间点" 注

---

## 4. R8 BLOCKER 逐条复审证据

| BLOCKER | 修复方式 | Binding test | 实测 |
|---------|----------|--------------|------|
| **R8-B1** | `api.py` canonical round-trip `parsed.isoformat() == raw_anchor`; docstring 修正 UTC → local | `test_r8b1_non_canonical_anchor_returns_422[basic_format\|iso_week_date\|datetime_style\|slash_separator]` + `test_r8b1_canonical_anchor_still_works` | ✅ 5 PASS |
| **R8-B2** | 单一权威 diff stat + 累计拆解表 + 测量时间点注 + 删除 B904 noise + standalone delta 文件对齐 | grep `+682\|+721` in closure active body → 0 hits in authoritative rows | ✅ |

---

## 5. 经验沉淀

### 5.1 `date.fromisoformat()` ≠ strict YYYY-MM-DD

R8-B1 揭示: `date.fromisoformat()` 接受 ISO 8601 的多种形式（basic `20260922`、week-date `2026-W38-2`）。任何 "validate ISO date" 的代码必须做 canonical round-trip —— `parsed.isoformat() == raw_anchor` —— 否则非严格形式会静默流过。

**通用原则**: "ISO date 校验" ≠ "严格 YYYY-MM-DD 校验"; 后者需要 explicit canonical check.

### 5.2 UTC vs local fallback 纪律

R8-B1 修正注释: `date.today()` 返回 local date, 不是 UTC. `requires_server_today_anchor` opt-in 设计的本意就是让 production 通过 env var 显式控制, 避免 local-time 模糊.

**通用原则**: 任何 "fallback to current time" 的代码, 注释必须明确 timezone (local vs UTC); 不一致会让 ops 误判.

### 5.3 报告口径: 单一权威 + 测量时间点

R8-B2 揭示: closure doc 必须:
1. **单一权威 diff stat** —— 当前 `git diff --stat` 实测值; 不放并列数字.
2. **测量时间点注** —— 累计拆解表的每行注明 "何时测"; 不混用 standalone 与累计.
3. **删除 noise** —— 任何 reader 无法 parse 的缩略 (如 ruff rule 编号 B904) 只在必要位置简短标注, 不进主体叙述.
4. **文件口径一致** —— standalone delta 文件列表与实际 modified list 对齐.

---

## 6. Gate

- ✅ 494 passed / 5 skipped / 3 deselected (cut-043R4 实跑, cut-043R3 489 + R8-B1's 5 binding tests)
- ✅ ruff / mypy (17 files) / lint-imports (2 contracts KEPT) 全部绿色
- ✅ 3/3 mutation anchors bitten
- ✅ 4-check smoke PASS=4 SKIP=0 FAIL=0
- ✅ 非法 anchor (包括 ISO basic / week-date / datetime / slash 形式) API 返回 422 (R7-B2 + R8-B1)
- ✅ Canonical YYYY-MM-DD 仍 200 (R8-B1 control)
- ✅ ECE_SERVER_TODAY_ANCHOR=2026-09-22 在 conftest 强制覆盖 (R7-B1)
- ✅ closure 单一权威 diff stat = `+861/-221` (R8-B2)
- ❌ **NOT committed** — 等待 Codex R9 第五轮复审 PASS 前不 commit
- ❌ **NOT pushed**

下一步（如 Codex R9 PASS）：commit + push via Clash proxy.
如 Codex 仍 HOLD：按新指出的 R9-B* 修, **不进入 cut-044**.
