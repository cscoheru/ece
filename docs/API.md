# API — Enterprise Context Engine v0

> 上游：`PRD.md` §18/§17/§22/§30/§31。契约即代码：本文件变更必须先于实现（FastAPI Pydantic 模型与此一一对应）。

## 0. 通用约定

- Base URL：`/api/v1`；内容类型 `application/json; charset=utf-8`。
- **身份（v0）**：请求头 `X-User-Id: U001`（display_id）。生产级 SSO/OIDC 明确不在 v0 范围（ADR-001）。
- **管理端点**：另需 `X-Admin-Token: $ECE_ADMIN_TOKEN`（/ingest、批量写）。
- 错误模型（RFC 7807 简化）：

```json
{"error": {"code": "permission_denied", "message": "U002 无权访问 PR001", "request_id": "ctx_..."}}
```

  code 枚举：`bad_request | not_found | permission_denied | resolution_ambiguous | insufficient_context | disabled_feature | internal`。
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

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /entities/{display_id} | 单实体（过权限；404=不存在或无权，响应一致以防探测） |
| GET | /entities?type=&q=&limit=&cursor= | 过滤查询（q 匹配 name/alias，过权限） |
| POST | /entities | 批量 upsert（Admin；走 Connector 归一化通道，禁止直插绕过 resolution） |
| GET | /entities/{id}/relationships?relation=&direction=out&as_of= | 关系查询（过权限 + temporal） |

## 4. Resolve（Entity Resolution 服务化）

### POST /api/v1/resolve

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

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /ingest/runs | `{"connector": "csv:suppliers", "params": {}}` → `{run_id}`；同步执行，v0 不做队列 |
| GET | /ingest/runs/{run_id} | 状态与 stats（created/updated/skipped/errors） |

Connector 契约（ARCHITECTURE §1）：`connect / discover_schema / fetch / normalize / sync`；新数据源 = 新 Connector 类 + ontology 映射声明，不改引擎。

## 8. Audit / Debugger

### GET /api/v1/audit/context/{request_id}

返回：request 头信息 + `items[]`（每项 kind/ref/source/decision/reason/score）+ agent 输出摘要（若有）。供 Debugger UI（Sprint 6）与 `scripts/export_audit.py` 使用。仅 management 部门或本人可查（过 Permission Engine）。

## 9. 健康

`GET /healthz`（进程存活）· `GET /readyz`（DB 连通 + migrations 版本一致 + LLM 端点可达（若配置））。

## 10. 版本化与兼容

- 破坏性变更升 `/api/v2`，v0 期间允许非破坏性字段新增。
- OpenAPI 由 FastAPI 自动生成（`/openapi.json`），CI 校验与 `API.md` 的端点清单一致（脚本 `scripts/check_api_docs.py`，Sprint 0 建立）。

