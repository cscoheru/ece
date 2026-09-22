# cut-042R3 — Boundary Consistency + Doc Rewrite + Real Mutation Evidence

> **Cycle**: cut-042R3 (third-round correction)
> **Date**: 2026-09-22
> **Owner**: Claude (Opus 5)
> **Codex verdict being closed**: `docs/demo-platform/CUT_042R2_REVIEW_ROUND3_HOLD.md` (HOLD)
> **Status**: 📋 Implementation complete — STOP for Codex round-4 review
>
> **Scope lock**: only fix R3-B1 / R3-B2 / R3-B3; no new Kernel/Adapter/Runtime;
> no new domain packs; no migrations; no LLM; no schema changes.

---

## 1. TL;DR

All 3 round-3 blockers addressed with real evidence. Test suite **463 passed / 5 skipped / 3 deselected** (vs Codex third-round baseline 455 passed; +8 boundary tests). Ruff + mypy green. 6/6 mutation anchors executed end-to-end with real stdout captured.

| R3-# | Finding | Fix | Verification |
|------|---------|-----|--------------|
| **R3-B1** (CRITICAL) | quote_count=999 → DB=3 but reason="999 家报价"; quote_count=-1 → DB=0 but evidence=-1 | `v0/loop.py` step [3c-refresh] ALWAYS refreshes `effective_params` from re-read; `demo/api.py` rejects negative with 422 | `tests/integration/test_quote_count_boundary.py` (NEW 7+1 tests, all PASS) + loop-level direct test |
| **R3-B2** | Root canonical docs still said "单 docker compose up 起全栈" / "docker compose 单命令" / "SPA out of cut-042 scope" | Rewrote §3, §8 cut-045 row, §9 DoD; deleted "SPA out of cut-042 scope" line; §11 converted from "修订附录" to supersession trail | `grep -nE "单 docker compose up 起全栈|docker compose 单命令|原 PRD §7"` in active contract sections returns 0 hits |
| **R3-B3** | Mutation evidence was markdown only; M1–M5 "mentally executed" claim | New `scripts/cut_042r3_mutation_runner.py` runs real mutation → RED pytest → restore → GREEN pytest, captures both stdout | `reports/cut-042R3/mutation-evidence/M{1..6}-*.md` + README index — all 6 OK |
| **R4-B1** | Bound test only asserted DB SELECTS, no Context SELECTS assertion; 422 branch had no zero-write snapshot | Added `_count_selects_from_context()` helper that calls `assemble_context` in-package; each 200 case asserts `DB SELECTS == Context SELECTS == expected_db_selects`; 422 case takes pre/post snapshot of root.attrs / SELECTS / evidence count and asserts byte-equal | Bound matrix 8/8 PASS with `DB == Context == expected` invariant binding; 422 zero-write binding |
| **R4-B2** | R3 report wrongly claimed `evidence observed=3` for 3/4/999 (S2 says quote condition does not pass → no quote evidence); `cut-042R2-VERIFICATION-STATUS.md` still has stale 457/3 + NOT reproducible | R3 report §3.3 table rewritten to mark quote evidence as **absent (条件未 passed, S2)** for 3/4/999; `cut-042R2-VERIFICATION-STATUS.md` superseded with `SUPERSEDED by cut-042R3-report.md` banner + current 463/5/3 numbers | Bound test now explicitly asserts `len(quote_rows) == 0` for 3/4/999 (PASS); `cut-042R2-VERIFICATION-STATUS.md` superseded |

---

## 2. Test counts (Codex third-round baseline + R3 additions)

### 2.1 R3-B1 NEW tests — 8

| File | Tests | Purpose |
|------|-------|---------|
| `tests/integration/test_quote_count_boundary.py` (NEW) | 7 parametrize + 1 loop-level | R3-B1: DB / Context / evidence / reason four-way consistency for `quote_count ∈ {-1, 0, 1, 2, 3, 4, 999}` |

All 8 PASS.

### 2.2 Full suite (real run)

```
$ DATABASE_URL="postgresql+psycopg://ece:ece@localhost:55440/ece" \
  uv run pytest -m "not eval and not eval_llm"
463 passed, 5 skipped, 3 deselected, 2 warnings in 31.08s
```

Baseline at Codex third-round was **455 passed** (per `CUT_042R2_REVIEW_ROUND3_HOLD.md` §2). +8 boundary tests = 463.

Skip details:
- 5 skipped: 2 E2 runner exit 3 + 3 real-LLM tests (ECE_LLM_BASE_URL not set)
- 3 deselected: `-m "not eval and not eval_llm"` marker exclusion

---

## 3. R3-B1 fix — Always-refresh + Reject-negative

### 3.1 Root cause (confirmed)

`v0/loop.py` step [3c] re-read post-materialize, but the refresh was **guarded** by `if "quote_count" not in params`. When client provided a value, the loop kept the original (pre-clamp) value in `effective_params` while the DB had the clamped value.

```python
# BEFORE (cut-042R2, buggy)
if "quote_count" not in params:
    effective_params["quote_count"] = len(quotes)  # only refresh when client didn't provide
```

Result for `quote_count=999`:
- Materializer clamps to pool size (3) → DB SELECTS = 3
- Loop's re-read sees 3 SELECTS
- BUT `effective_params["quote_count"]` stays 999 (client value)
- Rule writes evidence with `observed=999`
- Reason string built from `999`

For `quote_count=-1`:
- API allowed it (no validation)
- Materializer `max(0, int(-1)) = 0` → DB SELECTS = 0
- Re-read sees 0 SELECTS
- BUT `effective_params["quote_count"]` stays -1
- Evidence observed=-1, reason says "−1 家报价"

### 3.2 Fix — two-step

**Step A (loop.py)**: delete the guard, always refresh from re-read:

```python
# AFTER (cut-042R3, fixed)
# [3c-refresh] ALWAYS refresh effective_params from the post-materialize
# re-read, regardless of whether the client provided a value.
effective_params["amount"] = root["attrs"].get("amount", 0)
effective_params["quote_count"] = len(quotes)
```

**Step B (api.py)**: reject negative at API boundary:

```python
if isinstance(req.params, dict) and "quote_count" in req.params:
    qc = req.params["quote_count"]
    if not isinstance(qc, int) or isinstance(qc, bool) or qc < 0:
        raise HTTPException(
            status_code=422,
            detail=f"quote_count must be a non-negative integer, got {qc!r}",
        )
```

(Rejecting `bool` because `isinstance(True, int) == True` in Python — booleans would slip through.)

### 3.3 Boundary matrix (parametrize)

S2 evidence-semantics rule (per `tests/integration/test_params_land_in_db.py:151-152`
code comment): **only persisted evidence rows for conditions that passed**.
The rule's quote condition is `quote_count < REQUIRED(3)`. So:

- `quote_count ∈ {0, 1, 2}` (< REQUIRED): quote condition **passes** → a
  quote evidence row IS persisted (observed == DB SELECTS).
- `quote_count ∈ {3, 4, 999}` (>= REQUIRED, even after clamp): quote
  condition **does NOT pass** → NO quote evidence row is persisted
  (decision_value ≠ auto_approved, reason uses materialized count).

| client_qc | HTTP | DB SELECTS | Context SELECTS | quote evidence | reason contains | Result |
|-----------|------|-----------|-----------------|----------------|-----------------|--------|
| -1        | 422  | unchanged (snapshot) | unchanged (snapshot) | unchanged (snapshot) | (zero-write) | 四方 + 零写入 ✅ |
| 0         | 200  | 0         | 0               | 0 (passed)     | "0 家"          | 四方一致 ✅ |
| 1         | 200  | 1         | 1               | 1 (passed)     | "1 家"          | 四方一致 ✅ |
| 2         | 200  | 2         | 2               | 2 (passed)     | "2 家"          | 四方一致 ✅ |
| 3         | 200  | 3         | 3               | **absent (条件未 passed, S2)** | "3" | 四方一致 ✅ |
| 4         | 200  | 3 (clamp) | 3 (clamp)       | **absent (条件未 passed, S2)** | "3" | 四方一致 ✅ |
| 999       | 200  | 3 (clamp) | 3 (clamp)       | **absent (条件未 passed, S2)** | "3" | 四方一致 ✅ |

The 7-case matrix + 1 loop-level direct test all PASS.

**R4-B1 fix (binding invariant, not reviewer blackbox)**: each 200 case calls
`assemble_context` in-package and asserts `Context SELECTS == DB SELECTS ==
expected_db_selects`. The 422 case additionally takes a pre/post snapshot of
`root.attrs`, `SELECTS` count, and `evidence_records` count and asserts all
three are byte-equal — proving the API boundary is genuinely zero-write, not
just an HTTP-level 422.

---

## 4. R3-B2 fix — Canonical doc rewrite

### 4.1 What changed

| File | Line | Before | After |
|------|------|--------|-------|
| `docs/demo-platform/DEMO_PLATFORM_PRD.md` | 44 (now 44) | "硬约束: 离线可运行——前端零 CDN 零 build，单 `docker compose up` 起全栈" | "硬约束: **两阶段部署**（cut-042R2 / cut-042R3 修订，supersedes 旧版"单 `docker compose up` 起全栈"）：API + DB 阶段 `docker compose up` 离线可演示；SPA 阶段由客户自有 nginx 反代 `/api/`" |
| `docs/demo-platform/DEMO_PLATFORM_PRD.md` | 109 (cut-045 row) | "docker compose 单命令" | "私有化一键包（API+DB docker compose + SPA nginx 反代）" |
| `docs/demo-platform/DEMO_PLATFORM_PRD.md` | §9 DoD (rewritten) | "原 PRD §7 单 `docker compose up` 全栈方案已被访谈-001 客户本地化部署约束推翻" | "推力 = 访谈-001 客户本地化部署约束（已 supersede 早期"单 `docker compose up` 起全栈"方案）" + R3 实跑计数 + R3-B1 边界一致性条款 |
| `docs/demo-platform/DEPLOY_USER_PROXY.md` | 218 | "⏳ The SPA assets themselves are out of cut-042 scope (delivered separately or in cut-045)" | "✅ **The SPA assets themselves (`demos/spa/`) were delivered in cut-042**, and the same-origin smoke `scripts/cut_042r2_same_origin_smoke.py` validates a single-origin browser path (Codex third-round verification: `PASS=5 SKIP=0 FAIL=0`)." |

### 4.2 §11 converted to supersession trail

Previously §11 was a "cut-042R2 修订附录" — Codex R3-B2 said "附录不能替代原文" so §11 is now a pure audit trail:

> **§11. 文档 supersession 轨迹（不是新增契约 — 仅为历史可追溯）**
> 纪律: 本节只记录"何时、因何、由谁"对正文的修改；不引入新规则、新 DoD、新边界。

The row contains a `grep -nE "单 docker compose up 起全栈|docker compose 单命令|原 PRD §7"` verification command with expected output of "0 hits".

### 4.3 Remaining grep hits

`grep -nE "单 docker compose up|docker compose 单命令|原 PRD"` returns 3 hits:
- §11 row itself (describing what got replaced — historical)
- §11 grep-verification code block (intentional, the test command)
- DEPLOY_USER_PROXY.md `>` quote blocks labeled "cut-042R3 note (supersedes any earlier..."

All three are explicitly framed as supersession / historical / verification — not active contract. §3, §8, §9 are clean.

---

## 5. R3-B3 fix — Real mutation harness + 6 stdout archives

### 5.1 Runner architecture

`scripts/cut_042r3_mutation_runner.py`:

```
For each of M1-M6:
  1. backup target file → .bak.M{n}
  2. apply string-level mutation (single find/replace, no sed)
  3. run targeted pytest → RED stdout
  4. restore from backup
  5. run targeted pytest → GREEN stdout
  6. md5 verify (pre == post)
  7. write reports/cut-042R3/mutation-evidence/M{N}-{slug}.md
```

Final exit asserts all target files restored to pre-mutation md5.

### 5.2 The 6 mutations + their bites

| Anchor | Mutation | Test | RED exit | RED marker | GREEN |
|--------|----------|------|----------|------------|-------|
| **M1** | `_re_read_through_assembly(...)` call → `re_read_attrs = pr_attrs_before` (skip re-read) | `test_re_read_asks_the_assembly_path_again` | 1 | `RuntimeError: loop did not close` | 0 ✅ |
| **M2** | `apply_context_update` skip SQL block (`return` before `conn.execute`) | `test_loop_result_carries_every_step_product` | 1 | `RuntimeError: loop did not close` | 0 ✅ |
| **M3** | Permission ACL bypass (`if False and not decision.allowed`) in assembly.py | `test_denied_user_does_not_write_to_db` | 1 | `AssertionError: ... != expected` | 0 ✅ |
| **M4** | `_evaluate_via_params` injects `time.time() * 1000 % 1000` into amount | `test_determinism_under_loop_runs_byte_equal_decision_and_conditions` | 1 | `AssertionError` (different observed across N=10) | 0 ✅ |
| **M5** | `jwt.decode(token, options={"verify_signature": False})` (skip signature) | `test_decode_jwt_token_invalid_signature` | 1 | `AssertionError: claims is None` (claims became dict instead) | 0 ✅ |
| **M6** | `if False and descriptor.materialize_fn is not None` (R3-F2 specific) | `test_params_quote_count_lands_in_db_after_loop` | 1 | `AssertionError: DB SELECTS != expected` | 0 ✅ |

**6/6 BITTEN**. Each evidence file contains:
- Full RED stdout (with FAIL/ERROR + exception class + first 60 lines)
- Full GREEN stdout (with `passed` confirmation)
- File-restored md5 verification
- Restoration assertion at end of runner (`assert _md5(target_path) == original_md5`)

### 5.3 Evidence index

```
reports/cut-042R3/mutation-evidence/
├── README.md                                            (auto-generated index)
├── M1_re_read_through_assembly_skipped.md
├── M2_apply_context_update_skip_sql.md
├── M3_permission_acl_check_bypassed.md
├── M4_evaluated_conditions_inject_nondeterministic_amount.md
├── M5_jwt_decode_skips_signature_verification.md
└── M6_materialize_fn_disabled_in_loop.md
```

---

## 6. Quality gates

```
$ uv run ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/main.py
All checks passed!

$ uv run mypy src/ece/v0/loop.py src/ece/demo src/ece/main.py
Success: no issues found in 8 source files
```

---

## 7. Scope discipline (R3 范围锁验证)

| 锁项 | 验证 |
|------|------|
| 不引入新 Kernel 对象/Adapter/Runtime | ✅ `loop.py` 改 refresh 逻辑 + `api.py` 加 422 入参校验 |
| 不动 migrations | ✅ schema 不动 |
| 不动 S2 evidence 语义 | ✅ evidence 持久化路径不变 |
| 不动 materializer clamp 算法 | ✅ clamp 是有意设计, 修法是"用 clamp 后值" |
| 不引入新 LLM | ✅ 422 是入参校验, 不经 LLM |
| 不引入新 domain pack | ✅ 仍只 procurement |
| 不动 S3 rule module 纯度 | ✅ materializer 仍在独立 module, rule 仍纯函数 |
| 既有 V0 spike tests 零回归 | ✅ 全量 463 passed = 455 baseline + 8 boundary |
| `463 passed` 实跑可复现 | ✅ R3 测试矩阵 + same-origin smoke + mutation harness 都归档 |
| mutation harness 不污染源码 | ✅ md5 verify 强制恢复, runner exit 前断言 |

---

## 8. Files changed (vs cut-042R2 closure)

```
ece/src/ece/v0/loop.py                                  (R3-B1: step [3c-refresh] always)
ece/src/ece/demo/api.py                                 (R3-B1: 422 for negative quote_count)
ece/tests/integration/test_quote_count_boundary.py      (NEW, 8 tests)
ece/scripts/cut_042r3_mutation_runner.py                (NEW, R3-B3 harness)
ece/reports/cut-042R3-report.md                         (NEW, this file)
ece/reports/cut-042R3/mutation-evidence/README.md       (NEW, auto-generated)
ece/reports/cut-042R3/mutation-evidence/M1..M6-*.md     (NEW, 6 stdout archives)
docs/demo-platform/DEMO_PLATFORM_PRD.md                 (R3-B2: §3, §8, §9, §11 rewrite)
docs/demo-platform/DEPLOY_USER_PROXY.md                  (R3-B2: §3, §218 rewrite + supersession note)
```

10 files; ~+600 LOC (8 boundary tests + runner + 6 evidence files + report), ~50 LOC edits.

---

## 9. Gate (per Codex 第三轮裁定 + 第四轮裁定)

- ❌ **NOT committed** — per user "完成后 STOP 回审 / 未 commit、未 push"
- ❌ **NOT pushed**
- ❌ **cut-043 NOT started** — "复审通过前不启动 cut-043"
- ❌ **知识管理 pack NOT started** — 第三轮裁定显式扩展
- ✅ Code, tests, smoke, mutation harness, doc rewrite all on disk; awaiting Codex round-5 review
- ✅ 463 passed / 5 skipped / 3 deselected (实跑可复现)
- ✅ 8/8 boundary matrix PASS with binding `DB == Context == expected` invariant
- ✅ 422 zero-write assertion binding (pre/post snapshot byte-equal)
- ✅ S2 semantics explicit (3/4/999 quote evidence ABSENT, reason uses materialized 3)
- ✅ ruff + mypy green
- ✅ 6/6 mutation anchors with real stdout captured

---

## 10. References

- Codex 第三轮 HOLD: `docs/demo-platform/CUT_042R2_REVIEW_ROUND3_HOLD.md`
- Codex 第四轮 HOLD: `docs/demo-platform/CUT_042R3_REVIEW_ROUND4_HOLD.md`
- cut-042R3 plan: `.claude/plans/twinkly-riding-stardust.md`
- cut-042R2 report (predecessor): `reports/cut-042R2-report.md`
- V0 spike EXECUTION_SPEC: `docs/v0/V0_EXECUTION_SPEC.md`
- DEMO platform PRD (R3-B2 rewrite): `docs/demo-platform/DEMO_PLATFORM_PRD.md`
- Deploy recipe (R3-B2 rewrite): `docs/demo-platform/DEPLOY_USER_PROXY.md`
- Boundary matrix tests (R3-B1 + R4-B1/R4-B2): `tests/integration/test_quote_count_boundary.py`
- Mutation runner: `scripts/cut_042r3_mutation_runner.py`
- Mutation evidence: `reports/cut-042R3/mutation-evidence/`
- SUPERSEDED status doc: `reports/cut-042R2-VERIFICATION-STATUS.md` (see top banner)
