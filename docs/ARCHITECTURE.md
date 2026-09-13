# ARCHITECTURE — Enterprise Context Engine v0

> 上游：`PRD.md`（§8/§9/§15/§16/§19/§29/§31）。本文将 PRD 架构固化为可实现的设计；冲突时以 PRD 为准并提 ADR 修订。

## 1. 分层总览

```text
┌────────────────────────────────────────────────────────┐
│ Agent Layer — src/domain_packs/procurement              │
│   Procurement Agent（评估/建议，Level 0–1；无写回）      │
└──────────────────────┬─────────────────────────────────┘
                       │ 仅通过 Context API
┌──────────────────────▼─────────────────────────────────┐
│ Context API — src/ece/api                              │
│   /context /search /entities /relationships            │
│   /permissions/check /resolve /actions /ingest /audit  │
└──────────────────────┬─────────────────────────────────┘
┌──────────────────────▼─────────────────────────────────┐
│ Engine Core — src/ece/*                                │
│  context/     Context Spec 加载 + Assembly Pipeline    │
│               + Context Package + Provenance           │
│  permissions/ Permission Engine（唯一授权判定点）        │
│  entities/    Entity Store + Entity Resolution         │
│  relationships/ Relationship Store + Temporal Query    │
│  search/      Query Planner → FTS / vector / SQL / 关系 │
│  connectors/  Connector Interface + CSV/JSON/Docs 实现 │
│  actions/     Action Preview（execute 默认关闭）        │
│  audit/       请求级审计与 Context Trace                │
│  llm/         OpenAI 兼容客户端（唯一 LLM 出口）        │
└──────────────────────┬─────────────────────────────────┘
              ┌────────▼────────┐
              │ PostgreSQL 16   │ 结构化+关系+FTS+pgvector
              └────────▲────────┘
                       │ Connector Layer（拉取→归一化→映射→入库）
        CSV / JSON / 本地文档（data/demo 合成企业数据集）
```

**依赖方向铁律**：`domain_packs → ece.api/ece.context → ece.core`；`ece.core` 不 import 任何 domain_packs 模块（ADR-010）。

## 2. 核心运行时对象

### 2.1 Task → Context Specification（引擎最重要的抽象，PRD §40/41）

每个领域任务声明其 Required Context，YAML 存于领域包，运行时加载：

```yaml
# src/domain_packs/procurement/context_specs/evaluate_purchase_request.yaml
spec: evaluate_purchase_request
version: 1
root_entity: purchase_request
requires:
  user: true                 # 用户+部门+角色
  entities:                  # 沿关系图展开的目标实体
    - {type: supplier, via: "SELECTS", max_hops: 1}
    - {type: contract, via: "SELECTS>HAS_CONTRACT", max_hops: 2}
  relationships: [SUBMITTED_BY, BELONGS_TO, SELECTS, HAS_CONTRACT, SUBJECT_TO, HAS_APPROVAL]
  documents:
    - {doc_type: procurement_policy, match: "applies to dept & category"}
    - {doc_type: quote, match: "linked to PR"}
  structured_data:
    - historical_purchases   # 同品类近 N 笔（含价格）
    - approval_history
  temporal: {mode: current}  # current | as_of(date) | between(a,b)
  limits: {max_entities: 60, max_chunks: 30, max_rows: 200}
```

Assembly 完全由 spec 驱动——新任务/新领域 = 新 YAML（+必要的检索扩展），不改引擎。

### 2.2 Context Package（PRD §17）

结构化（非纯文本）返回给 Agent，每项携带 provenance：

```json
{
  "package_id": "ctx_01H...",
  "task": {"intent": "evaluate_purchase_request", "spec_version": 1},
  "user": {"id": "U001", "display": "张三", "roles": ["procurement_manager"], "department": "D01"},
  "entities": [{"ref": "PR001", "type": "purchase_request", "attrs": {}, "src": {}}],
  "relationships": [{"from": "PR001", "rel": "SELECTS", "to": "SUP001", "valid": ["2026-01-01", null], "src": {}}],
  "documents": [{"doc": "POLICY-2026-03", "chunk": 12, "text": "超过100万元需三家比价", "src": {}}],
  "business_data": [{"kind": "historical_purchase", "rows": [], "src": {}}],
  "denied": [{"ref": "CON009", "reason": "acl:department_denied"}],
  "sources": [],
  "metadata": {"generated_at": "", "as_of": null, "counts": {}}
}
```

`denied` 显式记录被权限过滤的对象——Agent 只知道"存在但不可见"，不知道内容（间接泄露评测的观测点）。

## 3. Context Assembly Pipeline（PRD §29 的 12 步，顺序不可变）

```text
1  Identify user          ← X-User-Id（v0）→ identity 加载
2  Resolve identity       → Person 实体解析（含别名表）
3  Determine permissions  → 计算 {user,roles,depts} 可见域（§5）
4  Resolve requested entities → Entity Resolution（别名/同名消歧，§6）
5  Retrieve relevant relationships → spec.relationships 限定，多跳 BFS，逐步权限过滤
6  Retrieve authorized documents → FTS/vector 候选 → classification+ACL 过滤
7  Retrieve structured data      → SQL 查询 → 行级权限过滤
8  Apply temporal constraints    → valid_from/valid_to 与 as_of 过滤
9  Rank context                  → spec required > 关系距离 > 检索分数；limits 截断
10 Build Context Package         → 结构化打包 + denied 列表
11 Record provenance             → 每项写 source{system,record_id,field|doc,page}
12 Return to Agent               → 同时写 audit（request_id、决策、sources、latency）
```

任何一步失败：fail-closed（返回错误或标记 insufficient_context），绝不降级为无权限过滤的宽松模式。

## 4. Query Planner 与检索（PRD §15）

```text
Query/Spec → Query Planner
   ├─ Keyword(FTS)   → doc_chunks.tsv（中文 simple+bigram 兜底，zhparser 可选）
   ├─ Vector         → doc_chunks.embedding（pgvector cosine, top-k 后过滤）
   ├─ Structured     → entities.attributes JSONB + 业务数据 SQL
   └─ Relationship   → relationships 多跳 SQL
        ↓ Entity Linking（命中文本 → canonical entity）
        ↓ Permission Filter（统一收口于 Permission Engine 之后）
        ↓ Merge & Rank → Context Assembly
```

## 5. Permission Engine（ADR-004）

- **模型**：subject（user/role/department）× object（entity/document）× effect（allow/deny），存 `acl_entries`；document 另有 `classification`（public/department/management/finance/procurement/confidential，PRD §28）。
- **判定顺序**：deny 优先 > user > role > department > classification 默认 > 默认 deny。
- **执行位置**：所有 Store 读方法以 `PermissionScope` 为必传参数；第 3 步算出后全程复用；SQL 层子查询过滤（不是取回后丢弃）。
- **间接泄露**：`denied` 只暴露 ref+reason；输出评测含"诱导泄露"用例（EVALUATION.md §3）。

## 6. Entity Resolution（PRD §12）

渐进流水线，每级可停：

```text
exact(source_id) → normalized_name → alias 表 → 规则（剥离"有限公司/（华南）"等后缀）
→ embedding 相似度（τ=0.92，以下进人工复核队列） → LLM 辅助（只产 candidate）
```

结果落 `entity_aliases`（canonical_id, source_system, source_ref, method, confidence）。
**LLM 猜测不得直接成为企业事实**；confidence < 0.9 一律进人工队列。

## 7. Temporal（PRD §14）

关系与 ACL 带 `valid_from/valid_to`（左闭右开）；实体属性变更走 `entity_revisions` 简表。
查询谓词：`current`（now ∈ [from,to)）/ `as_of(d)` / `between(a,b)`。

## 8. Procurement Agent（领域包内，PRD §19/20）

- 输入：User Question + Context Package（只此二者，不直连任何存储）。
- 组成：Role/Goal + 领域规则（比价阈值、审批链完整性、价格偏离带）+ LLM + 结构化输出 schema（conclusion / reasoning_summary / risks[] / recommendation / evidence[] / confidence）。
- **规则优先**：规则引擎产出确定性问题（如"金额触发比价但无比价记录"），LLM 负责综合表述与解释——与国产开源模型的友好负载分布一致（ADR-006）。
- 输出的每条 evidence 必须引用 package 内 source_id；评测校验引用真实性。

## 9. Action 安全（PRD §30）

| Level | 含义 | v0 |
|---|---|---|
| 0 | 只回答 | ✓ |
| 1 | 生成建议/草稿 | ✓ |
| 2 | Preview + 人工确认 | 仅 `/actions/preview` |
| 3 | 自动执行 | **关闭**（env kill-switch，代码级禁用） |

## 10. Observability 与 Context Debugger（PRD §31/32）

- `context_requests` + `context_items` 记录全链路（谁、什么意图、看到/被拒了什么、来自哪个 source、耗时、模型）。
- `/audit/context/{request_id}` 返回 trace；Debugger UI（Sprint 6）可视化 Query→Retrieval→Permission→Context→Agent→Answer。
- 日志不落敏感原文，仅 ref 与 hash。

## 11. 部署拓扑

```text
docker compose:
  api (uvicorn, 单进程) ── db (postgres:16 + pgvector)
  卷: ./data(只读合成数据) ./volumes/pg
无外网依赖：LLM 端点指向企业内 vLLM/Ollama；不回传任何遥测。
```

## 12. 未来扩展点（现在不做，ADR 留触发条件）

Neo4j/Memgraph（ADR-003）、OpenSearch/Redis（ADR-009）、多领域包并行（ADR-010）、Glean Context Adapter（PRD §39：Context API 之下可替换数据面，Agent 层零改动）。

