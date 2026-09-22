# cut-044R2 — Closure Report

> **Cycle**: cut-044R2 (corrective cycle for cut-044R1 Codex R1 HOLD)
> **Date**: 2026-09-22
> **Triggers**: `docs/demo-platform/CUT_044R1_REVIEW_ROUND2_HOLD.md` (Codex R1 3-blocker verdict)
> **Scope lock**: 只修 R2-B1..R2-B3; 不动 Kernel / 其他 pack / LLM / migrations; 既有 523 tests 零退化
> **Status**: ⏳ Code self-check 全绿 → ⏳ 提交 (双推 via Clash proxy) → ⏳ Codex R2 复审 (待复审)

---

## 0. 一句话

cut-044R1 Codex R1 HOLD 3 阻断全部修正: R2-B1 审计期间必填改为 **spec-driven** (改 caller-behavior trigger → spec.params_schema contract source); R2-B2 `today` 加入 strict YYYY-MM-DD canonical round-trip (R1 漏校验 today); R2-B3 closure 文件计数 13 → 14 修正 + 边界保证措辞从 "guaranteed non-empty" 改为 "spec-driven validation" 真实描述. 累计 **529 passed** (R2 +6) / 5 skipped / 3 deselected / 零退化. Same-origin smoke **PASS=10** (R2 +2 R2-B1/R2-B2 新增).

---

## 1. Plan vs Actual — Scope Lock 履行

| 范围锁 | R2 计划 | Actual | 履行 |
|---|---|---|---|
| `src/ece/context/` engine core | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/demo/spec.py` `registry.py` `loop.py` `mapper.py` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/demo/api.py` | 修改 (R2-B1/R2-B2 spec-driven block, ~80 LOC) | 修改 ~70 LOC (替换 caller-behavior trigger 为 spec-driven validation) | ✅ |
| `src/ece/v0/loop.py` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `migrations/versions/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/{procurement,knowledge}/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/compliance/agent/v0_rules.py` | 修改 (wrapper docstring 措辞) | 修改 ~17 LOC (docstring + 注释: OR-fallback 改为 defensive only) | ✅ |
| `tests/integration/test_compliance_boundary.py` | 修改 (+3 R2-B1 + 3 R2-B2 = +6 422 cases) | +6 cases 全部 RED→GREEN | ✅ |
| `scripts/cut_044_same_origin_smoke.py` | 修改 (+2 R2-B1/R2-B2 checks = 8→10) | +2 checks PASS | ✅ |
| `reports/cut-044R1-closure.md` | 修改 (§1 文件计数 13→14) | §1 加 R2-B3 校正块 | ✅ |
| `reports/cut-044R2-closure.md` | 新增 | 本文件 | ✅ |

**总文件数 (cut-044R2 standalone delta)**: 4 修改 (api.py + v0_rules.py + test_compliance_boundary.py + cut_044_same_origin_smoke.py) + 2 修改 (cut-044R1-closure.md 校正块 + 新增本文件) = **6 文件**.

> **R2-B3 数字校正对比**:
>
> | 来源 | 原数 | 校正后 | 校正理由 |
> |---|---|---|---|
> | `cut-044R1-closure.md` §1 总文件数 | 13 文件 | **14 文件** | 漏算 ece sub-repo 1 个新 closure file (10 modified + 1 new = 11, 加 parent 1 + memory 2 = 14, 非 13) |
> | `cut_044_same_origin_smoke.py` 总 check 数 | 8 checks | **10 checks** | R2 加 R2-B1 + R2-B2 各 1 个 new check |
> | `cut-044R2` 实跑 pytest | R1 baseline 523 | **529 passed** | R2 +6 (3 R2-B1 + 3 R2-B2 boundary cases) |
> | Wrapper 边界保证措辞 | "guaranteed non-empty canonical" | **"spec-driven validation"** | R2-B1 黑盒证伪: caller-behavior trigger (`if "period_start" in params or "period_end" in params`) 让 BOTH 缺失绕过校验 |

---

## 2. Plan vs Actual — User Decisions (R2 锁定 from Codex R1 VERDICT)

| # | User 决策 (Codex R1 裁定) | R2 实施 | Actual 实施 |
|---|---|---|---|
| 1 | **R2-B1** spec-driven required-field: 缺 BOTH period fields → 422 | 改 api.py 触发条件: caller-behavior → spec-driven (`"period_start" in spec.params_schema`); 同样 spec-driven 触发 today 校验 | ✅ 实施 + 3 黑盒 422 cases (R2_B1_missing_both_period / missing_only_period_start / missing_only_period_end) |
| 2 | **R2-B2** today strict canonical round-trip (二选一: 校验 or 移除); 本刀选校验 (保留 today 是 caller-supplied business param) | api.py 同 spec-driven block 加 today strict round-trip (仅 caller-supplied, NOT `requires_server_today_anchor=true` 时跳过) | ✅ 实施 + 3 黑盒 422 cases (R2_B2_missing_today / malformed_today / non_canonical_iso_today) |
| 3 | **R2-B3** closure 文件计数 + 边界保证措辞 | git diff 真实统计; spec-driven 措辞反映 wrapper 真实运行模型 | ✅ §1 加 R2-B3 校正块 + R2 closure 自带校正 |

---

## 3. Verification (R2 实跑)

### 3.1 binding invariant

| 套件 | R2 计划 | 实跑 | 状态 |
|---|---|---|---|
| `tests/unit/test_compliance_rule_and_decision.py` | 12 (无变化) | 12 PASS | ✅ |
| `tests/integration/test_compliance_boundary.py` | 15 + 6 R2 = 21 | **21 PASS** | ✅ |
| `tests/integration/test_compliance_domain_discovery.py` | 2 | 2 PASS | ✅ |
| **小计** | **35** | **35** | ✅ |

### 3.2 全量 baseline

```text
pytest -m "not eval and not eval_llm"
→ 529 passed, 5 skipped, 3 deselected
```

cut-044R1 baseline 523 → cut-044R2 529 (+6 from R2 new boundary cases: 3 R2-B1 + 3 R2-B2). **零退化**.

### 3.3 Quality gates

| Gate | Command | 结果 |
|---|---|---|
| ruff | `ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/entities src/ece/main.py src/ece/context/update.py src/ece/evidence` | ✅ All checks passed! |
| mypy | `mypy src/ece/v0/loop.py src/ece/demo src/ece/domain_packs/procurement/agent/materializer.py src/ece/domain_packs/procurement/agent/v0_rules.py src/ece/domain_packs/knowledge src/ece/domain_packs/compliance src/ece/entities/ontology_resolver.py src/ece/entities/pipeline.py src/ece/main.py` | ✅ Success: no issues found in 22 source files |
| lint-imports | `lint-imports` | ✅ Contracts: 2 kept, 0 broken |
| mutation runner | `cut_044_mutation_runner.py` | ✅ 3/3 anchors OK (M1 count invert / M2 coverage isdisjoint / M3 force gap_list) |
| same-origin smoke (R2 新增 2 checks) | `cut_044_same_origin_smoke.py` | ✅ **PASS=10 SKIP=0 FAIL=0** (8 prior + 2 R2-B1/R2-B2) |

### 3.4 R2-B1 + R2-B2 black-box boundary matrix (6 cases)

| # | 场景 | 期望 | 实跑 |
|---|---|---|---|
| 1 | **R2_B1_missing_both_period_422** | 422 / "period_start" in detail | ✅ |
| 2 | **R2_B1_missing_only_period_start_422** | 422 / "period_start" in detail | ✅ |
| 3 | **R2_B1_missing_only_period_end_422** | 422 / "period_end" in detail | ✅ |
| 4 | **R2_B2_missing_today_422** | 422 / "today" in detail | ✅ |
| 5 | **R2_B2_malformed_today_422** | 422 / "today" in detail (today="not-a-date") | ✅ |
| 6 | **R2_B2_non_canonical_iso_today_422** | 422 / "today" in detail (today="20260922" basic) | ✅ |

所有 422 cases 继续断言 zero-write (pre/post snapshot byte-equal: attrs / REQUIRES_SYSTEM count / evidence_records count).

### 3.5 R2 same-origin smoke (10 checks via true reverse proxy)

| # | Check | R2 Status |
|---|---|---|
| 1 | R1-B3 SPA index.html reachable from origin (proxy proof) | PASS |
| 2 | Compliance domain auto-discovered in /domains | PASS |
| 3 | Compliance sufficient (COMP-CTL-001 + comp-alice) | PASS |
| 4 | Compliance permission contrast (comp-eve + COMP-CTL-001 → no_permission) | PASS |
| 5 | Compliance coverage-only fail (COMP-CTL-003 + comp-alice → gap_list) | PASS |
| 6 | R1-B1 reversed period_start > period_end via origin → 422 | PASS |
| 7 | R1-B1 empty period_start via origin → 422 | PASS |
| 8 | R1-B1 request_before_evidence via origin → gap_list (audit-period intersection) | PASS |
| 9 | **R2-B1 missing BOTH period fields via origin → 422 (spec-driven required-field)** | **PASS** |
| 10 | **R2-B2 malformed today='not-a-date' via origin → 422 (strict YYYY-MM-DD canonical)** | **PASS** |

Total: **PASS=10 SKIP=0 FAIL=0** via cut-042R2 R2-F3 ThreadingHTTPServer reverse proxy.

### 3.6 attribution grep 自检

```bash
grep -rnE "Codex R0 PASS|R0 PASS|502 / 512|502/512" \
  reports/cut-044-report.md \
  reports/cut-044R1-closure.md \
  reports/cut-044R2-closure.md \
  docs/demo-platform/DEMO_PLATFORM_PRD.md \
  .claude/projects/-Users-kjonekong/memory/domainAgentECE-cut-044-closure.md \
  .claude/projects/-Users-kjonekong/memory/MEMORY.md
```

**预期**: 所有命中都在校正 / 解释文本, 状态声明 0 命中.
**实际**: ✅ 全部命中在解释文本 (`cut-044-report.md §8 R1-B2 / R12-REPORT` / `cut-044R1-closure.md §7 R9 衍生铁律` / `cut-044-report.md §1 状态行` / `PRD §8 cut-044 行 R0 HOLD` 标注 / `MEMORY.md` R0 HOLD 警告 / `CUT_044_REVIEW_ROUND1_HOLD.md` 是裁定源不是 status claim). 状态声明 (Status / Codex verdict / Reviewer) 均已校正.

---

## 4. R2-B1 设计决策 (Why & How)

### 4.1 Spec-driven validation (而非 caller-behavior trigger)

```python
# cut-044R1 (FLAWED — caller-behavior trigger)
if "period_start" in req.params or "period_end" in req.params:
    # validate period_start, period_end → 422 if missing/malformed
    # But: missing BOTH fields → caller-behavior trigger is False → bypass
```

```python
# cut-044R2 (FIXED — spec-driven contract)
spec_declares_period = (
    "period_start" in spec.params_schema
    or "period_end" in spec.params_schema
)
spec_declares_today_caller_supplied = (
    "today" in spec.params_schema and not spec.requires_server_today_anchor
)
if spec_declares_period or spec_declares_today_caller_supplied:
    # validate strictly — required-field semantics from spec contract
```

**Why spec-driven 而不是 caller-behavior**:
- Caller-behavior (`if X in req.params`) 是 optional-validation 语义:
  caller 不送 = caller 没要求校验, 因此 spec 声明的必填字段可被绕过
- Spec-driven (`if X in spec.params_schema`) 是 required-field 语义:
  spec 声明必填 = API 必填, caller 无法通过"省略"绕过
- 这是 cut-043R4 R8-B1 在 server anchor 上的成功模式; R2 把同模式扩展到
  audit period + today

**How to apply**: 任何"`spec.params_schema` 声明 X → X 在 API 必填" 的场景,
默认 spec-driven trigger; 若业务确实要 optional (e.g., debug flag), 用
explicit caller opt-in 字段, NOT caller-behavior trigger.

### 4.2 today validation 仅 caller-supplied 时启用

```python
# cut-044R2 — today 校验条件: spec declares + NOT requires_server_today_anchor
spec_declares_today_caller_supplied = (
    "today" in spec.params_schema and not spec.requires_server_today_anchor
)
```

**Why**: KM (Knowledge Management) 包声明 `requires_server_today_anchor=true`,
today 由 server 在 env-validation 后注入, 不需要 caller 校验 (也不能让 caller 覆盖);
Compliance 不声明, today 是 caller-supplied business param (审计基准日),
必须 strict 校验防止 today="not-a-date" 静默通过.

**How to apply**: 区分 server-owned vs caller-supplied today 走不同路径;
所有 caller-supplied 日期参数都必须 strict canonical round-trip.

---

## 5. R2-B3 设计决策 (Why & How)

### 5.1 Closure 文件计数 — git 真实统计

```bash
# ece sub-repo
git diff --stat <R2-base-commit>..<R2-commit> -- ece/

# parent repo
cd .. && git diff --stat <R2-base-commit>..<R2-commit>

# external memory (不在 git repo 内, 由 cc 维护)
ls -la .claude/projects/-Users-kjonekong/memory/domainAgentECE-cut-044-closure.md \
       .claude/projects/-Users-kjonekong/memory/MEMORY.md
```

**Why**: cut-044R1 closure 算术错误 (10 modified ece + 3 modified 父仓 = 13).
R2 真实: 11 ece files (10 modified + 1 new closure) + 1 parent PRD + 2 memory = **14**.

### 5.2 边界保证措辞 — 描述真实运行模型

| 措辞版本 | 描述 | 是否准确 |
|---|---|---|
| R1 原版 | "wrapper 收到时 period_start/period_end 必然 non-empty canonical" | ❌ R2-B1 黑盒证伪 (missing BOTH → bypass) |
| R2 校正 | "spec.params_schema declares X → API 必填 X" (spec-driven) | ✅ 与 api.py 实现一致 |

**Why**: 边界保证的真实来源是 **api.py spec-driven validation block**, 不是
wrapper 内部任何 OR-fallback. 旧措辞用"guaranteed"是把 API 契约错误归因到 wrapper
本身 — wrapper 本质上是 params 的 consumer, 它对 params 的契约保证是 0 维度
(只能 trust caller OR api boundary). 真实保证在 api.py spec-driven block.

**How to apply**: 任何 rule / wrapper docstring 在描述"上游保证"时, 必须指明
保证的真实所在层 (api boundary / loader / materializer). 不要把 API 契约
错误归因到 rule / wrapper.

---

## 6. R1 → R2 cumulative state (closure evolution)

| 维度 | cut-044 | cut-044R1 | cut-044R2 |
|---|---|---|---|
| pytest baseline | 512 passed | 523 passed (+11) | **529 passed (+6)** |
| Same-origin smoke | 4 checks (名不副实) | 8 checks (真 reverse proxy, +4) | **10 checks** (+2 R2-B1/R2-B2) |
| 审计期间校验 | 假参数 (rule 只读 today) | strict canonical round-trip + period_start<=period_end | **+ spec-driven 必填 (R2-B1)** |
| today 校验 | (无) | (无 — R1 漏) | **strict canonical round-trip (R2-B2)** |
| Closure 文件计数准确性 | n/a | 算术错 (13 ≠ 实际 14) | **校正 14** |
| 边界保证措辞准确性 | n/a | over-claimed ("guaranteed non-empty") | **spec-driven validation** |

---

## 7. Gate

- ⏳ Code self-check 全绿 (529 passed, mutation 3/3, ruff/mypy/lint-imports green, same-origin smoke 10/10)
- ⏳ NOT committed yet — 双推 ece + parent via Clash proxy
- ⏳ Next: Codex R2 复审; R2 PASS → start cut-045 (蓝图诚实状态徽章 + 私有化部署包 + 整体验收)

---

## 8. Next Command

```bash
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 add -A
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 commit -m "cut-044R2: spec-driven required-field enforcement + today canonical + closure counts

Per Codex R1 HOLD (docs/demo-platform/CUT_044R1_REVIEW_ROUND2_HOLD.md):
- R2-B1: api.py validation trigger changed from caller-behavior
  ('if period_start or period_end in req.params') to spec-driven
  ('if period_start or period_end in spec.params_schema'); missing
  BOTH period fields now 422 (previously bypassed silently). When
  spec declares a field, it is REQUIRED — caller cannot omit.
- R2-B2: today strict YYYY-MM-DD canonical round-trip at API
  boundary (when caller-supplied, i.e. spec declares today AND
  NOT requires_server_today_anchor). today='not-a-date' now 422.
- R2-B3: cut-044R1-closure.md §1 file count 13 -> 14 (correction
  note added); boundary guarantee wording changed from 'guaranteed
  non-empty' to 'spec-driven validation' (R2-B1 black-box disproved
  the old wording).

Tests: 529 passed (+6 R2 cases), 5 skipped, 3 deselected, 0 regression.
Mutation 3/3 OK, ruff/mypy/lint-imports green, same-origin smoke 10/10
(8 prior + 2 R2-B1/R2-B2)."
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin frontend
```

Codex R2 PASS → 启动 cut-045 (蓝图诚实状态徽章 + 私有化部署包 + 整体验收).

---

## 9. Lessons (apply to cut-045 提交纪律)

> **铁律 (R10 衍生)**: 边界契约的真实来源在 API 层 (api.py), 不是 wrapper
> (rule layer). 任何 rule / wrapper docstring 在描述"上游保证"时, 必须指明
> 真实保证层, 不得把 API 契约错误归因到 wrapper. R2-B1 黑盒 (missing BOTH
> period fields → silent execution) 证伪了 R1 的 "wrapper 收到时 X 必然 Y"
> 措辞 — wrapper 本身对 params 是 0 维度保证.
>
> **Why**: R1 措辞看似 defensive / 安全, 实际掩盖了 API 层 contract 漏洞.
> R2 黑盒揭示: 即使 wrapper 加再多 "OR-fallback to empty", 只要 caller 通过
> spec-bypass route 缺送, 任何 wrapper 都无法 handle. 真正闭环在 spec-driven
> validation block (api.py), 不在 wrapper.
>
> **How to apply**: 任何"上游保证" 措辞模板改为 "{layer} guarantees that,
> by the time this code runs, {invariant}". layer 必须具体 (api boundary /
> loader / materializer), 不允许 "wrapper / rule / upstream" 这种含糊词.
> 配合 grep 自检: `grep -rnE 'wrapper.*guaranteed|rule.*guaranteed' src/`
> 命中应 = 0.

---

**Author**: Claude (cut-044R2 corrective executor)
**Reviewer**: Codex R1 (裁定 R1 HOLD) → cut-044R2 待 Codex R2 复审