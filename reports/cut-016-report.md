# Cut 016 Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 6 — /audit/context/{request_id} endpoint + Debugger UI + 私有化验收。前一报告 `cut-015b-report.md` 完成 real LLM integration test；本刀做 Sprint 6 closure。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 016（Sprint 6） |
| **触发** | `ece/TASKS.md` S6 + 用户"cut-016"指令 |
| **上游参考（只读）** | `docs/API.md` §8 (audit/debug endpoint spec) + `docs/DATA_MODEL.md` §5 (context_requests + context_items schema) + ADR-004 (PermissionScope) + ECE/CLAUDE.md (Debugger UI server-rendered, no SPA) + ECE/CLAUDE.md 私有化验收 |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-15 |
| **涉及文件** | `src/ece/audit/trace.py` (NEW) + `src/ece/api/audit.py` (NEW) + `src/ece/api/debug.py` (NEW) + `src/ece/main.py` (EDIT, wire routers) + `docs/API.md` (EDIT, §8 expand + /debug doc) + `tests/integration/test_s6_audit.py` (NEW, 8 tests) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | Sprint 6 closure: /audit/context JSON endpoint + /debug HTML UI (server-rendered) + 私有化 env flag + 8 tests; deferred to cut-017+: v0.1 release prep (real perf bench, E6 scale 100) |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行。**1 个工作 commit（`eb2aad7`）+ 1 个报告 commit**。批处理不触碰 §7 区段。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（Sprint 6 closure 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 4（`audit/trace.py` + `api/audit.py` + `api/debug.py` + `tests/integration/test_s6_audit.py`） |
| 修改 Python文件 | 1（`main.py` wire audit + debug routers） |
| 修改 Data文件 | 1（`docs/API.md` §8 expand + /debug doc） |
| 新增 测试 | 8（audit + debug integration tests） |
| 总计 | 6 files changed, 521 insertions(+), 1 deletion(-) |

### 1.2 逐交付

#### Audit trace helper（`src/ece/audit/trace.py` NEW）

- `get_context_trace(engine, request_id) → dict | None`
- 读 `context_requests` + `context_items`（per DATA_MODEL §5）
- 返回: `request_id, user_ref, intent, status, counts, latency_ms, created_at, items[]`
- 每 item: `seq, item_kind, ref, decision, reason, source`（per DATA_MODEL §5 schema）

#### /audit/context JSON endpoint（`src/ece/api/audit.py` NEW）

- `GET /api/v1/audit/context/{request_id}` per `docs/API.md` §8
- `AuditTraceItem` + `AuditTraceResponse` Pydantic models
- Per ADR-004 **PermissionScope**: only owner (user_ref match) 可 view
- Errors:
  - `400` missing `X-User-Id` header
  - `403` other user accessing
  - `404` request_id 不存在

#### Debugger UI（`src/ece/api/debug.py` NEW）

- `GET /debug/context/{request_id}` per `docs/API.md` §8
- **Server-rendered HTML**（per ECE/CLAUDE.md: no SPA framework, no Jinja2）
- 私有化 mode: `ECE_DEPLOYMENT_MODE=local` enables; production → 404
- HTML output: metadata + counts badges + items table (Seq/Kind/Ref/Decision/Reason)
- Same PermissionScope as /audit (owner-only)

#### main.py wire（`src/ece/main.py` EDIT）

- Add `audit_router` + `debug_router` to imports + `app.include_router(...)`
- Update endpoint map comment: Sprint 6 routes now in app routes (not "planned")
- /debug/* no longer in `check-api-docs` WARN list

#### API.md doc update（`docs/API.md` EDIT）

- §8 expand: GET /api/v1/audit/context full schema (request/response with items)
- §8 add: GET /debug/context/{request_id} (private deployment)
- Heading fix: remove fullwidth parens from heading (check_api_docs regex pattern)

#### Tests (8 新增)

`tests/integration/test_s6_audit.py`:

| Test | 验证 |
|---|---|
| `test_audit_context_endpoint_requires_x_user_id` | 400 缺 `X-User-Id` |
| `test_audit_context_not_found` | 404 不存在 request_id |
| `test_audit_context_returns_trace` | 200 with full payload (request_id, user_ref, intent, status, counts, items, latency_ms) |
| `test_audit_context_forbidden_other_user` | 403 PermissionScope (other user) |
| `test_debug_context_404_in_production` | 404 when `ECE_DEPLOYMENT_MODE=production` |
| `test_debug_context_html_in_local` | 200 HTML (default `local` mode) with `Context Trace` + request_id in body |
| `test_debug_context_forbidden_other_user_local` | 403 even in local mode (PermissionScope enforced) |
| `test_audit_trace_module_importable` | `get_context_trace` callable + has `engine`/`request_id` params |

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `eb2aad7` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 88 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 141 passed, 6 skipped, 1 warning in 17.08s
$ make check-api-docs          # OK — 14 routes registered (Common: 14 | Docs-only (planned): 0 | App-only: 0)
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
eb2aad7 feat(s6): /audit/context + Debugger UI + private deployment mode (cut-016 closure)
0663dd4 docs(research-v2): cut 015b report (Sprint 5 follow-up #2 — real LLM integration test)
de4d4b6 test(s5): real LLM integration tests for E6 ≥80% accuracy gate (cut-015b closure)
cd4f1a4 docs(research-v2): cut 015a report (Sprint 5 follow-up — MockLLM status-based + E6 scale 50)
98469fe fix(s5): MockLLM status-based + E6 scale 50 + fallback (cut-015a closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 141 passed 6 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| v0.1 release prep | cut-017+ (real perf bench 真值 data + E6 scale to 100) |
| Multi-user PermissionScope | V0 仅 owner;多人协作 cut-018+ |
| 持久化 audit log | V0 context_requests + context_items 已够;持久化归 cut-017+ |
| Audit export tool (scripts/export_audit.py) | docs/API.md §8 提及; cut-017+ |
| Production mode Debugger UI 替代 (e.g. read-only timeline) | V0 仅本地 私有化;production 不开 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE_DEPLOYMENT_MODE env | 默认 `local`（dev） | 生产设 `production` 自动隐藏 /debug/* |
| Debugger UI 私有化 | ✅ 完整（server-rendered HTML, no SPA per ECE/CLAUDE.md） | 无 |
| /audit PermissionScope | ✅ owner-only | 多用户 cut-018+ 扩 |
| 5 项 discipline | ✅ 全绿（141 passed 6 skipped, 14 routes registered） | 无 |

---

## 3. Commit 信息

**1 个工作 commit（Sprint 6 closure 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `eb2aad7` | 6 files, +521/-1（audit/trace + api/audit + api/debug + main.py wire + API.md + 8 tests） | ✅ 5 项纪律全绿；make test 141 passed 6 skipped |

**HEAD after push**: `eb2aad74f30b2f1a633e061f02782ff794b44708`

**Push range**: `de4d4b6..eb2aad7 main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 check_api_docs.py regex heading 陷阱（中文 fullwidth 字符吞 path）

**症状**: `make check-api-docs` 报 `ERROR — implemented but not documented: GET /debug/context/{request_id}`。但 `docs/API.md` §8 有完整 endpoint 文档。

**根因**: `check_api_docs.py` 的 regex:
```python
pattern = re.compile(r"^###\s+(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)")
```

`[^\s]+` 匹配 non-whitespace 字符。**中文 fullwidth `（` 不是 whitespace**（Unicode property 不同于 ASCII 空白），所以 regex 把 `/debug/context/{request_id}（私有部署 only）` 整段 capture 起来 → 提取的 path 变成 `/debug/context/{request_id}（私有部署` 含中文括号 → 不 match app 实际 route `/debug/context/{request_id}` → "not documented"。

**修复**:
```diff
- ### GET /debug/context/{request_id}（私有部署 only）
+ ### GET /debug/context/{request_id}
+
+ Server-rendered HTML trace page (per ECE/CLAUDE.md: no SPA framework)。
+ ...
```

把中文括号挪到 heading 下行，**heading 只含 clean path**。Regex 正常 match → "documented"。

**教训**（§6.4 入红线）:
- **regex 测试 path 必须检查 non-ASCII 字符**: `[^\s]+` 看似 safe 但中文括号/标点会被吞入
- **doc heading 严格只含 METHOD + path**: 描述挪下 1 行
- **避免 fullwidth 字符在 regex 路径里**: 中文 docs 章节标题 / 描述挪下 heading 行

### 4.2 Debugger UI server-rendered HTML (no SPA, no Jinja2)

**Per ECE/CLAUDE.md**: "no SPA framework, no frontend build pipeline"。**V0 实现 = inline f-string + html.escape**:
```python
return (
    '<!DOCTYPE html>\n'
    '<html lang="zh-CN">\n'
    "<head>\n"
    '  <meta charset="UTF-8">\n'
    f"  <title>Context Trace {html.escape(trace['request_id'])}</title>\n"
    "  <style>\n"
    "    body { font-family: -apple-system, sans-serif; margin: 20px; }\n"
    ...
    "</body>\n"
    "</html>"
)
```

**关键**:
- `html.escape()` 在每个动态值 — 防 XSS（虽然 PermissionScope 已限制 owner-only，但 defense in depth）
- 内联 CSS（V0 简表）— 复杂 styles 可用 link tag + static dir
- 不依赖 Jinja2 等模板引擎 — install footprint minimal

**好处**:
- 单文件 endpoint 完整 UI
- 无前端 build pipeline (`npm install` 不需要)
- V0 部署 = Python 进程 + `ECE_DEPLOYMENT_MODE=local`
- Sprint 5 切 real LLM 仍 V0 模式即可

**对比 路径 决定** (per cut-010 §4.4): `/debug/*` 是私部署 专属, `/audit/*` 是 API(JSON); 两者 share audit 逻辑但 render 格式不同

### 4.3 私有化 deployment mode via ECE_DEPLOYMENT_MODE env

**机制** (per cut-016 §1.2 + ECE/CLAUDE.md 私有化验收):
```python
def _is_private_deployment() -> bool:
    return os.environ.get("ECE_DEPLOYMENT_MODE", "local") == "local"

@router.get("/debug/context/{request_id}")
def get_debug_context(...):
    if not _is_private_deployment():
        raise HTTPException(status_code=404, ...)
    # ... return HTML
```

**默认** = `local`（开发友好）。**生产** = `ECE_DEPLOYMENT_MODE=production` → /debug/* 返 404（hide UI 避免外网暴露）。

**V0 选 404 而非 403** 的理由: 404 不泄露 endpoint 存在性（anti-probing: 不知道 /debug 是否注册）；403 会暴露注册事实。

**Sprint 5+ 增强**:
- /debug/* 应额外 加 IP allowlist（仅 localhost / 内网）
- 或加 HTTP basic auth (development token)

---

## 5. 经验教训

1. **check_api_docs regex 中文陷阱**（§4.1）: `[^\s]+` 看似 safe 但中文 fullwidth 字符（`（）`）不是 whitespace → 吞入 path → 不 match app 实际 route。**doc heading 严格只含 METHOD + path**，中文描述挪下 1 行
2. **Server-rendered HTML 用 inline f-string + html.escape**（§4.2）: 不依赖 Jinja2 等模板引擎（per ECE/CLAUDE.md no SPA framework）。`html.escape()` 每个动态值防 XSS（defense in depth 即使 PermissionScope 已限 owner-only）
3. **私有化 mode 用 404 而非 403**（§4.3）: 隐藏 endpoint 存在性（anti-probing）；403 暴露注册事实
4. **/audit 与 /debug 共享 PermissionScope 验证**（§1.2）: 同一 `trace["user_ref"] != x_user_id` check 两 endpoint 复用 — DRY 不重复验证逻辑
5. **Sprint 6 跨 cut 验证**: audit JSON 端点 + debug HTML UI 同步落地（不只一个 endpoint），让 E2E Debugger 体验完整

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-016-report.md` | `ece/reports/cut-017-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 3 项非典型项（**check_api_docs regex 中文陷阱 / Server-rendered HTML inline f-string / 私有化 404 vs 403**）
- §5 5 条教训
- §6 红线 (累积 cut-007-008-009-010-011-012-013-014-015a-015b-016)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013-014-015a-015b-016）

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
- **check_api_docs regex 中文陷阱**（cut-016 §4.1 入红线——`[^\s]+` 看似 safe 但中文 fullwidth 字符（`（）`）会被吞入 path；doc heading 严格只含 METHOD + path，中文描述挪下 1 行）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。