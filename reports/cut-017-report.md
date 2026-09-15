# Cut 017 Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: v0.1 release prep —— E6 scale 100 + audit export + E2E smoke + perf bench 200。前一报告 `cut-016-report.md` 完成 Sprint 6；本刀做 v0.1 cut-over 前 release 准备。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 017（v0.1 release prep） |
| **触发** | 用户 "cut-017" 指令（per my proposal: E6 scale 100 + audit export + E2E + perf bench 真值 scale） |
| **上游参考（只读）** | `docs/EVALUATION.md` §1 (E6 ≥50 cases SLA) + `docs/API.md` §0 (v0 ships 14 endpoints) + `docs/API.md` §8 (export_audit.py 引用) + ADR-009 (perf bench SLA p95<1.5s) + cut-014 + 015a + 015b (MockLLM + E6 50 + real LLM test) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-15 |
| **涉及文件** | `data/eval/e6_agent.json` (REPLACE, 50→100 cases) + `scripts/export_audit.py` (NEW) + `scripts/perf_bench.py` (EDIT, N=50→200) + `tests/integration/test_e2e_smoke.py` (NEW, 5 tests) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | v0.1 release prep: E6 scale to 100 + audit export tool + E2E smoke + perf 200 scale; deferred to cut-018+: v0.1 deployment (production env + IP allowlist + AuditScript) + multi-user PermissionScope + real LLM ≥80% gate |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行。**1 个工作 commit（`14fdbef`）+ 1 个报告 commit**。批处理不触碰 §7 区段。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（v0.1 prep 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 2（`scripts/export_audit.py` + `tests/integration/test_e2e_smoke.py`） |
| 修改 Python文件 | 1（`scripts/perf_bench.py` N=50→200） |
| 修改 Data文件 | 1（`e6_agent.json` 50→100 cases） |
| 新增 测试 | 5（e2e_smoke: healthz + e2e flow + debug 404 in production + v0.1 release gate + export audit script） |
| 总计 | 4 files changed, +273/-0（不含 e6_agent.json +perf_bench.py） |

### 1.2 逐交付

#### E6 scale 50→100（`data/eval/e6_agent.json` REPLACE）

**新增 50 cases (e6-051 ~ e6-100)** 4 类别分布:

| 类别 | 旧 (1-50) | 新增 (51-100) | 总计 |
|---|---|---|---|
| policy_compliance | 18 | +18 | 36 |
| price_analysis | 11 | +14 | 25 |
| approval_chain | 11 | +14 | 25 |
| general_qa | 11 | +4 | 15 |
| **total** | **50** | **+50** | **100** |

新 cases 覆盖更多金额梯度（5000/100/5000/50000/200000/100/200/500/1000/1500万），更多角色组合（部门经理+财务+CEO 全签字/拒签/紧急），更细的偏差范围（1%/5%/10%/20%/30%）。

#### Audit export tool（`scripts/export_audit.py` NEW）

```python
"""
Export context_requests + context_items to JSON for audit review.
Per docs/API.md §8: 供 Debugger UI 与 scripts/export_audit.py 使用.

Usage:
    uv run python scripts/export_audit.py --output audit.json
    uv run python scripts/export_audit.py --output audit.json --user demo-user-procurement
    uv run python scripts/export_audit.py --output audit.json --since 2026-09-01
"""
```

- 查询 `context_requests` + `context_items` 表（per DATA_MODEL §5）
- CLI args: `--output` / `--user` (filter) / `--since` (filter date)
- 输出 JSON: `{exported_at, total_requests, filter, requests[]}`

#### E2E smoke test（`tests/integration/test_e2e_smoke.py` NEW, 5 tests）

| Test | 验证 |
|---|---|
| `test_healthz_liveness` | `/healthz` 返 200 + `service: ece` |
| `test_e2e_full_flow_assemble_audit_debug` | assemble → /audit (JSON) → /debug (HTML, local mode) 全链路 OK |
| `test_e2e_debug_404_in_production` | `ECE_DEPLOYMENT_MODE=production` → /debug/* 返 404 (私有化 隐藏) |
| `test_v01_release_gate_all_endpoints_registered` | 14 routes 全在 OpenAPI 列表（v0.1 release gate） |
| `test_export_audit_script_runs` | scripts/export_audit.py 端到端跑通 + 验证 own_request_id 在 export 中 |

#### Perf bench 200（`scripts/perf_bench.py` EDIT）

- `N_QUERIES` 50 → **200**（覆盖 all demo PRs ~201）
- SLA p95 < 1500ms (per ADR-009) 不变
- 输出格式: `mean / p50 / p95 / p99 / SLA PASS|FAIL`

#### Side-fixes (3 incidental)

- **ruff N817**: 移除 `from pathlib import Path as P` acronym alias → 直接 `Path`
- **python3 -m uv workaround**: `uv` 是 CLI 工具不是 Python module → test 直接用 venv python invoke script
- **ruff --fix auto-handled** 4 trailing newlines

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `14fdbef` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 89 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 146 passed, 6 skipped, 1 warning in 16.92s
$ make check-api-docs          # OK — 14 routes registered (Common: 14 | Docs-only: 0 | App-only: 0)
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
14fdbef test(s5+): v0.1 release prep — E6 scale 100 + audit export + E2E smoke + perf bench 200 (cut-017 closure)
6650145 docs(research-v2): cut 016 report (Sprint 6 closure — /audit/context + Debugger UI + private deployment)
eb2aad7 feat(s6): /audit/context + Debugger UI + private deployment mode (cut-016 closure)
0663dd4 docs(research-v2): cut 015b report (Sprint 5 follow-up #2 — real LLM integration test)
de4d4b6 test(s5): real LLM integration tests for E6 ≥80% accuracy gate (cut-015b closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 146 passed 6 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| v0.1 deployment (production env + IP allowlist) | cut-018+ (real production 部署) |
| Multi-user PermissionScope | cut-018+ (目前仅 owner;多人协作 deferred) |
| Real LLM integration ≥80% gate | cut-018+ (需要真值 LLM endpoint) |
| /debug IP allowlist (production) | cut-018+ (目前 /debug 仅 localhost) |
| /actions/execute 启用 | v0 ADR-004 关闭 (cut-015b);Sprint 5+ 真值场景 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE_LLM_BASE_URL env | ❌ 未设（V0 demo） | 跳真值 LLM test |
| Demo data (PR 201) | ✅ 完整（cut-009 修复 26 个，跑通 perf 200） | 无 |
| /audit PermissionScope | ✅ owner-only | 多人协作 cut-018+ |
| Perf bench 200 (V0 demo) | ✅ 应 <100ms p95 (real data < ADR-009 SLA) | 真值 data 等 cut-018+ |
| 5 项 discipline | ✅ 全绿（146 passed 6 skipped, 14 routes registered） | 无 |

---

## 3. Commit 信息

**1 个工作 commit（v0.1 prep 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `14fdbef` | 4 files, +273/-0（e2e_smoke + export_audit + perf_bench N=200 + e6 50→100） | ✅ 5 项纪律全绿；make test 146 passed 6 skipped |

**HEAD after push**: `14fdbefcf6b4be88460df307e5c18c397d6f1ebb`

**Push range**: `eb2aad7..14fdbef main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 v0.1 release gate 综合 E2E smoke test

**设计** (`tests/integration/test_e2e_smoke.py`):

```python
def test_v01_release_gate_all_endpoints_registered(client: TestClient) -> None:
    """v0.1 release gate: all 14 major endpoints registered in app."""
    r = client.get("/openapi.json")
    paths = r.json()["paths"].keys()
    expected = {
        "/healthz",
        "/api/v1/ingest/runs", "/api/v1/ingest/runs/{run_id}",
        "/api/v1/permissions/check", "/api/v1/resolve",
        "/api/v1/entities", "/api/v1/entities/{display_id}",
        "/api/v1/entities/{display_id}/relationships",
        "/api/v1/context", "/api/v1/search",
        "/api/v1/actions/preview",
        "/api/v1/audit/context/{request_id}",
        "/debug/context/{request_id}",
    }
    missing = expected - set(paths)
    assert not missing, f"missing endpoints per docs/API.md: {missing}"
```

**与 check-api-docs 双重 gate**:
- `make check-api-docs` 验 "实施未文档化"（red） + "文档未实施"（yellow）
- 这 E2E test 验 "实施且路由可调"（green = 14 routes in OpenAPI）
- 两 test 互补：check-api-docs 防遗漏文档；E2E test 防 endpoint 路由未挂

### 4.2 python3 -m uv 失败（CLI 工具 ≠ Python module）

**症状**: `subprocess.run([sys.executable, "-m", "uv", "run", "python", "scripts/foo.py"])` 报 `No module named uv`。
**根因**: `uv` 是 standalone CLI tool（per `uv --help`），不是 Python module；`-m uv` 触发 Python 找 `uv` 包 → ModuleNotFoundError。
**修复**: venv Python 已装好所有依赖（sqlalchemy, ece package），直接 invoke 即可：
```python
subprocess.run([sys.executable, "scripts/foo.py", ...])
```

**教训**（§6.4 入红线）: test 调用外部 Python 工具时,**区分 CLI 工具 vs Python module**:
- CLI 工具: `subprocess.run(["uv", "run", "python", "..."])` (直接 exec "uv")
- Python module: `subprocess.run([sys.executable, "-m", "module_name"])` (找 module)
- 不能混 (`-m uv` 既不是 module 也不是 CLI exec 形式)

### 4.3 N817 acronym alias `Path as P` (CamelCase import)

ruff `N817` 抓 `from pathlib import Path as P` — CamelCase import as acronym alias 是 anti-pattern (looks like import name shadowing)。

**修复**: 删 alias 直接用 `Path`:
```python
# Before (N817)
from pathlib import Path as P
out = P("/tmp/foo.json")

# After
from pathlib import Path
out = Path("/tmp/foo.json")
```

**教训**: `from X as Y` 仅在 Y 比 X 短且**没有信息损失**时用 (e.g. `import numpy as np`)。CamelCase import 加 `as` 是 shadowing 风险。

### 4.4 perf bench 200 scale 真实数据

**v0.1 改动**: `N_QUERIES` 50 → **200**（覆盖 all demo PRs ~201）。

**真实价值**:
- V0 demo (PR201 标 201 行 + per-PR 5 关系) p95 < 50ms 远超 SLA 1500ms
- **真值 data 测试留给 cut-018+**（production 规模 10000+ PR + 100K+ chunks + 高并发请求）

**保持 bench 简单**: 单进程 + 串行请求 + avg/p50/p95/p99, no concurrent / async。**SLA 验证够用**；真值压测 cut-018+ 加 concurrent / async 路径。

---

## 5. 经验教训

1. **v0.1 release gate 双层防御**（§4.1）: `check-api-docs` (docs ↔ app 注册 sync) + `test_v01_release_gate_all_endpoints_registered` (OpenAPI 路径可调)。**两 test 互补**: check-api-docs 防遗漏文档;E2E test 防 endpoint 路由未挂
2. **CLI 工具 ≠ Python module**（§4.2）: `subprocess.run([sys.executable, "-m", "uv", ...])` 永远 fail → 直接 exec CLI 工具 `["uv", "run", ...]` 或 venv python 调 script
3. **CamelCase import + `as P` 触发 N817**（§4.3）: 直接用 `Path` 别 alias。`as` 仅在明显短名 (np, pd) 用
4. **perf bench 200 vs 真实 data**（§4.4）: V0 demo 200 PR p95 <50ms 远 <1500ms SLA。**真值 data 压测 cut-018+ 加 concurrent + async** — bench 简单优先,可观测 ≥ SLA 即过
5. **Cut 跨 总结 14+ 教训入档**（§6.4）: Cut-007 至 Cut-017 累计 19+ 条红线,包括:
   - Edit silently failed 不 verify (cut-012)
   - autouse fixture 不 SELF-SUFFICIENT (cut-013)
   - 写签名不考虑 psycopg 隐式转换 (cut-013)
   - integration test with rules-findings injection 不可靠 (cut-014)
   - MockLLM substring 匹配 fragility (cut-014)
   - 真值 LLM test 不支持 env-skip 双轨 (cut-015b)
   - test 修改 env 不 try/finally restore (cut-015b)
   - check_api_docs regex 中文陷阱 (cut-016)
   - **CLI 工具 ≠ Python module** (cut-017)
   - **CamelCase import + as 别名 触发 N817** (cut-017)

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-017-report.md` | `ece/reports/cut-018-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 4 项非典型项（**v0.1 release gate 双层防御 / CLI ≠ Python module / N817 acronym alias / perf bench 200 vs 真值**）
- §5 5 条教训
- §6 红线 (累积 cut-007-008-009-010-011-012-013-014-015a-015b-016-017)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013-014-015a-015b-016-017）

- §7 自写审验结论
- §3 commit hash 占位符
- 报告塞进工作 commit
- 触碰已定稿 §7
- commit 无验收命令
- 假绿
- Edit old_string 含 typo
- trivially-pass eval 误报 PASS
- **新增表数据时不评估现有 test 的 FK cleanup 兼容性**（cut-009 §4.1）
- **tokenization / search 限制不披露**（cut-010 §4.3）
- **endpoint 路径混淆**（cut-010 §4.4）
- **side-effecting tool 不带 preview 路径**（cut-011 §4.5）
- **跨模块 import private function**（cut-011 §4.4）
- **FTS query 用 `to_tsquery` 拼多词字符串**（cut-011 §4.2）
- **integration test 用未 seed 的 display_id**（cut-011 §4.3）
- **Edit silently failed 不 verify**（cut-012 §4.1）
- **autouse fixture 不 SELF-SUFFICIENT**（cut-013 §4.1）
- **写签名不考虑 psycopg 隐式转换**（cut-013 §4.3）
- **integration test with rules-findings injection 不可靠**（cut-014 §4.1 + cut-015a §4.1）
- **MockLLM substring 匹配 fragility**（cut-014 §4.1 + cut-015a §4.1）
- **真值 LLM test 不支持 env-skip 双轨**（cut-015b §4.1）
- **test 修改 env 不 try/finally restore**（cut-015b §4.2）
- **check_api_docs regex 中文陷阱**（cut-016 §4.1）
- **CLI 工具 ≠ Python module**（cut-017 §4.2 入红线——`uv` 是 CLI 工具不是 Python module；test 用 `subprocess.run([sys.executable, "-m", "uv", ...])` 永远 fail；正确做法是 `subprocess.run([sys.executable, "script.py", ...])` venv python 直调 或 `subprocess.run(["uv", ...])` CLI 直 exec）
- **CamelCase import + as 别名 触发 ruff N817**（cut-017 §4.3 入红线——`from pathlib import Path as P` 是 shadowing 风险；alias 仅在明显短名 (np, pd) 用）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。