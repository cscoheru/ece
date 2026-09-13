# Enterprise Context Engine
## 独立产品研发 PRD / Technical Product Plan v0.1

**项目代号：** ECE（Enterprise Context Engine）  
**版本：** v0.1  
**文档性质：** Product + Architecture + Engineering Plan  
**目标：** 构建一个独立于具体 LLM / Agent Framework 的企业 Context 基础设施，使 AI Agent 能够理解企业中的“人、组织、权限、业务对象、文档、系统、关系和时间”，并在权限约束下完成企业级任务。

---

# 1. 项目背景

当前企业 AI 应用存在一个核心问题：

> LLM 本身已经具备很强的语言理解和推理能力，但它并不了解一个具体企业。

普通 RAG 主要解决：

> “企业有哪些文档，哪些文档与这个问题相关？”

Enterprise Context 要进一步解决：

> “这个用户是谁？他属于哪个组织？他有什么权限？这个业务对象是什么？它和哪些人、部门、合同、政策、历史记录有关？这些信息在什么时间有效？AI 当前到底应该看到哪些信息？”

因此，Enterprise Context Engine 不是一个简单的：

- Vector Database
- Knowledge Base
- RAG
- Knowledge Graph
- Chatbot
- Agent Framework

而是一层位于企业数据系统和 Agent 之间的：

> **Enterprise Semantic + Permission + Relationship + Temporal Context Layer**

核心目标是让 Agent 从“会回答问题的模型”变成“理解企业环境并能够安全执行任务的企业 Agent”。

---

# 2. Product Vision

## 2.1 长期愿景

构建一个：

> **让 AI 理解企业世界的 Context Infrastructure。**

最终形成：

```text
Enterprise Systems
        ↓
Enterprise Context Engine
        ↓
Domain Context
        ↓
Domain Agents
        ↓
Enterprise AI
```

企业不需要一次性把所有业务交给 AI。

而是：

```text
Search
  ↓
Answer
  ↓
Suggest
  ↓
Review
  ↓
Action
  ↓
Cross-system Action
  ↓
Enterprise AI
```

通过逐步扩大 AI 的信息访问范围和行动权限，使企业能够在不破坏原有组织与信息边界的情况下逐步获得 AI 价值。

---

# 3. 产品原则

## P1. Context First

不以 Agent 数量作为核心产品指标。

核心能力是：

> Agent 能否获得正确、完整、权限正确、时间正确的企业 Context。

---

## P2. Permission Before Intelligence

权限判断必须发生在 LLM Context Assembly 之前。

错误架构：

```text
全部企业数据
      ↓
LLM
      ↓
“请不要回答没有权限的信息”
```

正确架构：

```text
User Identity
      ↓
Permission Engine
      ↓
Authorized Data
      ↓
Context Assembly
      ↓
LLM
```

LLM 不负责决定用户是否有权访问数据。

---

## P3. Enterprise Context ≠ Vector RAG

不同信息使用不同检索方式：

```text
Document
    → Keyword / Full Text / Vector

Entity
    → Entity Resolution

Relationship
    → Graph / Relational Query

Business Data
    → Structured Query

Permission
    → ACL / Policy

Time
    → Temporal Query
```

最后统一进入 Context Assembly。

---

## P4. Domain First

第一版不做完整 Enterprise Context。

先做：

> Procurement Context

通过一个真实业务场景验证技术架构。

成功后再抽象成 Enterprise Context。

---

## P5. Platform Independent

产品不能从架构层面绑定 Glean、OpenAI、Claude、DeepSeek、Qwen 或任何单一 Agent Framework。

未来可以：

```text
                 ┌─ Glean
                 ├─ OpenAI
Agent Layer ← Context Adapter
                 ├─ 自建 Runtime
                 └─ Other Platforms
```

Context Engine 必须保持独立。

---

# 4. MVP 定义

## 4.1 MVP 名称

**Procurement Intelligence Context**

第一版不是：

“企业 AI 平台”。

而是：

> **一个能够理解采购业务上下文，并为 Procurement Agent 提供可信 Context 的 Engine。**

---

# 5. MVP 用户场景

核心场景：

> “这个采购申请是否合理？”

例如：

```text
采购申请：
A 部门申请采购 1,000 台设备

供应商：
供应商 X

报价：
1,280 元 / 台

AI 需要判断：
这个报价是否合理？
```

Context Engine 不应该只搜索：

“采购制度”。

而应该组装：

```text
User
Department
Role
Permission

Purchase Request
Product
Quantity
Supplier
Current Quote

Historical Purchase
Historical Price

Supplier
Supplier History
Contract

Procurement Policy
Approval Rules

Similar Purchase Requests
Approval History
```

最终 Agent 才能判断。

---

# 6. MVP 功能范围

## 6.1 必须实现

### A. Identity

支持：

- User
- Organization
- Department
- Role

---

### B. Entity

支持：

- Person
- Organization
- Department
- Supplier
- Product
- PurchaseRequest
- Contract
- Policy
- Approval
- Document

---

### C. Relationship

支持：

```text
Person MEMBER_OF Department
Person HAS_ROLE Role
Department BELONGS_TO Organization

PurchaseRequest SUBMITTED_BY Person
PurchaseRequest BELONGS_TO Department
PurchaseRequest SELECTS Supplier
PurchaseRequest CONTAINS Product

Supplier HAS_CONTRACT Contract
PurchaseRequest REFERENCES Contract

PurchaseRequest SUBJECT_TO Policy
PurchaseRequest HAS_APPROVAL Approval
```

---

### D. Entity Resolution

例如：

```text
张三
张经理
张总
张三（采购部）
```

能够识别是否为同一 Person。

同时支持：

```text
无限极
Infinite
Infinite China
无限极（中国）
```

实体归一。

---

### E. Permission

至少支持：

- User ACL
- Department ACL
- Role ACL
- Document ACL
- Entity ACL

必须实现：

> Unauthorized data never enters the LLM context.

---

### F. Search

支持：

1. Keyword Search
2. Semantic Search
3. Entity Search
4. Structured Query
5. Relationship Query

---

### G. Context Assembly

核心 API：

```http
POST /context
```

输入：

```json
{
  "user_id": "U001",
  "intent": "evaluate_purchase_request",
  "entities": [
    {
      "type": "purchase_request",
      "id": "PR001"
    }
  ]
}
```

输出：

```json
{
  "user_context": {},
  "organization_context": {},
  "entity_context": {},
  "relationship_context": {},
  "policy_context": {},
  "historical_context": {},
  "permission_context": {},
  "sources": []
}
```

---

### H. Agent

第一版只做：

**Procurement Intelligence Agent**

支持：

- 采购申请分析
- 供应商分析
- 报价合理性分析
- 政策匹配
- 历史采购比较
- 风险提示
- 证据引用

---

### I. Action

MVP 只做低风险 Action：

- 生成审核意见
- 生成采购分析报告
- 生成审批建议

暂不直接执行：

- 下采购订单
- 修改 ERP 数据
- 支付
- 删除数据

---

# 7. 明确不做的事情

v0.1 不做：

- 全企业数据接入
- 十几个企业系统 Connector
- 完整 ERP
- 完整 OA
- 完整 CRM
- 完整 HR 系统
- 通用 Agent Marketplace
- 多租户商业化平台
- 完整 BI
- 自动审批
- 自动付款
- 自动修改核心业务数据
- Neo4j 大型知识图谱
- Kubernetes
- 微服务化
- 自研大模型
- Fine-tuning

核心原则：

> **先证明 Context Engine，而不是证明自己可以堆一个企业软件。**

---

# 8. 系统总体架构

```text
┌───────────────────────────────────────────────┐
│                 Agent Layer                   │
│                                               │
│ Procurement Agent / Future Domain Agents     │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────┐
│                Context API                    │
│                                               │
│ /context                                      │
│ /search                                       │
│ /entities                                     │
│ /relationships                                │
│ /permissions                                  │
│ /actions                                      │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────┐
│            Enterprise Context Engine           │
│                                               │
│ Context Assembly                              │
│ Entity Resolution                             │
│ Relationship Engine                           │
│ Permission Engine                             │
│ Temporal Context                              │
│ Query Planner                                 │
└──────────────┬──────────────┬─────────────────┘
               │              │
               ▼              ▼
       ┌─────────────┐  ┌───────────────┐
       │ Search Layer│  │ Structured DB │
       │             │  │               │
       │ BM25        │  │ PostgreSQL    │
       │ Vector      │  │ Relations     │
       └──────┬──────┘  └───────┬───────┘
              │                  │
              └────────┬─────────┘
                       ▼
┌───────────────────────────────────────────────┐
│             Connector Layer                   │
│                                               │
│ CSV / Excel / API / Mock ERP / Mock OA       │
│ Documents / Database                         │
└───────────────────────────────────────────────┘
```

---

# 9. 核心模块

## 9.1 Connector Layer

Connector 的职责：

```text
Source System
     ↓
Extract
     ↓
Normalize
     ↓
Transform
     ↓
Entity Mapping
     ↓
Context Store
```

MVP Connector：

1. CSV
2. JSON
3. REST API
4. Local Documents

暂不要求连接真实 ERP。

必须设计 Connector Interface：

```python
class Connector:
    def connect(self):
        pass

    def discover_schema(self):
        pass

    def fetch(self):
        pass

    def normalize(self):
        pass

    def sync(self):
        pass
```

未来：

```text
ERPConnector
OAConnector
CRMConnector
HRConnector
KMConnector
FeishuConnector
WeComConnector
```

---

# 10. Unified Entity Model

核心 Entity：

```text
Person
Organization
Department
Role
Permission

Document
Policy

Supplier
Product
Contract

PurchaseRequest
PurchaseOrder
Approval
Task

System
Application
```

每一个 Entity 至少包含：

```json
{
  "id": "SUP001",
  "type": "supplier",
  "name": "供应商A",
  "source_system": "ERP",
  "source_id": "12345",
  "attributes": {},
  "created_at": "",
  "updated_at": ""
}
```

---

# 11. Relationship Model

Relationship 必须是一等对象。

例如：

```json
{
  "source": "SUP001",
  "relation": "HAS_CONTRACT",
  "target": "CON001",
  "valid_from": "2026-01-01",
  "valid_to": null,
  "source_system": "ERP"
}
```

支持：

- source
- relation
- target
- validity
- provenance
- confidence

---

# 12. Entity Resolution

企业中最大的实际问题之一是：

> 同一个东西在不同系统里名字不同。

例如：

```text
ERP：
Supplier ID = 10028

OA：
供应商名称 = XX科技有限公司

合同系统：
XX科技

财务系统：
XX科技有限公司（华南）
```

Context Engine 必须建立：

```text
Canonical Entity
       ↑
 ┌─────┼─────┐
ERP    OA    Finance
```

MVP 可以使用：

```text
Exact Match
+
Normalized Name
+
Alias
+
Rule
+
Embedding Similarity
+
LLM assisted resolution
```

但最终必须保留：

```text
canonical_id
source_id
resolution_method
confidence
```

不能让 LLM 的猜测直接成为企业事实。

---

# 13. Permission Engine

这是产品最重要的安全边界之一。

原则：

> Permission enforcement must happen before context assembly.

流程：

```text
User
 ↓
Identity
 ↓
Role
 ↓
Department
 ↓
ACL
 ↓
Authorized Entities/Documents
 ↓
Context Retrieval
 ↓
LLM
```

MVP 支持：

```text
User-level ACL
Department-level ACL
Role-level ACL
Document ACL
Entity ACL
```

必须测试：

### Test 1

用户 A 可以查看：

```text
采购申请 PR001
```

用户 B 不可以。

Agent 给 A 和 B 提出相同问题。

结果：

```text
A → 可以得到 PR001 Context

B → PR001 不得进入 Context
```

不能依靠 Prompt 防止泄露。

---

# 14. Temporal Context

企业数据不是静态的。

例如：

```text
2025：
张三 → 采购经理

2026：
李四 → 采购经理
```

如果用户问：

> “2025 年这个采购是谁审批的？”

不能返回当前组织关系。

因此关系需要：

```text
valid_from
valid_to
```

Context Query 必须支持：

```text
current
as_of
between
```

例如：

```json
{
  "as_of": "2025-12-31"
}
```

---

# 15. Search Architecture

不要建立单一 Retrieval。

采用：

```text
                 User Query
                     ↓
               Query Planner
                     ↓
        ┌────────────┼────────────┐
        ↓            ↓            ↓
    Keyword       Vector       Structured
        ↓            ↓            ↓
      Docs         Docs        Business Data
        └────────────┼────────────┘
                     ↓
               Entity Linking
                     ↓
               Relationship
                     ↓
              Context Assembly
```

---

# 16. Context Assembly

Context Assembly 是整个系统的核心。

输入：

```text
User
Intent
Entities
Time
Permissions
```

例如：

```json
{
  "user_id": "U001",
  "intent": "evaluate_purchase_request",
  "entity_ids": ["PR001"]
}
```

Engine 自动展开：

```text
PR001
 ↓
Department
 ↓
Requester
 ↓
Supplier
 ↓
Product
 ↓
Contract
 ↓
Policy
 ↓
Historical Purchase
 ↓
Approval History
```

同时执行：

```text
Permission Filtering
Temporal Filtering
Relevance Ranking
Source Validation
```

最终形成：

```text
Context Package
```

---

# 17. Context Package

Context Package 不应该只是文本。

建议结构：

```json
{
  "task": {
    "intent": "evaluate_purchase_request"
  },

  "user": {},

  "entities": [],

  "relationships": [],

  "documents": [],

  "business_data": [],

  "policies": [],

  "history": [],

  "permissions": {},

  "sources": [],

  "metadata": {
    "generated_at": "",
    "context_version": ""
  }
}
```

这样 Agent 可以自己决定如何使用 Context。

---

# 18. Context API

核心接口：

```http
POST /context
```

获取任务 Context。

---

```http
GET /entities/{id}
```

获取实体。

---

```http
GET /entities/{id}/relationships
```

获取实体关系。

---

```http
POST /search
```

执行统一搜索。

---

```http
POST /permissions/check
```

检查权限。

---

```http
POST /actions/preview
```

生成 Action Preview。

---

```http
POST /actions/execute
```

执行经过授权的 Action。

MVP 中 `/execute` 默认关闭。

---

# 19. Agent Architecture

Agent 不应该自己去访问所有数据库。

错误：

```text
Agent
 ├─ ERP
 ├─ OA
 ├─ CRM
 ├─ HR
 └─ Database
```

正确：

```text
Agent
   ↓
Context API
   ↓
Context Engine
   ↓
Enterprise Systems
```

这样可以形成清晰的安全边界。

---

# 20. Procurement Agent

Agent 输入：

```text
User Question
+
Context Package
```

Agent 输出：

```json
{
  "conclusion": "",
  "reasoning_summary": "",
  "risks": [],
  "recommendation": "",
  "evidence": [],
  "confidence": 0
}
```

注意：

Agent 不需要输出隐藏 Chain of Thought。

系统只保留：

- 可验证结论
- 简明理由
- Evidence
- Source
- Confidence

---

# 21. 示例

用户：

> “PR001 这个采购申请合理吗？”

Context Engine：

```text
User:
采购部经理

Purchase Request:
采购 1,000 台设备

Supplier:
供应商 A

Current Price:
1280

Historical Price:
1150

Market Reference:
1180

Policy:
超过 100 万需要三家供应商比价

Approval:
当前申请尚未完成比价
```

Agent：

```text
结论：
存在采购价格偏高风险。

主要依据：
1. 当前报价高于历史采购价格；
2. 高于系统中的参考价格；
3. 当前采购金额触发比价要求；
4. 当前申请尚未发现完整比价记录。

建议：
补充供应商比价材料后再进入下一审批阶段。
```

每一项都应该能够回溯到 Source。

---

# 22. Evidence / Provenance

所有关键 Context 必须保留来源：

```json
{
  "fact": "采购金额为128万元",
  "source": {
    "system": "ERP",
    "record_id": "PR001",
    "field": "total_amount"
  }
}
```

文档：

```json
{
  "fact": "超过100万元需要三家比价",
  "source": {
    "document_id": "POLICY-2026-03",
    "page": 12
  }
}
```

目标：

> **Every important AI conclusion should be traceable to enterprise evidence.**

---

# 23. Evaluation Framework

Evaluation 不作为项目最后补充，而是 MVP 的核心模块。

建立：

```text
Context Evaluation
+
Agent Evaluation
```

## 23.1 Entity Accuracy

测试：

```text
“XX科技”
“XX科技有限公司”
“XX科技（广州）有限公司”
```

是否正确归一。

---

## 23.2 Permission Accuracy

测试：

```text
Authorized → visible

Unauthorized → invisible
```

核心指标：

> Unauthorized Context Exposure = 0

这是硬指标。

---

## 23.3 Retrieval Accuracy

测试：

> 是否找到完成任务真正需要的数据。

---

## 23.4 Relationship Accuracy

例如：

```text
Supplier → Contract
PurchaseRequest → Supplier
Employee → Department
```

不能错连。

---

## 23.5 Temporal Accuracy

测试：

```text
as_of 2025
```

是否使用 2025 年有效关系。

---

## 23.6 Context Completeness

对于：

```text
evaluate_purchase_request
```

定义 Required Context：

```text
User
Department
Purchase Request
Supplier
Product
Price
Policy
Historical Data
Approval
```

缺失关键 Context 时：

> Agent 应该明确表示信息不足，而不是猜测。

---

## 23.7 Agent Accuracy

最终测试：

```text
Question
→ Context
→ Agent
→ Conclusion
```

使用人工构造 Ground Truth。

---

# 24. MVP 技术栈

建议：

```text
Python 3.12+

FastAPI
Pydantic

PostgreSQL
pgvector

OpenSearch / Elasticsearch

Redis

SQLAlchemy

pytest

Docker Compose
```

LLM：

```text
OpenAI-compatible API
```

支持：

```text
GPT
Claude
DeepSeek
Qwen
其他兼容模型
```

Agent Runtime：

> MVP 自建轻量 Runtime。

暂时不依赖复杂 Agent Framework。

---

# 25. Graph 技术策略

v0.1：

> **不用 Neo4j。**

关系数据先存在 PostgreSQL：

```text
entities
relationships
```

通过 SQL / recursive query 实现关系查询。

原因：

第一版真正需要验证的是：

> Context Model 是否成立。

而不是：

> Graph Database 是否先进。

当出现：

- 多跳关系大量增加
- 图查询复杂
- 性能瓶颈

再考虑：

```text
Neo4j
Memgraph
其他 Graph DB
```

---

# 26. Repository Structure

建议：

```text
enterprise-context-engine/

├── README.md
├── CLAUDE.md
├── AGENTS.md
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── SECURITY.md
│   ├── API.md
│   ├── EVALUATION.md
│   └── ADR/
│
├── src/
│   ├── api/
│   ├── context/
│   ├── entities/
│   ├── relationships/
│   ├── permissions/
│   ├── search/
│   ├── connectors/
│   ├── temporal/
│   ├── agents/
│   └── actions/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── evaluation/
│
├── data/
│   ├── demo/
│   ├── entities/
│   ├── documents/
│   └── policies/
│
├── scripts/
│
├── docker/
│
└── docker-compose.yml
```

---

# 27. Demo Dataset

第一阶段不等待真实企业数据。

建立一个 Synthetic Enterprise：

```text
Enterprise:
Demo Corporation

Departments:
Procurement
Finance
IT
Sales
HR

Users:
20+

Suppliers:
50+

Products:
100+

Purchase Requests:
200+

Contracts:
50+

Policies:
20+

Approval Records:
500+

Documents:
500+
```

数据必须包含：

- 正常案例
- 异常案例
- 权限边界
- 同名人员
- 同供应商不同名称
- 历史组织变更
- 多部门采购
- 不完整资料

---

# 28. Security Test Dataset

必须专门建立：

```text
Public
Department
Management
Finance
Procurement
Confidential
```

例如：

```text
User A:
Procurement

User B:
Finance

User C:
Management
```

测试：

```text
A 是否看到 Finance 数据？

B 是否看到 Procurement 数据？

普通员工是否看到 Management 文档？

Agent 是否因为推理而间接泄露不可见信息？
```

最后一项尤其重要。

---

# 29. Context Assembly Policy

Context Engine 必须遵守：

```text
1. Identify user
2. Resolve identity
3. Determine permissions
4. Resolve requested entities
5. Retrieve relevant relationships
6. Retrieve authorized documents
7. Retrieve structured data
8. Apply temporal constraints
9. Rank context
10. Build Context Package
11. Record provenance
12. Return to Agent
```

顺序不能随意改变。

---

# 30. Action Safety

Agent 的 Action 分三级：

### Level 0

只回答。

### Level 1

生成建议 / 草稿。

### Level 2

需要用户确认后执行。

### Level 3

自动执行。

MVP：

```text
Level 0 ✓
Level 1 ✓
Level 2 Preview
Level 3 ✗
```

---

# 31. Observability

所有 Context 请求记录：

```text
request_id
user_id
intent
entities
retrieval sources
permission decisions
context size
LLM model
latency
result
```

不能记录不必要的敏感原文。

核心目的：

> 出问题以后能够知道 Agent 为什么看到这些信息。

---

# 32. Context Debugger

建议 MVP 必须有一个简单 Web UI：

```text
User:
张三

Intent:
evaluate_purchase_request

Entity:
PR001
```

显示：

```text
User Context
✓

Permission
✓

Purchase Request
✓

Supplier
✓

Contract
✓

Policy
✓

Historical Data
✓

Documents
✓
```

点击某一项：

```text
为什么这个 Context 被加入？
来源是什么？
权限是什么？
时间范围是什么？
```

这是非常重要的开发工具。

未来甚至可以成为产品能力。

---

# 33. MVP UI

只需要三个页面：

## Page 1 — Ask

```text
Ask Enterprise AI

[这个采购申请合理吗？]

        ↓

Answer
Evidence
Risk
Recommendation
```

---

## Page 2 — Context Explorer

```text
User
Organization
Entity
Relationship
Document
Permission
Timeline
```

---

## Page 3 — Context Debugger

查看：

```text
Query
→ Retrieval
→ Permission
→ Context
→ Agent
→ Answer
```

---

# 34. Development Roadmap

## Phase 0 — Architecture

目标：

建立：

```text
Entity Model
Relationship Model
Permission Model
Context API
```

输出：

```text
docs/
tests/
schema/
```

不做 Agent。

---

# Phase 1 — Context Core

实现：

- Entity Store
- Relationship Store
- Permission Engine
- Entity Resolution
- Context Assembly

验收：

```text
POST /context
```

能够返回完整 Procurement Context。

---

# Phase 2 — Retrieval

加入：

- PostgreSQL
- pgvector
- OpenSearch
- Hybrid Search

实现：

```text
Keyword
+
Semantic
+
Structured
+
Relationship
```

---

# Phase 3 — Procurement Agent

实现：

```text
Question
 ↓
Intent
 ↓
Context
 ↓
Agent
 ↓
Answer
 ↓
Evidence
```

---

# Phase 4 — Evaluation

建立至少：

```text
100 Context Tests

50 Permission Tests

50 Entity Resolution Tests

50 Agent Tests
```

形成 Benchmark。

---

# Phase 5 — Context Debugger

建立 Web UI。

实现：

```text
Context Trace
Permission Trace
Source Trace
Agent Trace
```

---

# Phase 6 — Action Preview

实现：

```text
Agent Recommendation
        ↓
Action Preview
        ↓
Human Confirmation
```

暂不自动执行。

---

# 35. MVP 验收标准

## 必须达到

### Context

> 90%+ 核心测试任务能够获得正确 Required Context。

### Entity Resolution

> 核心实体归一准确率 ≥ 95%。

### Permission

> Unauthorized Context Exposure = 0。

这是硬门槛。

### Provenance

> 关键事实 100% 有 Source。

### Temporal

> 核心历史关系测试准确率 ≥ 95%。

### Agent

> 基于标准测试集，核心采购分析任务达到可人工接受水平。

注意：

Agent 准确率不是第一阶段唯一指标。

---

# 36. Product Success Criteria

MVP 成功不是：

> “做出了一个很酷的 AI Chat。”

而是证明以下命题：

### Hypothesis 1

Agent 能通过 Context Engine 理解业务对象。

### Hypothesis 2

Agent 可以在权限边界内工作。

### Hypothesis 3

Context 比单纯 RAG 能显著改善企业任务完成质量。

### Hypothesis 4

Context Engine 可以脱离具体 LLM。

### Hypothesis 5

Procurement Context 可以抽象成未来其他 Domain Context 的基础。

---

# 37. 下一阶段扩展

Procurement Context 成功以后：

```text
Procurement Context
        ↓
Enterprise Context Core
        ↓
┌────────────┬─────────────┬────────────┐
│            │             │
KM Context   HR Context    Sales Context
│            │             │
Knowledge    People        Customer
Policy       Organization  Opportunity
Document     Role          Contract
```

最终：

```text
Enterprise Context
        ↓
Domain Agents
        ↓
Enterprise Agent Layer
```

---

# 38. 产品商业化方向

长期可以形成三层：

## Layer 1 — Context Infrastructure

企业部署：

```text
Enterprise Context Engine
```

---

## Layer 2 — Domain Context

例如：

```text
Procurement Intelligence
Compliance Intelligence
Knowledge Intelligence
Sales Intelligence
```

---

## Layer 3 — Agents

例如：

```text
Procurement Agent
Contract Agent
Compliance Agent
Knowledge Agent
Management Assistant
```

因此商业模式不应该只是：

> “帮企业做一个 Agent。”

而可以逐渐变成：

> **Enterprise Context Infrastructure + Domain Intelligence + Agents**

---

# 39. 与 Glean 的关系

独立产品架构必须允许：

```text
                    Domain Agent
                         │
                         ▼
                 Context Adapter
                   /           \
                  /             \
             Glean              ECE
              Context          Context
```

如果未来 Glean 合作：

```text
Glean
 ├─ Enterprise Search
 ├─ Identity
 ├─ Connectors
 └─ Enterprise Context
          ↓
      Domain Context
          ↓
        Agent
```

如果不合作：

```text
ECE
 ├─ Connectors
 ├─ Identity
 ├─ Permissions
 ├─ Search
 ├─ Entity
 ├─ Relationship
 └─ Context
          ↓
      Domain Context
          ↓
        Agent
```

因此：

> **现在独立研发并不会浪费。**

反而可以让未来是否使用 Glean 变成一个技术选择，而不是战略依赖。

---

# 40. 最重要的技术边界

第一阶段不要试图解决：

> “企业所有数据如何统一？”

真正需要解决的是：

> “为了完成一个明确的企业任务，AI 需要哪些 Context？”

所以 Context Assembly 应该从：

```text
Task
```

倒推：

```text
Required Entities
Required Relationships
Required Documents
Required Structured Data
Required Permissions
Required Time
```

形成：

> **Task → Context Specification**

例如：

```yaml
task: evaluate_purchase_request

required_context:
  - user
  - department
  - purchase_request
  - supplier
  - product
  - current_price
  - historical_price
  - procurement_policy
  - contract
  - approval_history
```

这是未来非常重要的产品抽象。

---

# 41. Context Specification

最终每一个 Domain Agent 都可以声明自己的 Context Requirements。

例如：

```yaml
agent:
  name: procurement_intelligence

tasks:

  evaluate_purchase_request:

    entities:
      - PurchaseRequest
      - Supplier
      - Product

    relationships:
      - submitted_by
      - belongs_to
      - selects
      - has_contract

    documents:
      - ProcurementPolicy

    structured_data:
      - historical_purchase
      - historical_price

    temporal:
      required: true

    permission:
      required: true

    provenance:
      required: true
```

Context Engine 自动执行。

这会成为 ECE 的核心抽象之一。

---

# 42. 核心竞争壁垒假设

不要把壁垒定义为：

```text
LLM
RAG
Vector DB
Agent Framework
```

这些都会快速商品化。

真正值得积累的是：

```text
Enterprise Entity Model
+
Entity Resolution
+
Permission Model
+
Relationship Model
+
Temporal Model
+
Context Specification
+
Context Evaluation
+
Domain Context
+
Enterprise Workflow
```

尤其是：

> **Context Evaluation Dataset**

如果未来积累了大量真实企业任务：

```text
Task
→ Required Context
→ Actual Context
→ Agent Result
→ Human Evaluation
```

就能够形成自己的 Context Benchmark。

---

# 43. 第一版完成后的判断标准

不要问：

> “这个产品是不是已经可以卖了？”

而问五个问题：

### Q1
如果把 LLM 从 GPT 换成 Claude，Context Engine 是否仍然工作？

### Q2
如果把 Procurement Agent 换成 Contract Agent，Context Engine 是否仍然工作？

### Q3
如果增加一个新的企业系统，是否只需要增加 Connector？

### Q4
如果一个用户没有权限访问某条信息，Agent 是否绝对无法通过 Context 获得它？

### Q5
如果 AI 给出一个判断，我们能否解释：

> “它为什么得到这个结论？”

如果五个问题都能回答“是”，说明 ECE 的底座基本成立。

---

# 44. Claude Code / Codex 执行原则

开发 Agent 必须遵循：

### Rule 1

先读：

```text
CLAUDE.md
docs/PRD.md
docs/ARCHITECTURE.md
```

再修改代码。

### Rule 2

每完成一个模块：

```text
Implement
→ Test
→ Evaluate
→ Document
```

### Rule 3

禁止为了“让 Demo 跑起来”绕过：

- Permission
- Provenance
- Entity Model
- Context API

### Rule 4

禁止提前引入复杂基础设施。

### Rule 5

所有重要架构决定写入 ADR。

---

# 45. ADR 初始列表

建立：

```text
ADR-001
Why Enterprise Context Engine?

ADR-002
Why PostgreSQL as initial Entity/Relationship Store?

ADR-003
Why not Neo4j in MVP?

ADR-004
Permission Before Context Assembly

ADR-005
Context API as Agent Boundary

ADR-006
LLM Provider Independence

ADR-007
Procurement Context as First Domain

ADR-008
Synthetic Enterprise Dataset for MVP
```

---

# 46. 第一阶段具体任务 Backlog

## Sprint 1

```text
[ ] 初始化 repository
[ ] Docker Compose
[ ] PostgreSQL
[ ] FastAPI
[ ] Pydantic
[ ] Entity schema
[ ] Relationship schema
[ ] Permission schema
[ ] Migration
```

---

## Sprint 2

```text
[ ] Entity CRUD
[ ] Relationship CRUD
[ ] User identity
[ ] Department
[ ] Role
[ ] ACL
[ ] Entity Resolution
```

---

## Sprint 3

```text
[ ] Context Specification
[ ] Context Assembly
[ ] /context API
[ ] Provenance
[ ] Temporal Context
```

---

## Sprint 4

```text
[ ] Document ingestion
[ ] Vector search
[ ] Keyword search
[ ] Structured retrieval
[ ] Hybrid retrieval
```

---

## Sprint 5

```text
[ ] Procurement Agent
[ ] Evidence generation
[ ] Evaluation dataset
[ ] Agent evaluation
```

---

## Sprint 6

```text
[ ] Context Debugger
[ ] Trace
[ ] Permission visualization
[ ] Source visualization
[ ] Demo
```

---

# 47. Definition of Done

一个模块只有满足以下条件才算完成：

```text
Code
✓

Unit Test
✓

Integration Test
✓

Security Test
✓

Evaluation
✓

Documentation
✓

Example
✓
```

尤其：

> **没有测试的 Context Engine 功能不算完成。**

---

# 48. 最终 MVP Demo

最终 Demo 应该可以现场演示：

```text
用户登录
   ↓
提出问题：

“PR001 这个采购申请合理吗？”
   ↓
系统识别用户
   ↓
检查权限
   ↓
识别 PR001
   ↓
找到 Supplier
   ↓
找到 Product
   ↓
找到 Contract
   ↓
找到 Procurement Policy
   ↓
查询历史采购
   ↓
组装 Context
   ↓
Procurement Agent
   ↓
生成判断
   ↓
展示 Evidence
   ↓
展示 Context Trace
```

然后做一个非常关键的 Demo：

```text
换成没有权限的用户
        ↓
再次提出同样问题
        ↓
Context Engine
        ↓
无法取得受保护数据
        ↓
Agent 明确说明信息不足
```

这个 Demo 的价值远高于一个普通的 Chatbot Demo。

---

# 49. 项目最终定位

ECE v0.1 不应该宣传为：

> “又一个企业 AI Agent 平台。”

更准确的技术定位是：

> **Enterprise Context Infrastructure for AI Agents**

中文：

> **面向企业 AI Agent 的 Context 基础设施。**

核心价值：

> **让 Agent 在企业既有组织、权限、业务和信息边界内理解企业，并逐步从 Search 走向 Answer、Suggest 和 Action。**

---

# 50. 下一阶段战略

MVP 不追求“大”。

路线应该严格遵循：

```text
                Enterprise Context Engine
                         │
                         ▼
                Procurement Context
                         │
                         ▼
                Procurement Agent
                         │
                         ▼
                 Real Enterprise
                         │
                         ▼
                  Real User Tasks
                         │
                         ▼
                   Evaluation
                         │
                         ▼
                 Context Refinement
                         │
                         ▼
                 Domain Expansion
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
         Knowledge    Contract     Compliance
             │           │           │
             └───────────┼───────────┘
                         ▼
                Enterprise Context
                         │
                         ▼
                  Enterprise AI
```

**第一阶段唯一目标：**

> **证明“Context Engine → Domain Agent”能够比普通 RAG + LLM 更可靠地完成一个真实企业任务。**

只要这个命题成立，后面的 Enterprise Context、Domain Agent、企业 AI 平台才有继续投入的理由。