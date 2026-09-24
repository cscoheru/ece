# Enterprise Context Engine (ECE)

> 面向企业 AI Agent 的 Context 基础设施：让 Agent 在企业既有**组织、权限、业务对象、关系与时间**边界内理解企业。
> v0 以 **Procurement（采购）领域包**验证架构。

## 可行性结论（2026-09-04 评审，详见根目录 `RED_TEAM_REVIEW.md` v3 演进脉络）

**有条件可行**。条件已内化为工程约束（见 `CLAUDE.md` 铁律与 ADR）：

| # | 条件 | 落点 |
|---|---|---|
| 1 | v0 只做采购任务需要的窄切片，禁止横向平台化提前发生 | CLAUDE.md 铁律 3；ADR-001 |
| 2 | 领域包与引擎核心隔离，访谈结论可换领域包而不重写引擎 | CLAUDE.md 铁律 4；ADR-010 |
| 3 | 技术栈瘦身：Postgres(FTS+pgvector) 一库承担，缓交 OpenSearch/Redis/Neo4j | ADR-009 |
| 4 | LLM 走 OpenAI 兼容端点，国产开源模型可本地部署、整体离线可运行 | ADR-006 |
| 5 | 权限零泄露与评测作为 CI 门槛，而非事后补充 | ADR-004；EVALUATION.md |
| 6 | 商业验证（客户访谈）与开发并行，采购领域定位为"建议生成"而非自动决策（规避招投标合规红线） | ADR-007 |

## 文档地图

| 文件 | 内容 |
|---|---|
| `CLAUDE.md` | 开发治理：铁律、栈约束、代码组织、DoD |
| `docs/PRD.md` | 需求唯一事实来源（产品+架构+工程计划 v0.1） |
| `docs/ARCHITECTURE.md` | 分层架构、请求生命周期、模块职责、部署拓扑 |
| `docs/DATA_MODEL.md` | 全部表结构、约束、索引、迁移策略 |
| `docs/API.md` | REST 契约：端点、示例、错误模型、鉴权 |
| `docs/EVALUATION.md` | 六类评测套件、指标门槛、运行方式 |
| `TASKS.md` | Sprint 0–6 任务分解、验收标准、依赖 |
| `docs/adr/` | 架构决策记录（ADR-001 ~ 010） |

## 快速开始（Sprint 0 完成后可用）

```bash
make setup      # uv 同步依赖
make up         # docker compose 起 api + postgres
make test       # unit/integration/security
make eval       # 评测套件（需 ECE_LLM_* 环境变量）
make demo       # 演示脚本：PR001 合理性分析 + 无权限用户对照
```

## Canonical seed（唯一权威链条）

> **R2**：在此之前，「canonical seed」在仓库里有三份互相不一致的定义 ——
> `make seed`（无关系）、CI 链条（无关系）、以及测试自己的 `subprocess` 自愈。
> 没有一份是完整的：`make seed` 建出 428 个实体但 **0 条关系**，于是任何
> 「重置 → seed → 跑评测」的流程都在空关系图上打分。
>
> 下面这条链是**唯一权威**定义。

```bash
make gen-dataset        # data/dataset/demo.json（确定性，S0.6）
make db-upgrade         # alembic upgrade head
make seed               # 实体 + 测试用户 + ACL + 关系 —— 完整入口
make gen-eval-datasets  # E1-E6 评测数据集（依赖 display_id，必须在 seed 之后）
uv run python scripts/ingest_demo_docs.py
```

## 集成测试完整前置链（OEI-005，2026-09-24）

> 本段是 **OEI-005 修复的回归**:此前集成测试（`tests/integration/test_compliance_boundary.py`、`test_knowledge_boundary.py`、`test_three_domain_acceptance.py`、`test_s4_5_temporal.py` 等）默认 `make test` 不会自动跑 fixture seeder，导致 **27 个红灯**（baseline 实际为 **48 failed**，因 `make seed` 也会缓解一部分 entity/relationship 集成）。本次把 3 个 fixture seeder 串成一个 Makefile 目标 + 文档段，让前置链**可发现**。

**完整本地集成测试链**（同一 PG、同一环境、单变量累加）：

```bash
# 1. 镜像准备（如本机未拉过 pgvector）
make pull-db

# 2. PG + 迁移
docker run -d --name ece-pg-tmp -e POSTGRES_USER=ece -e POSTGRES_PASSWORD=ece -e POSTGRES_DB=ece -p 55432:5432 postgres:16-pgvector
export DATABASE_URL='postgresql+psycopg://ece:ece@127.0.0.1:55432/ece'
make db-upgrade

# 3. demo dataset + seed（canonical chain）
make gen-dataset
make seed

# 4. 集成测试 fixture seeder（OEI-005 新增）
make seed-fixtures   # = seed_temporal_roles + seed_knowledge_fixture + seed_compliance_fixture

# 5. 跑测试
make test
```

**或一行**（适用于 CI）：

```bash
make test-integration
```

跑完后**期望**:`passed ≈ 680`、`failed = 1`、`errors = 0`——唯一 failed 是 `test_cut_045_local_origin_smoke.py::test_deployment_smoke_passes_against_local_origin`，属**部署 smoke**（依赖 nginx + 静态 SPA + upstream uvicorn），非产品代码缺陷；详见 `onyx-lab/OEI-005/evidence/09-triage-table.md`。

如果 `make test` 跑出**额外** failed/error，是真正的回归信号，按 OEI-005 §1.2 的三类根因分类排查。



空库上 `make seed` 的产出：

| 对象 | 期望 |
|---|---|
| entities | **428**（`demo:demo` 420 + `api:header` 4 + `demo:seed_departments` 4） |
| relationships | **1200**（`demo:seed_relationships`，每个 demo PR 恰 6 条） |
| acl_entries | **3**（`demo:cut-040-test-acl`） |

**幂等**：第二次 `make seed` 与第一次逐字段相同（实体 `created=0`；关系
delete-then-insert 回同样的 1200 条）。

两点约定：

- `scripts/seed_relationships.py` 保留为兼容 CLI wrapper，内部调用
  `ece.seed.seed_demo_relationships()` —— **只有一份实现**。
- E4/E5 runner 在关系 fixture 缺失或不完整时 **`exit 2` 拒绝运行**，
  而不是对空图打分（那会产出 vacuous pass）。
