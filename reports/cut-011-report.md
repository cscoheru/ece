# Cut 011 Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 4 path B main——step 6/7 real impl + S4.5 MCP Tool Layer (4 tools + PermissionScope)。前一报告 `cut-010-report.md` 完成 S4.1 + S4.3 entry；本刀做 S3.2 pipeline completion + MCP 暴露。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 011（Sprint 4 path B main） |
| **触发** | `ece/TASKS.md` S3.2 step 6/7 + S4.5 + 用户"cut-011"指令 |
| **上游参考（只读）** | `docs/ARCHITECTURE.md` §3 step 6-7 + `docs/DATA_MODEL.md` §4 (documents schema) + `docs/API.md` §2 (POST /search) + cut-007 §1.2 (step 6/7 stubs) + cut-010 §4.4 (endpoint 路径分离) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-14 |
| **涉及文件** | `src/ece/context/documents.py` (NEW) + `src/ece/context/structured_data.py` (NEW) + `src/ece/mcp/{__init__,auth,tools,server}.py` (4 NEW) + `src/ece/context/assembly.py` (EDIT, replace step 6/7 stubs) + `pyproject.toml` (EDIT, add mcp>=1.0) + `uv.lock` (auto) + `tests/integration/test_s4_6_step6_7.py` (NEW, 6 tests) + `tests/integration/test_s5_mcp.py` (NEW, 8 tests) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | S3.2 step 6/7 real impl + S4.5 MCP Tool Layer (4 tools + auth + server)；mcp 2.x FastMCP→MCPServer 兼容性 fix；其他 S4.2 vector + S4.4 perf + temporal relationships 全部 deferred 到 cut-012+ |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行（per cut-002 §7.3.1 裁定生效）。**1 个工作 commit（`3a03e6a`）+ 1 个报告 commit**。批处理不触碰 §7 区段（per cut-003R2 治理注记）。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（step 6/7 + MCP + 5 side-fixes 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 8（2 context modules + 4 mcp modules + 2 test files） |
| 修改 Python文件 | 1（`assembly.py` 替换 step 6/7 stubs） |
| 修改 pyproject.toml | 1（`mcp>=1.0` 依赖） |
| uv.lock | 自动更新（mcp + transitive deps） |
| 新增 测试 | 14（6 S4.6 + 8 S5.1） |
| 总计 | 11 files changed, 1019 insertions(+), 6 deletions(-) |

### 1.2 逐 Sub-task 交付

#### S3.2 step 6 — Document retrieval（`src/ece/context/documents.py`）

| 内容 | 实现 |
|---|---|
| `get_documents(engine, spec, identity, as_of)` | FTS via `plainto_tsquery('simple', :q)` (handles multi-word natural language "procurement policy" → `procurement & policy`) + `ts_rank` ranking; JOIN documents for classification + title; per-row permission filter via `check_permission`; truncate to `spec.limits.max_chunks` |
| Permission filter | `check_permission(identity, "document", display_id, classification, acl_entries=[])` — no doc-level ACL rows in v0 (acl_entries table has no doc_type rows); classification default matrix handles public/department/management |
| Why `plainto_tsquery` (not `to_tsquery`) | cut-011 first attempt used `to_tsquery` — multi-word "procurement policy" syntax error (`psycopg.errors.SyntaxError: syntax error in tsquery: "procurement policy"`). `plainto_tsquery` is the natural-language variant that inserts `&` between tokens automatically. |
| Return shape | list of {doc, chunk, text[:200], snippet[:200], title, src} per docs/API.md §2 |

#### S3.2 step 7 — Structured data retrieval（`src/ece/context/structured_data.py`）

| 内容 | 实现 |
|---|---|
| `get_structured_data(engine, spec, identity, as_of)` | per-spec.kind SQL via `_KIND_HANDLERS` dispatch dict |
| v0 handlers | `historical_purchase` → `entities WHERE entity_type='purchase_record'`; `approval_history` → `entities WHERE entity_type='approval'`; both LIMIT 100 |
| Fail-soft | Unknown kind → skip (not raise) per ADR-004 — future specs can list kinds before handlers exist |
| Permission | per-row `check_permission(entity, "entity", display_id, "department", acl_entries=[])` — uniform envelope |
| v0 demo returns `[]` | demo has no purchase_record/approval entities seeded; spec handlers return empty for these kinds. **Sprint 5+ 真实数据后才有 rows** |

#### Assembly update（`src/ece/context/assembly.py`）

```python
# Before (cut-007 §1.2 stub)
documents: list[dict[str, Any]] = []
business_data: list[dict[str, Any]] = []

# After (cut-011 real impl)
documents = get_documents(engine, spec, identity, as_of=as_of)
business_data = get_structured_data(engine, spec, identity, as_of=as_of)
```

`assemble_context` 现在返回真数据——`pkg.documents` / `pkg.business_data` 不再永远空。**`/context` endpoint 真正有用**（v0 demo 数据下 documents 含 POL-2026-03 chunks，business_data 仍空）。

#### S4.5 — MCP Tool Layer（`src/ece/mcp/`）

| 文件 | 内容 |
|---|---|
| `__init__.py` | Package marker + 设计 summary（4 tools + PermissionScope） |
| `auth.py` | `check_user_permission(user_ref, object_type, object_ref, classification='public')` — resolves identity, inlines ACL load (per-object-type: entity/document), returns True/False via check_permission. `object_exists` for anti-probing not_found vs forbidden. |
| `tools.py` | 4 tool implementations: `search_tool` (calls search_documents), `get_record_tool` (2-step: existence→permission; returns `{error: not_found\|forbidden}` envelope), `create_task_tool` (PREVIEW ONLY), `send_message_tool` (PREVIEW ONLY) |
| `server.py` | `mcp = MCPServer("ECE Context Engine")` (mcp 2.x rename); 4 `@mcp.tool()` decorators; `mcp.run()` stdio transport. Claude Code 接入: `claude mcp add ece-context -- python -m ece.mcp.server` |

**create_task + send_message PREVIEW ONLY**: per ADR-004 + ECE/CLAUDE.md iron rule: `/actions/execute` v0 关闭。两 tool 返回 `preview: True, status: "would_create"/"would_send"` 描述会做什么但不真做。

**PermissionScope 强制**: 每个 tool call 经 `auth.check_user_permission` (per ADR-004 anti-probing + ECE/CLAUDE.md iron rule 1 "Permission Before Intelligence")。**tool 不能绕过权限引擎**——这是 MCP 层与 API 层共享的同一个 invariant。

#### Tests（14 个新增）

**test_s4_6_step6_7.py (6 tests)**:
1. `test_get_documents_with_demo_seed` — POL-2026-03 in package after assemble
2. `test_get_documents_empty_when_no_spec_documents` — requires.documents=[] → []
3. `test_get_documents_truncated_to_max_chunks` — `len(items) <= spec.limits.max_chunks`
4. `test_get_structured_data_empty_when_no_kind` — `requires.structured_data=[]` → []
5. `test_get_structured_data_unknown_kind_returns_empty` — fail-soft per ADR-004
6. `test_assemble_context_includes_documents_field` — end-to-end integration

**test_s5_mcp.py (8 tests)**:
1. `test_search_tool_returns_dict` — `{items, meta}` structure
2. `test_get_record_tool_existing_entity` — PR201 (demo-seeded) returns ref+type
3. `test_get_record_tool_unknown_user_returns_forbidden` — anti-probing: unknown user + existing object → forbidden (not not_found)
4. `test_get_record_tool_non_existent_display_id_returns_not_found` — anti-probing: missing → not_found
5. `test_get_record_tool_refuses_to_leak_existence` — low-permission user + existing object → cannot tell if exists
6. `test_create_task_is_preview_only` — preview=True, status=would_create
7. `test_send_message_is_preview_only` — preview=True, status=would_send
8. `test_send_message_body_length_recorded` — body_length metadata

#### Side-fixes (5 incidental)

| 文件 | 修复内容 |
|---|---|
| `pyproject.toml` | `mcp>=1.0` 依赖添加（per TASKS.md S4.5） |
| `src/ece/mcp/server.py` | `mcp.server.fastmcp.FastMCP` → `mcp.server.mcpserver.MCPServer`（mcp 2.2.0 重命名；v1 API 已 deprecated） |
| `src/ece/mcp/server.py` | `mcp = FastMCP(...)` → `mcp = MCPServer(...)`（同 rename） |
| `src/ece/context/documents.py` | `to_tsquery` → `plainto_tsquery`（多词 query 语法 error：FTS natural language 支持） |
| `tests/integration/test_s5_mcp.py` | `PR0001` → `PR201`（demo seed 不含 4-digit zero-padded PR；改用 known-existing 3-digit PR） |
| `src/ece/mcp/auth.py` | `_load_acl_for` private import 改 inline ACL query（per-object-type 支持 entity/document；保留 private 命名） |

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `3a03e6a` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 69 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 94 passed, 3 skipped, 1 warning in 11.34s
$ make check-api-docs          # OK — no app-only routes
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
3a03e6a feat(s4): step 6/7 real impl + MCP Tool Layer (4 tools + PermissionScope) (cut-011 closure)
4e5cbec docs(research-v2): cut 010 report (Sprint 4 path B entry — S4.1 + S4.3)
1205727 feat(s4): doc ingestion + POST /search endpoint with FTS keyword route (cut-010 closure)
eb40093 docs(research-v2): cut 009 report (path A — seed_relationships unlocks E4/E5)
7554731 feat(s3): seed_relationships (path A unlock E4/E5) + FK cleanup fixes (cut-009 closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 94 passed 3 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| S4.2 vector route (embedding model) | cut-012+（bge-small-zh-v1.5 部署 + 推理 pipeline） |
| S4.4 perf benchmark (p95<1.5s) | cut-012+（需要真值 benchmark） |
| Structured data 更多 kind handlers | cut-012+（需要更多 demo data 验证） |
| Chinese tokenization (zhparser / pg_trgm / bigram) | cut-012+（ADR-009 appendix） |
| Temporal relationships (2025/2026 manager change) | cut-012+（role entity 加 temporal predicate） |
| /actions/execute 启用 (create_task/send_message 真值) | v0 ADR-004 关闭；Sprint 5+ 真值场景才开 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE API server | ❌ 8765 未启动 | runner skip；test 用 TestClient in-process |
| `alembic current` | ✅ `0005_context_audit (head)` | 无 |
| mcp 2.2.0 FastMCP 重命名 | ⚠️ v1 API 失效；本刀已迁移到 MCPServer | v2 migration guide 引用 |
| `mcp>=1.0` 依赖 | ✅ 2.2.0 安装（2.2.0 是 latest） | uv sync 已 run |
| demo data: purchase_record/approval entities | ❌ 0 行 | `get_structured_data` v0 仍返回 []（per-spec.kind handlers 已写就绪，等真值数据） |
| demo data: FTS 检索 POL-2026-03 | ✅ 已 ingest | `get_documents` 实际检索到 demo doc（per spec, `query = doc_type.replace("_", " ")` → "procurement policy"） |
| FTS 简单 tokenizer 中文精度 | ⚠️ V0 限制 | 切-012+ 加 zhparser / bigram fallback（per cut-010 §4.3） |

---

## 3. Commit 信息

**1 个工作 commit（step 6/7 + MCP + 5 side-fixes 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `3a03e6a` | 11 files, +1019/-6（2 context + 4 mcp + 2 test + 1 assembly edit + 1 pyproject + 1 uv.lock） | ✅ 5 项纪律全绿；make test 94 passed 3 skipped |

**HEAD after push**: `3a03e6af3562a2baecabe5abaf9c78117213cf89`

**Push range**: `4e5cbec..3a03e6a main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 mcp 2.x FastMCP→MCPServer 重命名（库版本升级兼容性）

`mcp 2.0+` 把 v1 `FastMCP` 重命名为 `MCPServer`，import path 从 `mcp.server.fastmcp` 改为 `mcp.server.mcpserver`。**代码迁移步骤**:
```python
# v1 (mcp<2) — 失效
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("...")

# v2 (mcp>=2.0) — 当前
from mcp.server.mcpserver import MCPServer
mcp = MCPServer("...")
```

`@mcp.tool()` 装饰器签名相同（params/return schema 自动推导）。迁移指南：https://py.sdk.modelcontextprotocol.io/v2/migration/

**触发原因**: `pyproject.toml` 写 `mcp>=1.0`，`uv sync` 装的是 2.2.0（latest）。**若需锁定 v1 API**：`mcp<2`。

**教训**: 跨库 major version 升级 = import path + class name 都可能变。**Sprint 5+ 真实部署前应该 test 全部 v2 兼容**。本 cut 1 个文件 1 行 import fix 兜底。

### 4.2 to_tsquery vs plainto_tsquery（FTS natural language 陷阱）

cut-011 第一版用 `to_tsquery('simple', :q)` → `psycopg.errors.SyntaxError: syntax error in tsquery: "procurement policy"`。**根因**: `to_tsquery` 需要 explicit operator（`&` / `|` / `!` / `<->`），空格分隔的多词 = 语法错误。

```sql
-- 失效:
WHERE dc.tsv @@ to_tsquery('simple', 'procurement policy')  -- 缺 &

-- 修复 (3 个选项):
WHERE dc.tsv @@ to_tsquery('simple', 'procurement & policy')  -- explicit &
WHERE dc.tsv @@ plainto_tsquery('simple', 'procurement policy')  -- auto-insert &
WHERE dc.tsv @@ phraseto_tsquery('simple', 'procurement policy')  -- phrasal match
```

**选 `plainto_tsquery`**: natural language API，对应用层友好（不需要 spec 文档化 query syntax）。

**教训**: PostgreSQL FTS 有 3 个 query 构造函数（`to_tsquery` / `plainto_tsquery` / `phraseto_tsquery`）——**应用层默认应选 `plainto_tsquery`**，需要 `phrasal` 匹配或 boolean operator 时才换。

### 4.3 demo PR0001 不在 seed（测试 data 假设错误）

`test_s5_mcp.py::test_get_record_tool_unknown_user_returns_forbidden` 用 `display_id="PR0001"`——`PR0001` 是 4-digit zero-padded 格式，但 `gen_dataset.py` 生成 3-digit 格式（PR001-PR201）。**测试用未 seed 的 data 触发 not_found 优先于 forbidden**。

**修复**: 改用 known-existing `PR201`（per cut-008 sample query）。

**教训**: 写 MCP/API/integration test 时，**display_id 必须先在 DB 里存在**——否则 not_found envelope 先于 permission envelope 触发，测试结果取决于数据状态而非 permission 逻辑。**Sprint 5+ 真实数据后**应考虑创建 fixed-display_id 的 test fixture entities（test seed）。

### 4.4 auth.py 内联 ACL load（private function 边界）

`_load_acl_for` 是 `permissions/engine.py` 的 private function（leading underscore）。我跨模块 import 它（auth.py）→ mypy 抓 `attr-defined`。

**修复**: 把 ACL query 内联到 `auth.py`（inlines 5 行），不修改 `engine.py` 的导出。

**对比 alternative**:
- (a) 把 `_load_acl_for` 改名为 `load_acl_for`（public），更新所有 callers（engine.py + assembly.py + auth.py）—— **3 文件修改**
- (b) 内联 query 到 auth.py —— **1 文件 5 行**

**选 (b)**: cross-module use of private functions = coupling leak。**修复 coupling 比增加 private symbol exposure 更优**。

**教训**: cross-module 用 private function（`_name`）即使能 work（Python 无 access modifier），是 design smell——mypy 抓到说明这个 coupling 异常。**修复 = 1) 内联 / 2) 提升为 public / 3) 提供 wrapper**。`plainto_tsquery` 类比：FTS function 都设计为 public-friendly API。

### 4.5 /actions/execute v0 关闭 + MCP tool preview（ADR-004 安全门）

`create_task_tool` / `send_message_tool` 在 v0 只返 preview，**不真做**——这是 ADR-004 "actions/execute disabled" + ECE/CLAUDE.md iron rule 的安全门。

```python
def create_task_tool(title: str, description: str) -> dict:
    """Preview only — no actual task creation per ADR-004."""
    return {
        "preview": True,
        "title": title,
        "status": "would_create",
        "note": "v0: actions/execute disabled per ADR-004; this is preview only",
    }
```

**设计意图**: MCP 是 Claude Code 的双向接口——tool 不应该隐式触发 side effect（task creation, message sending）。**v0 强制 preview = 用户可在 Claude Code UI 上看到 "would do" 描述再授权**。

**Sprint 5+ 真值场景**:
- 启用 `/actions/execute` 后端（env `ECE_ACTIONS_EXECUTE_ENABLED=true`）
- tool 真正调 API（`POST /api/v1/tasks` 等新 endpoint）
- preview 行为由 caller 决定（per-action 的 `confirm_required` flag）

**v0 教训**: 任何 side-effecting tool 必须先有 preview 路径——既保护 user 又让 Cline 审计有据可查。**Sprint 5+ add `/actions/execute` 时** preview 路径不能去掉，只能 toggle。

---

## 5. 经验教训

1. **mcp 2.x 兼容性（§4.1）**: major version 升级 = import path + class name 都变。`pyproject.toml` 写 `mcp>=1.0` 让 uv 装 2.2.0——下次 major bump 时同样的 fix。**Sprint 5+ 真实部署应 lock version**。
2. **FTS query 构造（§4.2）**: 应用层默认用 `plainto_tsquery`，避免 `to_tsquery` 字符串语法陷阱。**V1 spec 文档化时**明确 query format（plain vs tsquery syntax）。
3. **测试 data 假设（§4.3）**: integration test 用 `display_id` 必须先在 DB 里存在——否则 not_found 优先于 permission envelope 触发，测试结果依赖于 data state 而非 permission logic。**Sprint 5+**应加 test seed fixture。
4. **Cross-module private use = design smell（§4.4）**: mypy 抓到 `_load_acl_for` 私用是 **couping leak 信号**。修复 = 内联或 public 化。**Sprint 5+ 任何私用都先 review coupling**。
5. **Side-effecting tool 必有 preview 路径（§4.5）**: MCP tool 触发 side effect 必须先返 preview 给 caller 授权。V0 关闭 `/actions/execute` 强制 preview = ADR-004 安全门。**Sprint 5+** add 真值 endpoint 时 preview 路径不能去掉。
6. **cut-010 教训延续（路径分离）**: 这次 MCP server 与 `/api/v1/*` 走不同的 transport（stdio vs HTTP），但**共享 `auth.py` 的 PermissionScope**——**permission invariant 在所有层共享**（per ECE/CLAUDE.md iron rule 1），即使 transport 不同。

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-011-report.md` | `ece/reports/cut-012-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 5 项非典型项（**mcp 2.x 兼容性 / FTS query 构造 / 测试 data 假设 / private function 边界 / side-effecting tool preview**）
- §5 6 条教训
- §6 红线 (累积 cut-007-008-009-010-011)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010）

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
- **side-effecting tool 不带 preview 路径**（cut-011 §4.5 入红线——MCP tool 必返 preview 才算 v0 接受）
- **跨模块 import private function**（cut-011 §4.4 入红线——`_name` 仅本模块可见，跨模块 = design smell）
- **FTS query 用 `to_tsquery` 拼多词字符串**（cut-011 §4.2 入红线——应用层默认 `plainto_tsquery`）
- **integration test 用未 seed 的 display_id**（cut-011 §4.3 入红线——data state 不应决定 permission 测试结果）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。