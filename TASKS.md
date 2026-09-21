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
- [ ] S4.2 Query Planner：keyword(FTS+bigram)/vector/structured/relationship 四路 + Entity Linking + 权限 SQL 下推（四路召回各自查询内做 PermissionScope 过滤，先过滤、后排序/截断；denied 仅计数） + merge/rank。
- [ ] S4.3 `POST /search`（API.md §2）。验收：检索评测（并入 E3 抽样子集）≥90%；denied_count 正确。
- [ ] S4.4 性能基准：seed 全量下 /context p95 < 1.5s（本地 Docker）。不达 → 先加索引/物化，不引 Redis（ADR-009）。
- [x] S4.5 MCP Tool Layer（K7，设计=根仓 execution-plan.md §4）：src/ece/mcp/{server,transport,auth}.py；暴露 4 工具 search / get_record / create_task / send_message，后两个仅 Preview 不执行；每个 tool call 强制经 PermissionScope（auth.py），不得绕过权限引擎；Claude Code 接入：`claude mcp add ece-context -- python -m ece.mcp.server`（仓库根目录执行）；mcp SDK 依赖本任务动工时引入 pyproject（S0.1 不加）。 [cut-041 完成 2026-09-21: transport.py + tests/integration/test_mcp_server.py 5 测试齐备; 与既有 test_s5_mcp.py 互补不重叠]
  验收：`python -m ece.mcp.server` 启动注册 4 工具；`tests/integration/test_mcp_*.py` 全绿（权限强制 / get_record 404 防探测 / create_task preview-only）；E2=0 不破；离线 stdio 可用。

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
| M1（S3 末） | E1≥95%；E2=0 泄露；E3≥90%；E5≥95%；Provenance 100%（E6 抽样预热） | 停下修复，不进 Sprint 4 |
| M2（S5 末） | E6 全门槛 + 双模型报告 | 分析失败类型（上下文缺 vs 模型弱），只允许"规则补位"类修复 |
| M3（S6 末） | 离线 demo 通过 + eval-report 归档 | 冻结 v0，进入客户演示循环（PRD §48 → 根目录访谈计划） |

总计 ≈ 30 个工作日（solo）。任何超过 2 天的新增工作必须先立 TASKS 条目 + 评估是否违反铁律 3（垂直纪律）。

---

## 附录 H — 测试 Hermeticity 规约（cut-035R2 R3）

**强制规则**：测试禁止依赖未提交本地工件；测试数据必须满足下列任一：

1. **commit 入仓**（force-add OK 当 `.gitignore` 整目录忽略但 CI 需要）。
2. **CI 内确定性生成**（`make gen-*` 类 target 跑在 seed/pytest 之前）。

**反模式**（cut-035R2 R1' 事故根因）：

- 在 `.gitignore` 把 `data/` 整目录屏蔽，但测试断言 `data/` 下某文件存在
- 例：`.gitignore:16` 含 `data/` → `data/eval/e2_permission.json` 与 `data/demo_docs/POL-2026-03.md` 本机私有 → CI 缺文件 → 4 个测试红（run `35048727117`：`4 failed, 306 passed, 25 skipped`），CC 却报 "vanished" → 第 6 次完整性事故
- 例：报告 §5.1 写根因结论前未跑 `gh run view --log-failed` 亲验 CI 日志

**强制自检**（每刀 commit 前）：

- [ ] `git ls-files data/ | wc -l` ≥ CI 期望命中数（grep `data/` 在 pytest 用法）
- [ ] 新增 data 资产有对应的 `make gen-*` target 或 `git add -f` 记录
- [ ] 若测试依赖某文件存在，该文件已在 CI workflow step 中显式创建/复制/生成

**上游配套**：

- `pytest -rs` 必须保留（cut-035R2 R5）：让 skip 原因可见，防止"绿但空转"
- CI workflow data 供给 step 必须在 `pytest` step 之前（顺序约束）
- R3 规约与 R1' 数据重建同步生效 — 见 `reports/cut-035R2-report.md`

---

## 附录 I — v0.2 Hardening Arc 检疫记录（cut-038 R38.2）

> 来源：`docs/track_b/execution-loop-plan.md` 漂移裁定段（2026-09-15）+ Cline cut-037 终审 §10（2026-09-16）〔§11→§10 笔误修正 per cut-038 §10.2-C3〕。

### I.1 范围漂移

v0.1 计划仅 Sprint 0–6。**刀 19–34（v0.2 hardening arc，16 刀）为 CC 自创轨道**，违反 v3-3 循环规则 3（"范围外想法记 TODO 汇报，不擅自做"）。`v0.2-cutover-checklist.md` / `v0.2-deploy.md` 均为事后自证文件，非规划产物。

### I.2 审验真空

刀 7–18 由 codex 审验（标准弱于 Cline：0001/0005 双建表炸弹埋于 cut-007 `6559a9e` 未被查出）。**刀 19–34 共 16 刀零审验**（handoff 自认 "自上次审验通过的 `526ea75` 以来"）。

### I.3 护栏失效

CI 自 2026-09-14T03:16（cut-6 时代最后一个绿）起 **53 连红、0 绿**——刀 7–34 每次 push 全红，**无一份报告披露**。cut-5R 装的 fresh-migrate+md5 护栏被整个 arc 无视。

### I.4 架构漂移

v0.1 的 PRD/ADR-004 权限模型（DB acl_entries + PermissionScope SQL 下推）被绕开，长出 **13 个 env 字符串配置的伪企业安全面**（env 存 token/撤销表/限流表），并携带 P0 级认证旁路（JWT 模式下 X-User-Id 未认证回落，活体实证 200 冒充）——**hardening arc 让产品比 Sprint 2 设计更不安全**。cut-036 砍静默回落 + cut-037 修 cut-028 invariant 旁路 = 止血三连收尾。

### I.5 v0.2 13 env 检疫清单（cut-038 R38.1 确认全部默认 off）

| Env | 用途 | 默认 |
|---|---|---|
| `ECE_USER_ORGS` | multi-tenant user→org mapping | **off** |
| `ECE_DELEGATION_ORG_TOKENS` | cross-org token delegation | **off** |
| `ECE_AUDIT_TOKEN_REQUEST_IDS` | per-resource audit token | **off** |
| `ECE_ORG_RATE_LIMITS` | org short-window rate limit | **off** |
| `ECE_REVOKED_TOKENS` | token kill-switch | **off** |
| `ECE_REDIS_URL` | Redis-backed rate/quota | **off** |
| `ECE_JWT_SECRET` | HS256 JWT | **off** |
| `ECE_JWT_PUBLIC_KEY` | RS256 JWT | **off** |
| `ECE_JWT_ALGORITHM` | HS256/RS256 selector | **off** (n/a unless SECRET/KEY set) |
| `ECE_REVOKED_USERS` | user-level lockout | **off** |
| `ECE_ORG_QUOTAS` | org long-window quota | **off** |
| `ECE_AUDIT_WEBHOOK_URL` | SIEM webhook target | **off** |
| `ECE_AUDIT_WEBHOOK_TIMEOUT` | webhook timeout (cosmetic) | **off** (n/a unless URL set) |

**结论**：13/13 默认 off，默认 env startup = 纯 v0.1（活体探针 `scripts/cut_038_default_env_probe.py` exit 0 验证）。

### I.6 检疫期处置

- **代码**：v0.2 弧所有代码**保留不动**（已默认 off，无运行时影响），但**不被视为产品代码**
- **测试**：R38.1 活体探针 + cut-026/035R2 baseline 349P/4S/0F 守住 v0.1 默认行为
- **文档**：`docs/v0.2-deploy.md` / `docs/v0.2-cutover-checklist.md` 头部 BLOCKER 警示（本附录生效）
- **未来路线**：v0.2 弧**不整体回滚**，但**全部隔离在 demo 层**；若需启用任一 env，必须走正式规划流程（PRD 增补 + 新 ADR + 用户批准），且重做为 DB-backed（acl_entries/委托表入库），弃 env-token 模式——预计另立 arc 约 6–8 刀，属新产品决策，由用户裁定是否启动。


---

## 附录 J — Production Gate 登记（cut-040R-2，Codex 第三轮补充判词 §五）

> 本附录是**治理登记**，不是权限架构设计。登记原因：该约束若只留在代码注释中会被遗忘。

### J.1 已登记的 Production Gate

| ID | 约束 | 位置 | V0 | Production |
|---|---|---|---|---|
| **PG-1** | **Production authorization chain MUST derive principal from authenticated credential; caller-supplied `req.user_ref` must be removed.** | `src/ece/api/identity.py` :: `POST /permissions/check` | **允许保留** | **禁止** |

**背景**：`/permissions/check` 现为 `user_ref = req.user_ref or x_user_id`，即**请求体可指定被检查的身份**。
作为 **verification surface**（"user X 能否访问 object Y？"）这是其设计用途，可接受。
但一旦进入真实**授权链**，调用者将能询问"**别人**能不能访问 X"，而非只能问"**我**能不能访问 X"。
授权主体绝不能由调用者自行指定。

### J.2 处置规则

- **V0 / demo / 评测**：保持现状，**不修改**（改动会波及 E2 全部 61 例的调用方式）。
- **进入 Production 前**：必须删除 `req.user_ref`，principal 只从认证凭据解析。
- **触发条件**：任何把 `/permissions/check` 接入真实访问决策的前置工作，**必须先完成 PG-1**。
- 计数器：本附录是 PG 系列的第 1 条；后续 Production Gate 追加于此表，不新开文档。

### J.3 明确不做

- ❌ 不在本刀内重构权限架构
- ❌ 不新增 IAM / 身份目录 / 凭据轮换能力（Kernel 只拥有 **enforcement point + scope contract**，见 `docs/v3/KERNEL_BOUNDARY.md` §3.1）
