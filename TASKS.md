# TASKS — Enterprise Context Engine v0

> 任务编号规则：`S<周>.<序号>`；每条含验收（DoD 引用 CLAUDE.md §3）。估算按 1 名全职开发者。
> **商业并行线（不属于本表但阻塞领域包定稿）**：根目录 RED_TEAM_REVIEW v3 的访谈验证持续进行；若结论换领域，只替换 `src/domain_packs/<new>/`，Sprint 0–4 全部复用（ADR-010）。

## Sprint 0 — 工程地基（2 天）

- [ ] S0.1 仓库初始化：`uv` + pyproject（python 3.12, fastapi, pydantic v2, sqlalchemy 2.0, alembic, psycopg, pgvector, pytest, ruff, mypy）、Makefile（setup/up/test/eval/demo/rev）。验收：`make setup && make test` 绿（空测试）。
- [ ] S0.2 docker-compose：api + postgres:16-pgvector，卷挂载 data/，离线可起。验收：`docker compose up` 后 `/healthz` 200。
- [ ] S0.3 CI（GitHub Actions 或本地 pre-commit）：lint + mypy + pytest(unit,integration,security)。验收：push 即跑，红则阻断。
- [ ] S0.4 `scripts/check_api_docs.py`：OpenAPI 端点清单 ↔ API.md 表格一致性校验。验收：故意加路由不改文档 → CI 红。
- [ ] S0.5 Alembic 初始迁移：DATA_MODEL §1–§5 全部表 + 索引。验收：`alembic upgrade head` 后 schema 与文档一致（自动比对）。
- [ ] S0.6 合成数据生成器骨架 `scripts/gen_dataset.py`：可产出 PRD §27 规模的 Demo Corporation（含对抗性标记列）。验收：生成 → 校验统计（数量/对抗用例计数）打印。

## Sprint 1 — 数据面：Connector + Entity/Relationship（4 天）

- [ ] S1.1 Connector Interface + csv/json/docs 三实现（ARCHITECTURE §1 契约）+ `/ingest/runs`。验收：integration 测试覆盖 happy path + 脏数据 skip 计数。
- [ ] S1.2 实体/关系入库管线（含 ontology.yaml 三元组校验、display_id 分配、provenance 字段落库）。验收：seed 全量导入 0 错误；违规三元组被拒并记录。
- [ ] S1.3 Entity/Relationship 只读 API（API.md §3）+ 分页 + 404 防探测一致性。验收：契约测试全绿。
- [ ] S1.4 seed.py 幂等重跑（upsert 语义）。验收：连跑两次 stats 第二次 created=0。

## Sprint 2 — 身份、权限、消歧（5 天）

- [ ] S2.1 Identity：X-User-Id → person 实体 + roles + department 解析（含别名）。验收：E1 子集通过。
- [ ] S2.2 Permission Engine：acl_entries + classification 默认矩阵 + 判定顺序（deny>user>role>dept>default）+ `PermissionScope` 注入所有 Store 读路径（SQL 子查询过滤）。验收：单元全绿 + `/permissions/check` 契约。
- [ ] S2.3 Entity Resolution 流水线（exact→normalized→alias→rule→embedding；llm 仅 candidate）+ `/resolve`。验收：E1 ≥95% 且歧义例 resolved:false；pending 队列落库。
- [ ] S2.4 **安全套件 E2（50 例）+ 间接泄露用例**。验收：Unauthorized Exposure = 0；CI 阻断生效。

## Sprint 3 — Context 核心（6 天）

- [ ] S3.1 Context Spec 加载器（YAML→内存模型，版本化）+ 领域包目录结构落地。
- [ ] S3.2 Assembly Pipeline 十二步（ARCHITECTURE §3）：fail-closed、temporal 谓词、limits 截断、denied 列表。
- [ ] S3.3 Provenance：每项 source 生成 + `sources[]` sid 分配；`context_requests/context_items` 写入。
- [ ] S3.4 `POST /context` 完整实现（含 resolution_ambiguous / insufficient_context 语义）。
- [ ] S3.5 **E3(100)+E4(30)+E5(30) 评测集**（由 gen_dataset 投影）。验收：E3≥90%、E4 错连=0、E5≥95%。

## Sprint 4 — 检索面（4 天）

- [ ] S4.1 文档 ingestion：分块 + tsv 生成 + embedding（ECE_EMBED_PROVIDER=local 默认 bge-small-zh-v1.5；api 模式留接口）。
- [ ] S4.2 Query Planner：keyword(FTS+bigram)/vector/structured/relationship 四路 + Entity Linking + 权限后置过滤 + merge/rank。
- [ ] S4.3 `POST /search`（API.md §2）。验收：检索评测（并入 E3 抽样子集）≥90%；denied_count 正确。
- [ ] S4.4 性能基准：seed 全量下 /context p95 < 1.5s（本地 Docker）。不达 → 先加索引/物化，不引 Redis（ADR-009）。

## Sprint 5 — Procurement Agent + Agent 评测（5 天）

- [ ] S5.1 领域规则库：比价触发（阈值 100 万边界）、价格偏离带（vs 历史价/市场参考）、审批链完整性、政策匹配——纯 Python 规则，输出结构化 findings。
- [ ] S5.2 Procurement Agent：Package+Question→结构化输出（API.md §6 schema）；规则 findings 注入 prompt；temperature=0。
- [ ] S5.3 `/actions/preview` + `/actions/execute` 双保险关闭。
- [ ] S5.4 **E6(50 问)** + 纯 RAG 基线对照（EVALUATION §5 H3）。验收：结论方向 ≥80%、evidence 真实率 100%、开源模型与强基线差距报告产出。

## Sprint 6 — Debugger、演示、定稿（4 天）

- [ ] S6.1 `/audit/context/{id}` + 最小 Debugger 页（三页 UI：Ask / Context Explorer / Debugger，服务端渲染即可，禁重型前端框架）。
- [ ] S6.2 Demo 脚本固化：PR001 合理性问题（有权限）→ 换 U002（无权限）→ insufficient_context 显式声明（PRD §48 两个核心演示）。
- [ ] S6.3 `make eval-report` 六套件汇总 + README 指标表更新。
- [ ] S6.4（选做）迷你换域演练：audit context spec 走通 /context（验证 H5/ADR-010，不建 Agent）。
- [ ] S6.5 私有化验收：断网环境（本地 Ollama + local embedding）`make demo` 全流程成功。

## 里程碑门槛（对照 PRD §35）

| 里程碑 | 门槛 | 未达动作 |
|---|---|---|
| M1（S3 末） | E2=0 泄露；E3≥90%；E5≥95% | 停下修复，不进 Sprint 4 |
| M2（S5 末） | E6 全门槛 + 双模型报告 | 分析失败类型（上下文缺 vs 模型弱），只允许"规则补位"类修复 |
| M3（S6 末） | 离线 demo 通过 + eval-report 归档 | 冻结 v0，进入客户演示循环（PRD §48 → 根目录访谈计划） |

总计 ≈ 30 个工作日（solo）。任何超过 2 天的新增工作必须先立 TASKS 条目 + 评估是否违反铁律 3（垂直纪律）。

