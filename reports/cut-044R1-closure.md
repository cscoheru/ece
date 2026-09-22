# cut-044R1 — Closure Report

> **Cycle**: cut-044R1 (corrective cycle for cut-044 Codex R0 HOLD)
> **Date**: 2026-09-22
> **Triggers**: `docs/demo-platform/CUT_044_REVIEW_ROUND1_HOLD.md` (Codex R0 4-blocker verdict)
> **Scope lock**: 只修 R1-B1..R1-B3 + R12-REPORT; 不动 Kernel / 其他 pack / LLM / migrations; 既 512 tests 零退化
> **Status**: ⏳ Code self-check 全绿 → ⏳ 提交 (双推 via Clash proxy) → ⏳ Codex R1 复审 (待复审)

---

## 0. 一句话

cut-044 Codex R0 HOLD 4 阻断全部修正: R1-B1 审计期间改为真参数 (API 边界 strict canonical round-trip + rule audit-period intersection); R1-B2 报告 + PRD + closure memory attribution 全部校正 (R0 PASS → R0 HOLD); R1-B3 same-origin smoke 改为真 reverse proxy (cut-042R2 R2-F3 pattern); R12-REPORT 报告数字 `502 / 512` → `512 passed`. 累计 523 passed (R1 +11) / 5 skipped / 3 deselected / 零退化.

---

## 1. Plan vs Actual — Scope Lock 履行

| 范围锁 | Plan 声称 | Actual | 履行 |
|---|---|---|---|
| `src/ece/context/` engine core | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/demo/spec.py` `registry.py` `loop.py` `mapper.py` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/demo/api.py` | 修改 (R1-B1 validation block, ~50 LOC) | 修改 ~52 LOC | ✅ |
| `src/ece/v0/loop.py` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `migrations/versions/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/{procurement,knowledge}/` | ZERO TOUCH | ZERO TOUCH | ✅ |
| `src/ece/domain_packs/compliance/agent/v0_rules.py` | 修改 (signature + filter, ~40 LOC) | 修改 ~86 LOC (含 docstring 收紧 + module-bottom 注) | ✅ |
| `src/ece/domain_packs/compliance/scenarios/default.yaml` | 修改 (~3 LOC 注释) | 修改 ~8 LOC (整段 audit-period intersection 解释) | ✅ |
| `tests/unit/test_compliance_rule_and_decision.py` | 修改 (_BOUNDARY_MATRIX 8 cases) | 8 cases RED→GREEN | ✅ |
| `tests/integration/test_compliance_boundary.py` | 修改 (4 audit-period 422 cases + 3 truth-table cases) | 4+3 cases RED→GREEN | ✅ |
| `scripts/cut_044_same_origin_smoke.py` | 修改 (升级真 reverse proxy) | 全重写: cut-042R2 R2-F3 stdlib ThreadingHTTPServer pattern, 8 checks | ✅ |
| `reports/cut-044-report.md` | 修改 (R0 HOLD attribution + 报告数字校正 + 新增 §8) | 修改 ~75 LOC | ✅ |
| `reports/cut-044R1-closure.md` | 新增 | 本文件 | ✅ |
| `docs/demo-platform/DEMO_PLATFORM_PRD.md` | 修改 (§8/§11) | §8 cut-044 行 R0 HOLD + §11 trail row R0 HOLD + cut-044R1 trail row | ✅ |
| `.claude/projects/.../domainAgentECE-cut-044-closure.md` | 修改 (attribution) | 全文重写 + R0 HOLD 警告 | ✅ |
| `.claude/projects/.../MEMORY.md` | 修改 (index pointer) | cut-044 entry 加 R0 HOLD 警告 | ✅ |

**总文件数**: 11 修改 (ece sub-repo: 10 modified + 1 new closure report) + 1 修改 (parent PRD) + 2 修改 (memory files) = **14 文件**.

> **R2-B3 校正 (cut-044R2)**: 原始 R1 closure 写 "13 文件" 是算术错误
> (10 modified ece + 3 modified 父仓). 实际: ece sub-repo commit 含 11 files
> (10 modified + 1 new `cut-044R1-closure.md`), 加 parent PRD 1 + memory 2,
> 总数应为 **14**. 本刀 (cut-044R2) 已修正本行.
>
> **R2-B3 边界保证措辞校正**: cut-044R1 closure 早期文档描述 wrapper 边界
> 时使用了 "guaranteed non-empty canonical" 措辞, 后被 R2 黑盒
> (missing BOTH period fields → 200 silent execution) 证伪. cut-044R2 改为
> **spec-driven validation** — 边界保证来自 `spec.params_schema` 是合同来源,
> 而非 caller 行为触发. 详见 cut-044R2-closure.md §2.

---

## 2. Plan vs Actual — User Decisions (R1 锁定)

| # | User 决策 | Plan 实施 | Actual 实施 |
|---|----------|----------|------------|
| 1 | audit period 真参数语义 | API 边界 strict YYYY-MM-DD canonical round-trip + period_start<=period_end 422; rule 按 audit-period **intersection** 筛选 (与 containment 二选一, 选交集 — plan §2.1 Why 写明业务合理性) | ✅ 同上; rule signature 加 `request_period_start` / `request_period_end`; `_evaluate_via_params` wrapper 透传 |
| 2 | 报告 / PRD / memory attribution 全部校正 | 全部从 R0 PASS → R0 HOLD; corrected in cut-044R1; PRD §8 cut-044 行标记, §11 trail row 重写, 新增 cut-044R1 trail row 占位 | ✅ 全部完成 |
| 3 | same-origin smoke 真实现 (而非改名) | 复用 cut-042R2 R2-F3 stdlib ThreadingHTTPServer pattern, 同源 origin `127.0.0.1:8089`, 8 checks (4 旧 + 3 R1-B1 + 1 origin proxy proof) | ✅ 同上 |
| 4 | 报告数字 502/512 → 512 passed | grep 自检 0 命中; 新增 §8 R12-REPORT 校正章节 | ✅ |

---

## 3. Verification (R1 实跑)

### 3.1 binding invariant

| 套件 | R1 计划 | 实跑 | 状态 |
|---|---|---|---|
| `tests/unit/test_compliance_rule_and_decision.py` | 8 unit + 8 boundary parametrize | 12 PASS | ✅ |
| `tests/integration/test_compliance_boundary.py` | 4 truth-table + 4 422 zero-write + 3 R1-B1 truth-table + 4 R1-B1 422 | 15 PASS | ✅ |
| `tests/integration/test_compliance_domain_discovery.py` | 2 | 2 PASS | ✅ |
| **小计** | **20+** | **29** | ✅ |

### 3.2 全量 baseline

```text
pytest -m "not eval and not eval_llm"
→ 523 passed, 5 skipped, 3 deselected
```

cut-044 baseline 512 → cut-044R1 523 (+11 from R1 new cases: 4 unit boundary + 4 integration 422 + 3 integration truth-table). **零退化**.

### 3.3 Quality gates

| Gate | Command | 结果 |
|---|---|---|
| ruff | `ruff check src/ece/v0 src/ece/demo src/ece/domain_packs src/ece/entities src/ece/main.py src/ece/context/update.py src/ece/evidence` | ✅ All checks passed! |
| mypy | `mypy src/ece/v0/loop.py src/ece/demo src/ece/domain_packs/procurement/agent/materializer.py src/ece/domain_packs/procurement/agent/v0_rules.py src/ece/domain_packs/knowledge src/ece/domain_packs/compliance src/ece/entities/ontology_resolver.py src/ece/entities/pipeline.py src/ece/main.py` | ✅ Success: no issues found in 22 source files |
| lint-imports | `lint-imports` | ✅ Contracts: 2 kept, 0 broken |
| mutation runner | `cut_044_mutation_runner.py` | ✅ 3/3 anchors OK (M1 count invert / M2 coverage isdisjoint / M3 force gap_list) |
| same-origin smoke (R1-B3 真实现) | `cut_044_same_origin_smoke.py` | ✅ PASS=8 SKIP=0 FAIL=0 |

### 3.4 attribution grep 自检

```bash
grep -rnE "Codex R0 PASS|R0 PASS|502 / 512|502/512" \
  reports/cut-044-report.md \
  docs/demo-platform/DEMO_PLATFORM_PRD.md \
  .claude/projects/-Users-kjonekong/memory/domainAgentECE-cut-044-closure.md \
  .claude/projects/-Users-kjonekong/memory/MEMORY.md
```

**预期**: 所有命中都在 §8 校正章节 (解释原错误), 状态声明 0 命中.
**实际**: ✅ 全部命中在解释文本 (`§8 R1-B2` / `§8 R12-REPORT` / `MEMORY.md` 警告); 状态行 (Status / Codex verdict / Reviewer) 均已校正.

### 3.5 R1-B1 black-box audit-period boundary matrix (8 cases)

| # | 场景 | 期望 | 实跑 |
|---|---|---|---|
| 1 | canonical full coverage (CTL-001 + period 2026-07-01..2026-09-30) | sufficient / 2 evidence | ✅ |
| 2 | CTL-002 missing finance (count + coverage both fail) | gap_list / 0 evidence (allowlist) | ✅ |
| 3 | CTL-003 missing hr+finance (count ok, coverage fail) | gap_list / 1 evidence (count only) | ✅ |
| 4 | request BEFORE evidence (2026-01-01..2026-06-30) | gap_list / 0 evidence (no intersection) | ✅ |
| 5 | request AFTER evidence (2026-10-01..2026-12-31) | gap_list / 0 evidence (no intersection) | ✅ |
| 6 | partial intersection (2026-08-15..2026-09-15) | sufficient / 2 evidence (all 3 still overlap) | ✅ |
| 7 | full containment (2026-06-01..2026-12-31 ⊇ evidence) | sufficient / 2 evidence | ✅ |
| 8 | today AFTER request_period_end (today reserved-only) | sufficient / 2 evidence (today 不参与过滤) | ✅ |

### 3.6 R1-B1 audit-period 422 zero-write (4 cases)

| # | 场景 | 期望 | 实跑 |
|---|---|---|---|
| 1 | empty period_start | 422 (canonical round-trip) | ✅ |
| 2 | malformed period_start "banana" | 422 (canonical round-trip) | ✅ |
| 3 | reversed period (period_start > period_end) | 422 (reversal check) | ✅ |
| 4 | non-canonical ISO form "20260922" | 422 (canonical round-trip) | ✅ |

所有 422 cases 继续断言 zero-write (pre/post snapshot byte-equal: attrs / REQUIRES_SYSTEM count / evidence_records count).

---

## 4. R1-B1 设计决策 (Why & How)

### 4.1 Audit period 边界语义 = intersection (而非 containment)

```python
in_audit = [
    ev for ev in evidence_set
    if str(ev.get("period_start", "")) <= request_period_end
    and str(ev.get("period_end", "")) >= request_period_start
]
```

**Why 交集而非包含**: 业务语义 — 审计师审视的是 "在审计期间内发生或持续存在的证据"; 任何覆盖到审计期间任一天的证据都应纳入审视. 反例: evidence period = 2026-07-01..2026-09-30, 请求 audit period = 2026-08-01..2026-12-31, 用 "包含" 语义会把这条 evidence 排除, 但审计师明显应该看到它.

**How to apply**: 任何"业务期间 vs 证据期间"的筛选场景 (合规审计、报告期间、复盘窗口), 默认交集语义; 若业务确实要求严格包含, 在 rule 内部加显式 `requested_containment: true` opt-in flag.

### 4.2 today 保留在签名但不参与过滤

```python
def evaluate_rule_R_COMP_AUDIT(
    control, evidence_set,
    request_period_start, request_period_end,
    today,  # RESERVED — 不参与过滤 (signature stability + future staleness checks)
)
```

**Why**: audit period 一旦指定, 证据"是否在审计范围内"由 period intersection 决定; `today` 作为"证据未过期"的隐含语义在审计场景下冗余. 保留 today 在 signature 是为了 API stability (callers already pass it) + future-proof for staleness checks.

### 4.3 API 边界 strict canonical round-trip (mirror R8-B1)

```python
if "period_start" in req.params or "period_end" in req.params:
    for _pfield in ("period_start", "period_end"):
        try:
            _parsed = _date.fromisoformat(_raw)
        except ValueError:
            raise HTTPException(422, detail=...) from None
        if _parsed.isoformat() != _raw:
            raise HTTPException(422, detail=...) from None
    if canonical_period["period_start"] > canonical_period["period_end"]:
        raise HTTPException(422, detail=...) from None
```

**Why**: cut-043R4 R8-B1 已经为 server anchor (`requires_server_today_anchor`) 做了 strict canonical round-trip; 同模式在 audit period 复用 — 拒绝 basic `20260922` / week-date `2026-W38-2` / ordinal `2026-265` 等非 YYYY-MM-DD ISO 8601 形式. fail-fast at API boundary, 不让 rule 处理可能流入业务语言的非规范日期.

---

## 5. R1-B3 设计决策 (Why & How)

### 5.1 Same-origin = 真 reverse proxy (而非改名)

cut-044 R0 脚本 `API_BASE = http://127.0.0.1:8765` 直接连 API, 完全没经 SPA origin; PRD §9 DoD 两阶段部署依赖同源反代链路 (用户自有 nginx 反代 `/api/*`), 真实部署核心从未验证过.

**修复**: 复用 cut-042R2 R2-F3 stdlib `ThreadingHTTPServer` pattern:
- 同源 origin `127.0.0.1:8089` (与 cut-042R2 的 8088 错开, 两个可并行)
- SPA 静态文件 (`demos/spa/index.html`) 由同进程 serve
- `/api/*` 反代到 FastAPI upstream `127.0.0.1:8765`
- 每个 check 用 `urllib.request.urlopen(f"{ORIGIN_BASE}/api/...")` 真实走同源

### 5.2 新增 origin proxy proof check

```python
def _check_origin_index_html() -> tuple[bool, str]:
    """R1-B3 — SPA index.html reachable from the same origin (proxy proof)."""
```

这个 check **不需要 DB**, 验证同源 origin server 真的起来了, 反代链路可见; 失败则说明 reverse proxy 配置本身有问题, 与 upstream 业务无关.

---

## 6. Gate

- ⏳ Code self-check 全绿 (523 passed, mutation 3/3, ruff/mypy/lint-imports green, same-origin smoke 8/8)
- ⏳ NOT committed yet — 双推 ece + parent via Clash proxy
- ⏳ Next: Codex R1 复审; R1 PASS → start cut-045 (蓝图诚实状态徽章 + 私有化部署包 + 整体验收)

---

## 7. Next Command

```bash
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 add -A
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 commit -m "cut-044R1: fix audit period semantics + attribution + same-origin smoke + report number

Per Codex R0 HOLD (docs/demo-platform/CUT_044_REVIEW_ROUND1_HOLD.md):
- R1-B1: rule signature adds request_period_start / request_period_end;
  filter is audit-period INTERSECTION (not today coverage); api.py strict
  YYYY-MM-DD canonical round-trip + period_start<=period_end 422 (mirror
  cut-043R4 R8-B1). today reserved in signature for future staleness.
- R1-B2: report + PRD + closure memory attribution corrected (R0 PASS ->
  R0 HOLD); new PRD §11 cut-044R1 trail row placeholder.
- R1-B3: cut_044_same_origin_smoke.py now uses cut-042R2 R2-F3 stdlib
  ThreadingHTTPServer reverse proxy (not direct API); 8 checks (4 original
  + 3 R1-B1 audit-period boundary + 1 origin proxy proof).
- R12-REPORT: report number 502/512 -> 512 passed.

Self-check: 523 passed (+11), 5 skipped, 3 deselected, 0 regression.
Mutation 3/3 OK, ruff/mypy/lint-imports green, same-origin smoke 8/8."
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin frontend
cd .. && git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 add docs/demo-platform/DEMO_PLATFORM_PRD.md
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 commit -m "cut-044R1: PRD sync (R0 HOLD attribution + §11 cut-044R1 trail row)"
git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin frontend
```

Codex R1 PASS → 启动 cut-045 (蓝图诚实状态徽章 + 私有化部署包 + 整体验收).

---

## 8. Lessons (apply to cut-045 提交纪律)

> **铁律 (R9 衍生)**: 自称 PASS 是审计事故. cc 提交前**只写 "已 commit/push, 待 Codex 复审"**; 真实裁定永远留给 Codex 第一行写.
> 若 cc 内部 run 全绿, 只能写 "self-check: 0F/0S 全绿", 不得冒充审验方结论.
>
> **Why**: Codex R1 抓出的 4 项阻断里, R1-B2 (虚假 PASS) 是最容易被忽视的 discipline 漏洞. 业务能力可能全绿, 但归属不诚实 = 看不见的回归风险 (审验被绕过后, R1-B1 这种业务缺陷也"看起来 PASS").
>
> **How to apply**: 任何 closure 文档 / report / PRD 状态行, **审验方结论必须空着等 Codex 写**, cc 只填自检数据 (pytest 行号 / ruff 行号 / mypy 行号 / lint-imports 行号 / mutation 行号). 完整 5 项 self-check 行齐了, 才算 "待复审", 不是 "PASS".

---

**Author**: Claude (cut-044R1 corrective executor)
**Reviewer**: Codex R0 (裁定 R0 HOLD) → cut-044R1 待 Codex R1 复审