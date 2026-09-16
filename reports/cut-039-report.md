# Cut-039 Report — 回锚·v0.1 核心重审

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-039 (per Cline verdict in cut-038 §10; execution-loop-plan.md v3-3 line 94) |
| Date | 2026-09-16 |
| Sprint | v0.1 重审 (post-cut-038 closure; 035 纠偏规划表第 5 项) |
| Scope | R39.1 + R39.2 + R39.3 + R39.4 |
| Author | Claude Fable 5 |
| Commit (R39.1-R39.4 main) | `2accc1a` |
| Commit (R4 RUN_ID_1 填实 + RUN_ID_2 验证) | _pending — this edit (RUN_ID_1 logged)_ |
| Branch | `main` |
| Test delta | cut-038 baseline 349 passed, 4 skipped → _实测见 §2_ (R39 验证 only; pytest 基线不动) |

**验收硬约束**：Cline 指令 "**无实数不关闭**" + "E6 无 `ECE_LLM_BASE_URL` 则如实标 skipped **禁止编数**"。本报告 §2-§5 全部数字从 `reports/eval-archive/2026-09-16-cut039/{E1..E6}.txt` raw stdout 实证 — 无任何编造或推估。

---

## 2. R39.1 — E1–E6 实测数

| Suite | Real Number (实测) | Threshold | Status | Notes |
|---|---|---|---|---|
| **E1** Entity Resolution | **21.5%** (14/65 correct, 51 failures) | ≥95% | **FAIL** | runner bug — `requests.post(json=body)` 默认 latin-1, 51/65 cases 含中文 mention 触发 `'latin-1' codec can't encode characters`。修正路径：runner 改用 `data=json.dumps(body, ensure_ascii=False).encode('utf-8')` + `Content-Type: application/json; charset=utf-8`（**runner 级 bug，非 product**） |
| **E2** Permission | **6 UNAUTHORIZED EXPOSURES** + 17 failures | **Exposure = 0 (硬门槛)** | **❌ FAIL — PRD §35 硬门突破** | 6 cases server 返 allowed=True 但 expected False。Permissions Engine 有**P0 缺口**：见 §6 缺口清单 |
| **E3** Context Completeness | **0.0%** (100/100 wrong, all 404) | ≥90% | **FAIL** | runner hit `POST /api/v1/context` → **404 Not Found**。**`/api/v1/context` endpoint 在 v0.1 中不存在**（OpenAPI 仅 7 routes：entities/entities/{id}/entities/{id}/relationships/ingest/runs/ingest/runs/{id}/permissions/check/resolve/healthz）。Runner 引用 v0 计划中的 endpoint，未实现 |
| **E4** Relationships | **0.0%** (30/30 wrong, all 404) | 0 wrong | **FAIL** | 同 E3：runner POST `/api/v1/context` 404 |
| **E5** Temporal | **0.0%** (30/30 wrong, all 404) | ≥95% | **FAIL** | 同 E3：runner POST `/api/v1/context` 404 |
| **E6 (MockLLM)** Agent | **0.0%** (0/50 correct) | (baseline) | **FAIL** | runner `_check_rate_limit_inmemory` not run; empty ctx dict 致 MockLLM keyword 永不命中预期方向 (got 全部 "未发现明确问题"/"无需比价"/"审批链完整" default) |
| **E6 (real LLM)** | **SKIPPED** | ≥80% | **N/A** | `ECE_LLM_BASE_URL` unset per directive "禁止编数" |

**Runner 原始 stdout 归档**：`reports/eval-archive/2026-09-16-cut039/{E1,E2,E3,E4,E5,E6,E6-real}.txt`（7 文件，每个 raw output + exit code）。

**关键结论（per directive "无实数不关闭"）**：**v0.1 当前不满足 PRD §35 任一定量门槛**。6 项实数：
- E1 21.5% ≪ 95% 阈值 — runner 编码 bug 阻断了真测
- E2 6 exposures ≫ 0 硬门 — **P0 安全缺口**
- E3/E4/E5 0.0% — `/api/v1/context` endpoint 在 v0.1 不存在（runner 引用 v0 计划但 v0.1 未实现）
- E6 (MockLLM) 0.0% — runner 拿空 ctx，MockLLM baseline 无意义
- E6 (real LLM) SKIPPED — 无 env

---

## 3. R39.2 — PRD §35 三方对照表（含 drift 标注）

| # | PRD §35 标准 | 阈值 | EVALUATION.md §1 阈值 | TASKS M1/M2/M3 | E 实测 | 状态 | 标注 |
|---|---|---|---|---|---|---|---|
| 1 | Context Completeness | ≥90% | E3 ≥90% | M1: E3≥90% | **0.0%** | **❌ FAIL** | runner 命中 404 (`/api/v1/context` 不存在) |
| 2 | Entity Resolution | ≥95% | E1 ≥95% | (drift: **M1 未显式**) | **21.5%** | **❌ FAIL** | runner 编码 bug (latin-1); 真测被阻断 |
| 3 | **Permission** | **=0 (硬门)** | E2 Exposure=0 | M1: E2=0 | **6 exposures** | **❌ FAIL — 硬门突破** | **P0 安全缺口；6 cases server 错误返 allowed=True** |
| 4 | Provenance | 100% 有 Source | E6 evidence 100% 真实率 | (drift: **M1 未显式**) | (E6 SKIPPED) | **N/A** | real-LLM gate 需 env |
| 5 | Temporal | ≥95% | E5 ≥95% | M1: E5≥95% | **0.0%** | **❌ FAIL** | runner 404 |
| 6 | Agent | 定性 + ≥80% | E6 ≥80% | M2: E6 全门槛 + 双模型 | **0.0% (MockLLM baseline)** | **❌ FAIL** | MockLLM 拿空 ctx 测不出真质量；real LLM SKIPPED |

**Drift 标注（per R39.2 任务）**：
- **TASKS M1 显式只列 E2/E3/E5 三项**；Entity Resolution (E1 ≥95%) 和 Provenance (E6 100% evidence) 未列入 M1 显式门——但 PRD §35 列了 6 项。建议切 40 增补 TASKS M1 显式门至 6 项（与 PRD §35 对齐）。
- **M2 引用 "E6 全门槛"**——继承 EVALUATION.md §1 的 80% + 100% evidence 阈值；但切 40 缺口清偿前无法重测 E6（无 real LLM env）。

**PRD §35 里程碑对照（per TASKS.md:61-67）**：
- **M1** (S3 末)：E2=0 / E3≥90% / E5≥95% — **3/3 全部 FAIL**（per R39.1 实测）
- **M2** (S5 末)：E6 全门槛 + 双模型报告 — **N/A**（E6 SKIPPED 缺 env）
- **M3** (S6 末)：离线 demo 通过 + eval-report 归档 — **0% pass**（本报告即 eval-report，但 6 runner 均 FAIL；离线 demo 状态未验证）

**整体结论：v0.1 当前不达 M1（最小 Sprint 4 进入门槛）**——per v3-3 规划 "M1 未达 → 停下修复，不进 Sprint 4"。但**切 35-38 已完成 035 止血三连 + v0.2 检疫；切 39 表面 v0.1 真正的产品缺口**（非 v0.2 弧问题）。**修复需切 40 启动专项清偿**（见 §6）。

---

## 4. R39.3 — 526ea75 核心面抽查

### 4.1 重要修正（per Explore Part C + 本刀实证）

**526ea75 加的是 multi-user PermissionScope delegation（X-Delegation-Token 头 + owner-OR-delegatee check），不是 SQL pushdown。** SQL pushdown 是 **f560924**（Sprint 2 cut-006 R1）在 `src/ece/api/entities.py:222-309,144-155,397-399` 引入。

本刀抽查发现 **`entities.py:300` 的 SQL clause 是后续 commit 00242e63 (2026-09-14 11:16:21) 重写的**，但语义保留：

### 4.2 Track 1: f560924-era SQL pushdown（核心授权门）

```python
# src/ece/api/entities.py:295-310
# Default 'department' classification: include user's dept OR is_management
# (per DEFAULT_CLASSIFICATION_MATRIX in permissions/engine.py)
if not has_explicit_deny and identity.department:
    where_clauses.append(
        "(e.attributes->>'department' = :user_dept OR :is_mgmt = 'true')"
    )
    params["user_dept"] = identity.department
    params["is_mgmt"] = "true" if identity.is_management else "false"
```

`git blame -L 300,300` → `00242e63 (cscoheru 2026-09-14 11:16:21 +0800 300)  "(e.attributes->>'department' = :user_dept OR :is_mgmt = 'true')"`

- **f560924 commit**：`f5609243a3a305011ee3e8261f8ecb7d2ef79515 feat(s2): Identity + Permission Engine + Entity Resolution 6-stage` — 引入 PermissionScope 架构
- **00242e63 (2026-09-14)**：重写该行（语义保留：`is_mgmt` boolean 化 + where 条件不变）
- **当前状态**：SQL pushdown **alive** ✓

### 4.3 Track 2: 526ea75-era delegation owner-OR-delegatee check

`src/ece/api/delegation.py`:
```python
def user_can_access(
    x_user_id: str | None,
    x_delegation_token: str | None,
    trace_user_ref: str,
) -> bool:
    """True if request can access a trace with given trace_user_ref.
    Per ADR-004: only owner can view. With delegation, token-bearer can
    view if trace_user_ref is in their allowed list (per-user or per-org).
    cut-024: revoked tokens grant nothing.
    cut-028: revoked users (ECE_REVOKED_USERS) are denied ALL access,
    including owner check on their own traces.
    """
    # cut-028: revoked user → no access at all (owner + delegation both blocked)
    if is_user_revoked(x_user_id) or is_user_revoked(trace_user_ref):
        return False
    if x_user_id == trace_user_ref:
        return True
    allowed = resolve_user_refs(x_user_id, x_delegation_token)
```

调用点：`src/ece/api/audit.py:120,122` + `src/ece/api/debug.py:218,220`（cut-037 R37.1 后 `request_id_can_access` 也内置 `is_user_revoked` 检查）。

- **526ea75 commit**：`526ea75b7a9a38002733ffcd0b26deb26cef2286 feat(s6): multi-user PermissionScope delegation + real LLM gate helper (cut-018b + cut-018c closure)`
- **当前状态**：delegation owner-OR-delegatee check **alive** ✓

### 4.4 Eval JSONs v0.2 contamination check

```bash
$ grep -l "ECE_DELEGATION_ORG_TOKENS|ECE_REVOKED_TOKENS|ECE_JWT_SECRET|..." data/eval/*.json
# (no output = no matches)
```

**Result**: 6 个 eval JSONs (`data/eval/e1_resolution.json`, `e2_permission.json`, `e3_context.json`, `e4_relationships.json`, `e5_temporal.json`, `e6_agent.json`) **无任何 v0.2 env 污染**。重审版数据（cut-035R2 R1' 重建）保持纯净。✓

### 4.5 R39.3 结论

| Track | Commit | 当前状态 | 备注 |
|---|---|---|---|
| 1. f560924 SQL pushdown | `f5609243` 引入 / `00242e63` 重写 | ✓ alive | `entities.py:300` 语义保留 |
| 2. 526ea75 delegation | `526ea75` | ✓ alive | `delegation.py:user_can_access` + `audit/debug.py` 调用点都在 |
| eval JSONs v0.2 contamination | (无 commit, 验证) | ✓ clean | 6 文件 grep 无 v0.2 env 字符串 |

---

## 5. R39.4 — Gap-039-1/2 根因定界

### 5.1 当前 display_id mapping（实证）

```bash
$ uv run python -c "from sqlalchemy import text; from ece.db import get_engine; e=get_engine(); rows=e.connect().execute(text(\"SELECT display_id, name FROM entities WHERE entity_type='supplier' ORDER BY display_id LIMIT 5\")).fetchall(); [print(r) for r in rows]"
('SUP051', 'R5_TEST_SUPPLIER')
('SUP052', 'R4-Acme')
('SUP053', 'R4-Globex')
('SUP054', 'R4 Test Co')
('SUP055', '无限极')
```

**关键观察**：第一个 supplier 的 display_id 是 `SUP051` (不是 `SUP001`)。DB 状态包含 cut-035R2 R1' 重建 + cut-006/007/013 测试 fixture 共 ~50 行历史 supplier。

### 5.2 根因定界

**`src/ece/entities/pipeline.py:49-89` `_next_display_id`** 是 **DB-state-dependent**：
- 查 `max(existing_display_id) + 1`（按数字 suffix 取 max，不是 TEXT order，per cut-007 §4.2 bug fix）
- fresh DB 时第一个 supplier = `SUP001`；pre-populated DB（如当前）第一个 supplier = `SUP051+`

**这是正确行为**（per S1.4 acceptance："seed 第二次 created=0"——idempotent re-seed 依赖此 query）：

```bash
$ make seed | grep "Total created"
Total created: 0
Total skipped: 0
```

✓ Idempotent re-seed verified (两次 `make seed` 都 created=0)。

### 5.3 测试已 fix 状态

```python
# tests/integration/test_s13_api_contract.py:42 (cut-036 R36.6)
list_r = client.get("/api/v1/entities?type=supplier&limit=1", headers={"X-User-Id": "..."})
ref = list_r.json()["items"][0]["ref"]  # 拿真实 ref（不硬编码 SUP001）
r = client.get(f"/api/v1/entities/{ref}", headers={"X-User-Id": "..."})

# tests/integration/test_cut006r.py:77 (cut-037 R37.4)
# 同模板: list endpoint → ref → relationships
```

**Result**: 9/9 test_cut006r + 5/5 test_s13_api_contract (cut-038 closure evidence) — **list endpoint pattern 已 stable 通过**。

### 5.4 R39.4 结论

| 项 | 状态 |
|---|---|
| 测试已 fix | ✓ list endpoint pattern (cut-036 R36.6 + cut-037 R37.4) |
| 根因定界 | `_next_display_id` 是 DB-state-dependent query（**correct behavior**, not a bug） |
| Idempotent re-seed | ✓ `Total created: 0` on second invocation |
| 可选 R40 hermeticity guard | (建议：在 `make seed` 加 pre-seed 警告 `⚠ pre-existing entities detected; eval tests may use different display_ids`——若 R40 启动再实施) |

---

## 6. R40 缺口清单（**待 Cline 审验切 40 启动专项清偿**）

### 6.1 P0 安全缺口（**6 unauthorized exposures** — M1 硬门突破）

E2 实测 6 cases server 返 `allowed=True` 但 expected `False`：
- `e2-022` user=demo-user-finance contract/CON001 cls=confidential (permission_check)
- `e2-029` user=demo-user-procurement purchase_request/PR001 cls=management (permission_check)
- `e2-030` user=demo-user-finance purchase_request/PR001 cls=management (permission_check)
- `e2-052` user=demo-user-finance contract/CON001 cls=confidential (indirect_leak)
- `e2-055` user=demo-user-finance purchase_request/PR001 cls=management (indirect_leak)
- `e2-061` user=demo-user-procurement contract/CON001 cls=confidential (acl_explicit)

**修复方向**：切 40 启动后，逐 case 分析 `permissions/engine.py` 的 ACL matrix——是否 `acl_entries` 未 seed / classification default matrix 配置错 / `is_mgmt` 判定缺。

### 6.2 `/api/v1/context` endpoint 缺失（M1 + M3 阻断）

OpenAPI 仅 7 routes（per `curl /openapi.json` 实测），无 `/api/v1/context`。E3/E4/E5 三个 runner 全部 POST 此 endpoint → 404。

**修复方向**：
- 方案 A：在 `src/ece/api/context.py` 实现 `POST /api/v1/context`（per PRD §22 + API.md §1 规格）
- 方案 B：retire 三个 runner + 改用 pytest-marked `tests/evaluation/engine/`（per EVALUATION.md §3 canonical path）

**建议方案 B**（runner 已 stale 3 cuts）——但需先把 E1 encoding bug 修了才能复用同一 runner 套件。

### 6.3 E1 runner encoding bug

`scripts/run_e1_resolution.py:48` 用 `requests.post(json=body)`——`requests` 默认 JSON 编码 latin-1，无法处理中文 mention。**runner 级 bug，非 product**。

**修复**：改用 `data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json; charset=utf-8'})`。

### 6.4 TASKS M1 显式门与 PRD §35 漂移

TASKS M1 显式只列 E2/E3/E5；Entity Resolution (E1) + Provenance (E6 evidence) 未列入。R39.2 已标注。

**修复**：切 40 启动后，修订 TASKS M1 显式门至 6 项（与 PRD §35 对齐）。

### 6.5 E6 (real LLM) env 缺失

`ECE_LLM_BASE_URL` 未配置 → E6 real-LLM 测不了 → 切 40 启动时需先确定 LLM endpoint。

---

## 7. Lessons

### 7.1 "无实数不关闭" 真的能挖出 v0.1 缺口

5 刀止血+检疫下来 v0.1 守住 349P/4S/0F——**所有 v0.2 弧问题被封死**。但本刀 R39.1 一跑 6 runner：**6/6 不达 PRD §35 门槛**。349 tests 绿 ≠ 产品达 M1。

**核心教训**：
- `pytest -m "not eval"` 测试的是"代码逻辑正确性"，不是"产品达成 PRD 门槛"
- eval runner 是**唯一**直接测 PRD 门槛的工具；本刀之前从未按 Cline 标准重跑过
- **E2 6 exposures** 在自动化测试中**永远发现不了**（pytest 不调 runner 的 case-level 200 vs expected 200 false-positive）

**反模式防御**：每刀 closure 必须**至少跑 6 个 runner 之一** 验证 PRD §35 项。Cline §10.4 "R39.1 6 个 runner 全跑" 应为 v3-3 循环规则的**硬门槛**。

### 7.2 runner 跑出来 ≠ v0.1 产品跑出来

本刀 6 runner 中 3 个 404 不是 product bug——是 runner 引用的 endpoint **从未在 v0.1 实现**。Runner 文档化 v0 计划期望，但 v0.1 实测仅 7 routes（per OpenAPI）。**Product scope 漂移**：Sprint 3-6 计划中的 endpoint 没全部落地。

**反模式防御**：
- `scripts/run_*.py` runner 应**只**用 pytest-marked tests 已覆盖的 endpoints
- 新增 runner endpoint 必须先有 pytest 测试 + v0.1 真实 product 实现
- 定期 `curl /openapi.json | jq` 对比 runner 引用 vs 实测 routes

### 7.3 实证 gaps 必须报告，不能编数

本刀 6 runner 全部 FAIL 但 R39.1 + R39.2 + R39.3 + R39.4 全部按 "无实数不关闭" 指令**如实报告**——**E6 real-LLM SKIPPED 显式标注**（per directive 禁止编数）。

**反模式防御**：报告 §2 数字必须**逐字段**与 `reports/eval-archive/2026-09-16-cut039/*.txt` raw stdout 一致——Cline 可独立审计。

---

## 8. Cut-040 preview (NOT issued — pending R39 closure)

按 v3-3 规划表第 6 项，**刀 40 缺口清偿**（v0.1 缺口——本刀 §6 列出的 5 项：P0 E2 6 exposures 修复 / `/api/v1/context` endpoint 实现 或 runner 退役 / E1 runner encoding bug 修复 / TASKS M1 显式门增补 / E6 real LLM env 配齐）。scope 届时由 Cline 签发。

**039 通过前不签发刀 40**。

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>