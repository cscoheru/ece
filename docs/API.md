# API — Enterprise Context Engine v0

> 上游：`PRD.md` §18/§17/§22/§30/§31。契约即代码：本文件变更必须先于实现（FastAPI Pydantic 模型与此一一对应）。

## 0. 通用约定

- Base URL：`/api/v1`；内容类型 `application/json; charset=utf-8`。
- **身份（v0）**：请求头 `X-User-Id: U001`（display_id）。生产级 SSO/OIDC 明确不在 v0 范围（ADR-001）。
- **身份（v0.2+ cut-027/032, cut-036 收紧）**：当 `ECE_JWT_SECRET` 或 `ECE_JWT_PUBLIC_KEY` 配置时，JWT 模式开启。**默认强制** `Authorization: Bearer <jwt>`；缺失或无效 → **401** + `WWW-Authenticate: Bearer realm="ece"`。`X-User-Id` 仅当 `ECE_ALLOW_HEADER_AUTH=1` 显式 opt-in 时可用作回落（不推荐：JWT 模式下回落存在冒充风险，参见 cut-036 R36.1）。
- **管理端点**：另需 `X-Admin-Token: $ECE_ADMIN_TOKEN`（/ingest、批量写）。
- 错误模型（RFC 7807 简化）：

```json
{"error": {"code": "permission_denied", "message": "U002 无权访问 PR001", "request_id": "ctx_..."}}
```

  code 枚举：`bad_request | not_found | permission_denied | unauthorized | resolution_ambiguous | insufficient_context | disabled_feature | internal`。
  - `unauthorized`（cut-036 新增）：JWT 模式开启 + 缺失/无效 Authorization（401）；区别于 `permission_denied`（403，资源级权限不足）。
- 所有响应可含 `request_id`（关联 `context_requests` 审计）。
- 时间：ISO-8601 UTC；日期（as_of/valid_from）为 `YYYY-MM-DD`。

## 1. Context（核心）

### POST /api/v1/context

组装任务上下文（ARCHITECTURE §3 十二步流水线的入口）。

请求：

```json
{
  "user_id": "U001",
  "intent": "evaluate_purchase_request",
  "entities": [{"type": "purchase_request", "id": "PR001"}],
  "as_of": null,
  "options": {"include_denied": true}
}
```

响应 `200`（结构见 ARCHITECTURE §2.2，此处给关键示例）：

```json
{
  "package_id": "ctx_01J...",
  "request_id": "0f1e...",
  "task": {"intent": "evaluate_purchase_request", "spec_version": 1},
  "user": {"id": "U001", "display": "张三", "department": "D01", "roles": ["procurement_manager"]},
  "entities": [
    {"ref": "PR001", "type": "purchase_request",
     "attrs": {"title": "采购1000台网络设备", "qty": 1000, "amount": 1280000, "currency": "CNY"},
     "src": {"system": "erp", "record_id": "PR001", "field": "total_amount"}},
    {"ref": "SUP001", "type": "supplier", "attrs": {"name": "无限极（中国）有限公司"}, "src": {"system": "erp", "record_id": "10028"}}
  ],
  "relationships": [
    {"from": "PR001", "rel": "SELECTS", "to": "SUP001", "valid": ["2026-01-01", null],
     "src": {"system": "erp", "record_id": "PR-PR001-SUP001"}}
  ],
  "documents": [
    {"doc": "POL-2026-03", "chunk": 12, "text": "采购金额超过100万元需三家供应商比价…",
     "src": {"system": "docs", "document_id": "POL-2026-03", "page": 12}}
  ],
  "business_data": [
    {"kind": "historical_purchase", "rows": [{"date": "2025-08-11", "product": "PRD017", "qty": 800, "unit_price": 1150, "pr": "PR0003"}],
     "src": {"system": "erp", "record_id": "REC0117"}}
  ],
  "denied": [{"ref": "CON009", "reason": "acl:department_denied"}],
  "sources": [{"sid": "s1", "system": "erp", "record_id": "PR001"}],
  "metadata": {"generated_at": "2026-09-04T10:00:00Z", "as_of": null,
               "counts": {"entities": 9, "relationships": 14, "documents": 5, "rows": 12, "denied": 1}}
}
```

错误：`resolution_ambiguous`（实体消歧失败，返回候选列表）；`insufficient_context`（spec 必需项被权限清空——**合法结果而非错误重试对象**，Agent 应据此声明信息不足）。

## 2. Search

### POST /api/v1/search

```json
{
  "user_id": "U001",
  "query": "网络设备 比价政策",
  "kinds": ["keyword", "vector", "entity", "structured", "relationship"],
  "filters": {"entity_type": "supplier", "doc_type": "procurement_policy"},
  "top_k": 10
}
```

响应：统一结果项 `[{kind, ref, title, snippet, score, src, matched_by[]}]`。**结果已过权限过滤**；被滤除数量在 `meta.denied_count`（不列明细）。

## 3. Entities / Relationships

### GET /api/v1/entities/{display_id}

单实体（过权限；404=不存在或无权，响应一致以防探测）

**Response**: `{ "ref": "SUP001", "type": "supplier", "name": "...", "attributes": {...}, "src": {"system": "...", "record_id": "..."} }`

### GET /api/v1/entities

过滤查询（q 匹配 name/alias，过权限）

**Query**:
- `type` (optional): filter by entity_type
- `q` (optional): substring match on name or alias
- `limit` (default 50, max 200)
- `cursor` (optional): opaque base64 of last display_id from previous page

**Response**: `{ "items": [Entity, ...], "next_cursor": "<base64>" | null }`

### POST /api/v1/entities

批量 upsert（Admin；走 Connector 归一化通道，禁止直插绕过 resolution）

**Body**: `{ "items": [{"type": "...", "name": "...", "source_id": "...", "source_system": "...", "attributes": {...}}, ...] }`

**Response**: `{ "created": int, "updated": int, "errors": [{"index": int, "source_id": "...", "error": "..."}] }`

### GET /api/v1/entities/{display_id}/relationships

关系查询（过权限 + temporal）

**Query**:
- `relation` (optional): filter by relation type (e.g. SUBMITTED_BY)
- `direction` (default "out"): out | in | both
- `as_of` (optional, ISO date): temporal filter

**Response**: `{ "items": [{"from": "U001", "rel": "SUBMITTED_BY", "to": "PR001", "valid": ["2026-01-01", null], "src": {"system": "...", "record_id": "..."}}, ...] }`

## 5. Permissions

### POST /api/v1/permissions/check

检查用户是否能访问某对象。返回 decision (allowed/reason/matched_rule)。

**Body**:
```json
{
  "user_ref": "U001",
  "object_type": "entity",
  "object_ref": "SUP001",
  "classification": "department"
}
```

`X-User-Id` header 也可（推荐，per ADR-004）。

**Response**:
```json
{
  "allowed": true,
  "reason": "classification department (matched)",
  "matched_rule": "classification-dept"
}
```

判定顺序（per ADR-004 Permission Before Context Assembly）：deny > user > role > dept > classification 默认矩阵 > default deny。

## 4. Resolve（Entity Resolution 服务化）

### POST /api/v1/resolve

`{"mention": "无限极", "type_hint": "supplier"}` → `{ "candidates": [...], "resolved": bool }`

6 级流水线（v0 实现 1-3 级）：exact → normalized → alias → rule → embedding → LLM。

歧义规则（per cut-005 §7.4）：多候选 → `resolved=false`，**不猜测**。### POST /api/v1/resolve

```json
{"mentions": [{"text": "无限极", "type_hint": "supplier"}, {"text": "张经理", "type_hint": "person"}]}
```

响应：`[{mention_index, candidates: [{entity: "SUP001", name: "无限极（中国）有限公司", method: "alias", confidence: 0.98}], resolved: true}]`。
`resolved:false` 且多候选 → 调用方（或 Agent）必须澄清，禁止默认取第一。

## 5. Permissions

### POST /api/v1/permissions/check

```json
{"user_id": "U002", "object_type": "entity", "object_ref": "PR001", "action": "read"}
```

响应：`{"allowed": false, "reason": "acl:department_denied", "request_id": "..."}`。
供测试、Debugger 与外部系统复用同一判定逻辑（Permission Engine 单点）。

## 6. Actions（PRD §30）

### POST /api/v1/actions/preview

```json
{"user_id": "U001", "intent": "evaluate_purchase_request",
 "entities": [{"type": "purchase_request", "id": "PR001"}],
 "question": "PR001 这个采购申请合理吗？"}
```

流程：内部调 /context（同一权限管线）→ Procurement Agent（规则+LLM）→ 返回：

```json
{
  "request_id": "...",
  "conclusion": "存在采购价格偏高风险",
  "reasoning_summary": "①报价高于历史价11.3%；②高于市场参考价8.5%；③金额触发三家比价要求；④未见完整比价记录",
  "risks": [{"type": "price_deviation", "detail": "1280 vs 历史均价1150", "evidence_sid": "s4"}],
  "recommendation": "补充三家比价材料后再进入下一审批阶段",
  "evidence": [{"sid": "s1", "fact": "采购金额128万元", "src": {"system": "erp", "record_id": "PR001", "field": "total_amount"}}],
  "confidence": 0.86
}
```

**约束**：每条 evidence 的 `sid` 必须存在于当次 package 的 `sources`（评测强制校验）。

### POST /api/v1/actions/execute

v0 **恒定返回** `403 {"code":"disabled_feature"}`（env kill-switch + 路由级硬编码双保险，ADR-004/PRD §18）。

## 7. Ingest（Admin）

### POST /api/v1/ingest/runs

`{"connector": "csv:suppliers", "params": {"path": "data/sample/suppliers.csv"}, "batch": "default"}` → `{"run_id": int, "stats": {...}}`

同步执行，v0 不做队列。stats 含 created / updated / skipped / errors。

### GET /api/v1/ingest/runs/{run_id}

状态与 stats（created/updated/skipped/errors）

**Response**: `{ "run_id": int, "connector": "...", "status": "done|done_with_errors", "stats": {...}, "started_at": "...", "finished_at": "..." }`

Connector 契约（ARCHITECTURE §1）：`connect / discover_schema / fetch / normalize / sync`；新数据源 = 新 Connector 类 + ontology 映射声明，不改引擎。

## 8. Audit / Debugger

### GET /api/v1/audit/context/{request_id}

Returns the trace for a context request (context_requests + context_items rows).

Per ADR-004 PermissionScope: only the owner (`user_ref`) can view their own traces.

**Headers** (cut-018b + cut-019 + cut-021 + cut-022 + cut-023 + cut-024):

| Header | Required | 用途 |
|---|---|---|
| `X-User-Id` | one of these | 自我访问 (owner check, 不可被撤销) |
| `X-Delegation-Token` | one of these | 跨用户访问 (manager / shared service, cut-018b，可被 cut-024 撤销) |
| `X-Delegation-Token` | 跨 org | 跨 org 访问 (cut-021 `ECE_DELEGATION_ORG_TOKENS`) |
| `X-Delegation-Token` | per-resource | 特定 request_id 访问 (cut-022 `ECE_AUDIT_TOKEN_REQUEST_IDS`) |
| `X-Org-Id` | 仅多租户模式 | 跨 org 隔离 (cut-019) + **速率限制**（桶选择由 cut-037 R37.2 改绑 user_ref 映射，X-Org-Id **不参与**） |

请求:

```
GET /api/v1/audit/context/{request_id}
X-User-Id: demo-user-procurement
X-Org-Id: org_a          # 仅当 ECE_USER_ORGS 配置时
```

响应 `200`:

```json
{
  "request_id": "ctx_abc123...",
  "user_ref": "demo-user-procurement",
  "intent": "evaluate_purchase_request",
  "status": "ok",
  "counts": {"entities": 5, "relationships": 4, "denied": 1, "documents": 0},
  "items": [
    {
      "seq": 0,
      "item_kind": "entity",
      "ref": "PR001",
      "decision": "allowed",
      "reason": "spec:root",
      "source": {"system": "demo:demo", "record_id": "..."}
    }
  ],
  "latency_ms": 87,
  "created_at": "2026-09-15T00:00:00+00:00",
  "org_id": "org_a"
}
```

错误：
- `401` JWT 模式开启 + 缺失/无效 Authorization（cut-036 R36.1）→ `code: unauthorized` + `WWW-Authenticate: Bearer realm="ece"`
- `400` 缺 `X-User-Id`/`X-Delegation-Token`；多租户模式下缺 `X-Org-Id`
- `403` 非 owner 调用 **或** 跨 org 访问 (`X-Org-Id != trace.org_id`)
- `404` request_id 不存在

**速率桶绑定（cut-037 R37.2 + cut-038 R38.3 文档回锚）**：
- 桶键 = `ECE_USER_ORGS` 映射的 user_ref 的 org（未映射 → 固定字符串 `"default"`）
- **X-Org-Id header 不再用于桶选择**（per "不再信裸 X-Org-Id" 指令，cut-037 R37.2）；X-Org-Id 仍用于跨 org 隔离（cut-019）和多租户 mode 的强制 header
- **单租户部署**（`ECE_USER_ORGS` 未配置）：所有未映射 user 共用 `"default"` 桶；operator 必须按 `ECE_ORG_RATE_LIMITS="default:N/m"` 配置（**不能用 X-Org-Id segmentation**——rotation evasion 已关）
- Quota 同理（`ECE_ORG_QUOTAS="default:Nd"`）

**多租户隔离 (cut-019)**：当 `ECE_USER_ORGS="user1:org_a;user2:org_b"` 配置时，
context_requests 行在 assemble_context 时记录 user 的 org_id；/audit 必须
提供 `X-Org-Id` 头且与 trace.org_id 匹配，否则 `403` (跨 org 阻止)。
单租户 (env 未配置)：不强制 `X-Org-Id`。

### GET /debug/context/{request_id}

Server-rendered HTML trace page (per ECE/CLAUDE.md: no SPA framework)。

仅当 `ECE_DEPLOYMENT_MODE=local` 启用；production mode 返 `404`（per 私有化验收）。

请求:

```
GET /debug/context/{request_id}
X-User-Id: demo-user-procurement
```

响应 `200 text/html`：HTML 表格列出 metadata + items（与 /audit 一致但 HTML 渲染）。

错误：
- `401` JWT 模式开启 + 缺失/无效 Authorization（cut-036 R36.1）→ `code: unauthorized` + `WWW-Authenticate: Bearer realm="ece"`
- `400` 缺 `X-User-Id`
- `403` 非 owner **或非 localhost 访问**
- `404` request_id 不存在或 production mode (`ECE_DEPLOYMENT_MODE=production`)

**安全限制（v0.1 deployment cut-018a）**:
- `/debug/*` 仅允许 localhost 访问（per ECE/CLAUDE.md 私有化验收 → 防止 audit trace 泄漏到外网）
- 默认允许 host: `127.0.0.1`, `::1`, `localhost`, `testclient` (test client)
- 覆盖: `DEBUG_ALLOWED_HOSTS="host1,host2,..."` 环境变量
- 生产部署建议: `DEBUG_ALLOWED_HOSTS=""` (empty → 只有 127.0.0.1/::1 显式允许)

**多租户隔离 (cut-019)**：与 `/audit` 一致 — 多租户模式下需要 `X-Org-Id` 头
与 trace.org_id 匹配；不匹配 `403` 跨 org 阻止。

## 8.5. Demo（cut-042，跨域通用）

公开 SPA 调用的实时六步闭环接口。业务命名（禁内部字段 `decision_id` /
`input_context_ref` / `package_id` / `evidence_id` / `context_request_id` /
`ctx_` / `dec_` / `ev_` 前缀外露）。

### GET /api/v1/demo/domains

已注册域清单（每个含业务标签 + 该域的 scenario 文件清单）。

请求：
```
GET /api/v1/demo/domains
X-User-Id: <caller>
```

响应 `200`：
```json
{
  "domains": [
    {
      "name": "procurement",
      "label": "采购合规审查",
      "scenarios": ["default"]
    }
  ]
}
```

### POST /api/v1/demo/scenarios/generate

实时跑六步闭环（assemble → rule → decision → evidence → update → re-read），
返回业务命名结论 + 证据 + 状态变化。

请求：
```
POST /api/v1/demo/scenarios/generate
Content-Type: application/json
X-User-Id: <caller>

{
  "domain": "procurement",
  "scenario": "default",
  "params": {"amount": 1500000, "quote_count": 2}
}
```

响应 `200`（allowed user）：
```json
{
  "domain": "procurement",
  "scenario": "default",
  "conclusion": "review_required",
  "conclusion_label": "需人工复核",
  "reason": "金额 1,500,000 ≥ 1,000,000 且仅 2 家报价（需 3 家）→ 需人工复核",
  "evidence": [{"claim": "...", "observed": 1500000, "threshold": 1000000,
                "source_record_id": "PR-001", "source_system": "procurement.legacy",
                "actor": "<caller>", "recorded_at": "ISO-8601"}],
  "state_change": {"before": "pending", "after": "review_required", "key": "review_status"},
  "actor": "<caller>",
  "denied_for": ["<other-user>"],
  "elapsed_ms": 47.2,
  "generated_at": "ISO-8601"
}
```

响应 `200`（denied user）：
```json
{
  "conclusion": "no_permission",
  "conclusion_label": "无权查看",
  "reason": "denied",
  "evidence": [],
  "state_change": {"before": null, "after": "pending", "key": "review_status"},
  "actor": "<caller>",
  "denied_for": ["<caller>"],
  "elapsed_ms": 1.7,
  "generated_at": "ISO-8601"
}
```

错误：
- `422` 域或 scenario 不存在
- `500` DB 未连接 / seed 缺失

契约测试：`tests/integration/test_demo_api_contract.py`（6 tests，禁止内部字段外露 +
N=5 byte-equal 确定性 + denied 零副作用 + 真实运行 `elapsed_ms > 0`）。
部署契约：SPA 部署在 user 自有服务器（nginx 反代 `/api/`），单源部署规避 CORS，
见 `docs/demo-platform/DEPLOY_USER_PROXY.md`。

## 9. 健康

`GET /healthz`（进程存活）· `GET /readyz`（DB 连通 + migrations 版本一致 + LLM 端点可达（若配置））。

## 10. 版本化与兼容

- 破坏性变更升 `/api/v2`，v0 期间允许非破坏性字段新增。
- OpenAPI 由 FastAPI 自动生成（`/openapi.json`），CI 校验与 `API.md` 的端点清单一致（脚本 `scripts/check_api_docs.py`，Sprint 0 建立）。


## 6. Engine Status（OEI-003，Engine Core 内部状态页）

> ⚠️ 本端点**不在 `/api/v1/` 前缀下**——它是 Engine Core 内部状态页，由 `ContentEnginePort` 抽象支撑，**不**走 JWT / 权限层。用于演示与排障，**不进**外部 v1 契约。

### GET /engine/status

返回 Engine 状态快照 + 可选检索引用（HTML 页面，浏览器直接打开）。

**查询参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | string | 否 | 若提供，触发一次 `ContentEnginePort.search(q)` 并把召回文档渲染为引用卡片（`source_type` / `engine_doc_id` / snippet） |

**HTML 内容**（无 `q`）：

- 引擎名 + 版本
- tier / GPU 开关
- LLM provider + default model
- 项目数 + 文件数
- 最近一次检索耗时（秒；首次为 None）

**HTML 内容**（带 `q`）：

- 在上述快照之上加 `<h2>Citations for query: {q}</h2>` 段
- 每条召回文档渲染为：`<div class="doc">` 块，含 `<h3>{title}</h3>` + `<div class="meta">`（source_type / engine_doc_id / updated_at）+ `<pre>`（snippet，截断 800 字符）

**降级行为**：当 `ECE_ONYX_BASE` 不可达或 cookie 失效时：

- HTTP 仍为 **200**（不返回 500）
- 页面顶部显示 `Engine degraded: <reason>` 黄色横幅
- 快照字段区显示空集；citations 段显示 "Recall failed (see degraded banner above)"

**选择器**（`ECE_CONTENT_ENGINE`）：

- `mock`（默认）— 离线固定数据，演示/CI 用
- `onyx` — 真实 Onyx 引擎，需配 `ECE_ONYX_BASE` + `ECE_ONYX_COOKIE_FILE`

**示例**：

```bash
# 默认 mock 模式
curl -s 'http://127.0.0.1:8000/engine/status' | less

# 真实 Onyx 模式
ECE_CONTENT_ENGINE=onyx \
ECE_ONYX_BASE=http://127.0.0.1:8080 \
ECE_ONYX_COOKIE_FILE=/home/fisher/.onyx-lab/.secrets/admin-cookies.txt \
uv run uvicorn ece.main:app --port 8000

# 含检索
curl -s 'http://127.0.0.1:8000/engine/status?q=问题树怎么用' | less
```

**安全注意**：

- cookie **不**进 ECE 仓；运行时通过 `ECE_ONYX_COOKIE_FILE` 环境变量读取
- 该端点**不**走权限 / 审计层——只用于内部演示，**不应**对外暴露
