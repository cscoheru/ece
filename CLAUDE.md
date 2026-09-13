# CLAUDE.md — Enterprise Context Engine (ECE)

> 本文件是 ECE 代码仓库内开发代理（Claude Code / Codex / 人类开发者）的**最高治理文件**。
> 商业层战略约束见仓库根 `../CLAUDE.md` 与 `../RED_TEAM_REVIEW.md`（v3）；两者冲突时，**以本文件为准于代码实现层面，以根文件为准于商业战略层面**。

## 1. 项目是什么

ECE = 面向企业 AI Agent 的 **Context 基础设施**（Entity / Relationship / Permission / Temporal / Context Assembly）。
v0 通过一个垂直领域包（**Procurement Pack**）验证架构，而不是做通用平台。

```text
Agent Layer（领域包，v0 仅 Procurement Agent）
        ↓ 只依赖
Context API（/context /search /entities /permissions /actions）
        ↓
Engine Core（Assembly / Resolution / Permission / Temporal / Query Planner）
        ↓
PostgreSQL（结构化+关系+FTS+pgvector）
        ↓
Connector Layer（v0: CSV / JSON / 本地文档；不连真实 ERP）
```

**需求唯一事实来源：`docs/PRD.md`**（由仓库根 `Enterprise Context Engine.md` 原样复制）。
工程文件优先级：`CLAUDE.md` → `docs/PRD.md` → `docs/ARCHITECTURE.md` → `docs/DATA_MODEL.md` → `docs/API.md` → `docs/EVALUATION.md` → `TASKS.md` → `docs/adr/`。

## 2. 五条不可违反的工程铁律（违反任何一条 = 返工）

1. **Permission Before Intelligence**：权限过滤必须发生在 Context Assembly 之前，由 Permission Engine 在数据访问层强制执行。禁止用 prompt 让 LLM"不要泄露"来替代。`Unauthorized Context Exposure = 0` 是 CI 硬门槛。
2. **禁止为 Demo 绕过核心抽象**：任何功能（包括 Demo）不得绕过 Permission / Provenance / Entity Model / Context API 四件套直接读库或硬编码结果。
3. **垂直纪律**：Engine Core 只实现"Procurement 任务 + 测试用例"明确需要的横向能力。任何"以后可能有用"的通用化（多租户、通用 Connector 平台、图数据库、消息队列、微服务、K8s、自研 Runtime）一律不做，除非 ADR 明确推翻。
4. **领域包隔离**：`src/domain_packs/procurement/` 是唯一允许出现采购业务逻辑的位置；`src/ece/`（引擎核心）**零采购 import**。这条保证客户访谈结论若指向其他领域（审计/合规），换领域包而不重写引擎。
5. **LLM 不可知**：一切 LLM 调用走 OpenAI 兼容端点，由环境变量配置（见 §4）。禁止在任何代码中出现具体厂商 SDK 依赖或模型名硬编码。LLM 的猜测不得直接写入企业事实（Entity Resolution 的 LLM 结果只产生 candidate + confidence，需规则/人工通道确认）。

## 3. 每次任务前的自检清单

1. 这个任务对应 `TASKS.md` 的哪一条？没有对应条目就先补条目再动手。
2. 它属于 Engine Core 还是 Domain Pack？放错层 = 违反铁律 4。
3. 是否引入了新的横向依赖？若是，停下写 ADR。
4. 完成定义（DoD）：Code + Unit Test + Integration Test + Security Test（涉权限时）+ Evaluation 用例 + 文档更新 + 可运行 Example。**没有测试的功能不算完成。**
5. 是否需要更新 `docs/API.md` / `docs/DATA_MODEL.md`？（接口与 schema 变更必须先改文档再改代码。）

## 4. 技术栈与运行约束（v0，详见 ADR-002/003/006/009）

```text
Python 3.12+ / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / Alembic
PostgreSQL 16 + pgvector + Postgres FTS（不引入 OpenSearch / Redis / Neo4j / 消息队列）
LLM: OpenAI-compatible endpoint（支持 GPT/Claude/DeepSeek/Qwen；通过 vLLM/Ollama 本地部署国产模型）
测试: pytest（单元/集成/安全/评测四类 marker）
部署: docker compose（api + postgres），必须支持完全离线运行（数据与模型均不出企业网）
```

关键环境变量（唯一 LLM 配置通道）：

```text
ECE_LLM_BASE_URL      # OpenAI 兼容端点，如 http://localhost:11434/v1（Ollama）或 https://api.deepseek.com/v1
ECE_LLM_API_KEY       # 本地模型可为任意占位串
ECE_LLM_MODEL         # 如 qwen2.5:14b / deepseek-chat / gpt-4o
DATABASE_URL          # postgresql+psycopg://ece:ece@db:5432/ece
ECE_ADMIN_TOKEN       # 管理端点（/ingest 等）令牌
ECE_ACTIONS_EXECUTE_ENABLED=false   # /actions/execute v0 强制关闭
```

## 5. 代码组织（对应 PRD §26，按铁律 4 调整）

```text
ece/
├── CLAUDE.md / TASKS.md / README.md
├── docs/（PRD / ARCHITECTURE / DATA_MODEL / API / EVALUATION / adr/）
├── src/
│   ├── ece/                    # Engine Core（零领域知识）
│   │   ├── api/                # FastAPI 路由与中间件
│   │   ├── connectors/         # Connector Interface + CSV/JSON/Docs 实现
│   │   ├── entities/           # Entity Store / Entity Resolution
│   │   ├── relationships/      # Relationship Store（含 temporal 查询）
│   │   ├── permissions/        # Permission Engine
│   │   ├── search/             # Query Planner + 关键词/向量/结构化/关系检索
│   │   ├── context/            # Context Spec 加载 + Assembly + Package + Provenance
│   │   ├── actions/            # Action Preview（execute 关闭）
│   │   ├── audit/              # context_requests 审计与 trace
│   │   └── llm/                # OpenAI 兼容客户端（唯一 LLM 出口）
│   ├── domain_packs/
│   │   └── procurement/        # context_specs/ + agent/ + eval_cases/ + dataset/
│   └── main.py
├── tests/{unit,integration,security,evaluation}/
├── data/（demo 合成企业数据集，见 PRD §27/§28）
├── scripts/（数据生成 / 评测运行 / seed）
├── docker/ + docker-compose.yml + Makefile
```

## 6. 开发循环（每个模块）

```text
Implement → Test（含 security/evaluation marker）→ Evaluate（跑对应评测集）→ Document（更新 docs）→ Commit
```

- 分支：`main` 保护；功能分支 `feat/<task-id>-<slug>`；提交信息含 TASKS.md 条目编号。
- 所有重要架构决策写 ADR（`docs/adr/ADR-0XX-*.md`，模板见 `docs/adr/_TEMPLATE.md`）。
- CI：lint（ruff）+ mypy（宽松模式）+ pytest（unit/integration/security 必跑；evaluation 在有 LLM 端点时跑）。

## 7. 与商业验证的关系（不可遗忘）

本仓库的产出同时是**客户演示物**。`../RED_TEAM_REVIEW.md` v3 的验证计划（48h CA 冒烟、含"中国三问"的访谈）与开发并行推进；访谈结论可能改变的是**领域包**（procurement → audit/compliance），不是引擎。因此：Demo 数据与话术必须中国化（私有化部署、数据不出域、模型自选），见 `docs/PRD.md` §39 与根目录战略文件。
