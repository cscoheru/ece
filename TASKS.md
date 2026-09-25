# TASKS — Enterprise Context Engine v0

> 任务编号规则：`S<周>.<序号>`；每条含验收（DoD 引用 CLAUDE.md §3）。估算按 1 名全职开发者。
> **商业并行线（不属于本表但阻塞领域包定稿）**：根目录 RED_TEAM_REVIEW v3 的访谈验证持续进行；若结论换领域，只替换 `src/domain_packs/<new>/`，Sprint 0–4 全部复用（ADR-010）。

## Sprint 0 — 工程地基（2 天）

- [x]  S0.1 仓库初始化：`uv` + pyproject（python 3.12, fastapi, pydantic v2, sqlalchemy 2.0, alembic, psycopg, pgvector, pytest, ruff, mypy）、Makefile（setup/up/test/eval/demo/rev）。验收：`make setup && make test` 绿（空测试）。  [verified OEI-008 step 0.2]
- [x]  S0.2 docker-compose：api + postgres:16-pgvector，卷挂载 data/，离线可起。验收：`docker compose up` 后 `/healthz` 200。  [verified OEI-008 step 0.2]
- [ ]  S0.3 CI（GitHub Actions 或本地 pre-commit）：lint + mypy + pytest(unit,integration,security)。验收：push 即跑，红则阻断。  [未实现, v0 范围外 — 本机无 .github/pre-commit 配置]
- [x]  S0.4 `scripts/check_api_docs.py`：OpenAPI 端点清单 ↔ API.md 表格一致性校验。验收：故意加路由不改文档 → CI 红。  [verified OEI-008 step 0.2]
- [x]  S0.5 Alembic 初始迁移：DATA_MODEL §1–§5 全部表 + 索引。验收：`alembic upgrade head` 后 schema 与文档一致（自动比对）。  [verified OEI-008 step 0.2 (0001-0008)]
- [x]  S0.6 合成数据生成器骨架 `scripts/gen_dataset.py`：可产出 PRD §27 规模的 Demo Corporation（含对抗性标记列）。验收：生成 → 校验统计（数量/对抗用例计数）打印。  [verified OEI-008 step 0.2]

## Sprint 1 — 数据面：Connector + Entity/Relationship（4 天）

- [x]  S1.1 Connector Interface + csv/json/docs 三实现（ARCHITECTURE §1 契约）+ `/ingest/runs`。验收：integration 测试覆盖 happy path + 脏数据 skip 计数。  [verified OEI-008 step 0.2]
- [x]  S1.2 实体/关系入库管线（含 ontology.yaml 三元组校验、display_id 分配、provenance 字段落库）。验收：seed 全量导入 0 错误；违规三元组被拒并记录。  [verified OEI-008 step 0.2]
- [x]  S1.3 Entity/Relationship 只读 API（API.md §3）+ 分页 + 404 防探测一致性。验收：契约测试全绿。  [verified OEI-008 step 0.2]
- [x]  S1.4 seed.py 幂等重跑（upsert 语义）。验收：连跑两次 stats 第二次 created=0。  [verified OEI-008 step 0.2]

## Sprint 2 — 身份、权限、消歧（5 天）

- [x]  S2.1 Identity：X-User-Id → person 实体 + roles + department 解析（含别名）。验收：E1 子集通过。  [verified OEI-008 step 0.2]
- [x]  S2.2 Permission Engine：acl_entries + classification 默认矩阵 + 判定顺序（deny>user>role>dept>default）+ `PermissionScope` 注入所有 Store 读路径（SQL 子查询过滤）。验收：单元全绿 + `/permissions/check` 契约。  [verified OEI-008 step 0.2]
- [x]  S2.3 Entity Resolution 流水线（exact→normalized→alias→rule→embedding；llm 仅 candidate）+ `/resolve`。验收：E1 ≥95% 且歧义例 resolved:false；pending 队列落库。  [verified OEI-008 step 0.2]
- [x]  S2.4 **安全套件 E2（50 例）+ 间接泄露用例**。验收：Unauthorized Exposure = 0；CI 阻断生效。  [verified OEI-008 step 0.2]

## Sprint 3 — Context 核心（6 天）

- [x]  S3.1 Context Spec 加载器（YAML→内存模型，版本化）+ 领域包目录结构落地。  [verified OEI-008 step 0.2]
- [x]  S3.2 Assembly Pipeline 十二步（ARCHITECTURE §3）：fail-closed、temporal 谓词、limits 截断、denied 列表。  [verified OEI-008 step 0.2]
- [x]  S3.3 Provenance：每项 source 生成 + `sources[]` sid 分配；`context_requests/context_items` 写入。  [verified OEI-008 step 0.2]
- [x]  S3.4 `POST /context` 完整实现（含 resolution_ambiguous / insufficient_context 语义）。  [verified OEI-008 step 0.2]
- [x]  S3.5 **E3(100)+E4(30)+E5(30) 评测集**（由 gen_dataset 投影）。验收：E3≥90%、E4 错连=0、E5≥95%。  [verified OEI-008 step 0.2]

## Sprint 4 — 检索面（4 天）

- [x]  S4.1 文档 ingestion：分块 + tsv 生成 + embedding（ECE_EMBED_PROVIDER=local 默认 bge-small-zh-v1.5；api 模式留接口）。  [verified OEI-008 step 0.2 (OEI-007 已把 embedding 交给引擎)]
- [x]  S4.2 Query Planner：keyword(FTS+bigram)/vector/structured/relationship 四路 + Entity Linking + 权限 SQL 下推（四路召回各自查询内做 PermissionScope 过滤，先过滤、后排序/截断；denied 仅计数） + merge/rank。  [verified OEI-008 step 0.2]
- [x]  S4.3 `POST /search`（API.md §2）。验收：检索评测（并入 E3 抽样子集）≥90%；denied_count 正确。  [verified OEI-008 step 0.2]
- [ ]  S4.4 性能基准：seed 全量下 /context p95 < 1.5s（本地 Docker）。不达 → 先加索引/物化，不引 Redis（ADR-009）。  [未实现, v0 范围外 — 无 reports/perf 落盘]
- [x]    S4.5 MCP Tool Layer（K7，设计=根仓 execution-plan.md §4）：src/ece/mcp/{server,transport,auth}.py；暴露 4 工具 search / get_record / create_task / send_message，后两个仅 Preview 不执行；每个 tool call 强制经 PermissionScope（auth.py），不得绕过权限引擎；Claude Code 接入：`claude mcp add ece-context -- python -m ece.mcp.server`（仓库根目录执行）；mcp SDK 依赖本任务动工时引入 pyproject（S0.1 不加）。 [cut-041 完成 2026-09-21: transport.py + tests/integration/test_mcp_server.py 5 测试齐备; 与既有 test_s5_mcp.py 互补不重叠]  [already checked pre-OEI-008 (cut-041)]
  验收：`python -m ece.mcp.server` 启动注册 4 工具；`tests/integration/test_mcp_*.py` 全绿（权限强制 / get_record 404 防探测 / create_task preview-only）；E2=0 不破；离线 stdio 可用。

## Sprint 5 — Procurement Agent + Agent 评测（5 天）

- [x]  S5.1 领域规则库：比价触发（阈值 100 万边界）、价格偏离带（vs 历史价/市场参考）、审批链完整性、政策匹配——纯 Python 规则，输出结构化 findings。  [verified OEI-008 step 0.2]
- [x]  S5.2 Procurement Agent：Package+Question→结构化输出（API.md §6 schema）；规则 findings 注入 prompt；temperature=0。  [verified OEI-008 step 0.2]
- [x]  S5.3 `/actions/preview` + `/actions/execute` 双保险关闭。  [verified OEI-008 step 0.2]
- [x]  S5.4 **E6(50 问)** + 纯 RAG 基线对照（EVALUATION §5 H3）。验收：结论方向 ≥80%、evidence 真实率 100%、开源模型与强基线差距报告产出。  [verified OEI-008 step 0.2]

## Sprint 6 — Debugger、演示、定稿（4 天）

- [x]  S6.1 `/audit/context/{id}` + 最小 Debugger 页（三页 UI：Ask / Context Explorer / Debugger，服务端渲染即可，禁重型前端框架）。  [verified OEI-008 step 0.2]
- [x]  S6.2 Demo 脚本固化：PR001 合理性问题（有权限）→ 换 U002（无权限）→ insufficient_context 显式声明（PRD §48 两个核心演示）。  [verified OEI-008 step 0.2]
- [x]  S6.3 `make eval-report` 六套件汇总 + README 指标表更新。  [verified OEI-008 step 0.2]
- [x]  S6.4（选做）迷你换域演练：audit context spec 走通 /context（验证 H5/ADR-010，不建 Agent）。  [verified OEI-008 step 0.2 (cross-domain smoke 等价)]
- [ ]  S6.5 私有化验收：断网环境（本地 Ollama + local embedding）`make demo` 全流程成功。  [未实现, v0 范围外 — 缺 Ollama+local embedding 链路]

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

---

## 附录 K — Onyx Enterprise Integration 后置交付登记（OEI-003 / OEI-004，2026-09-24）

> 本附录登记已交付但**不属于 v0 PRD 主线**的能力，与 OEI 主线（`../onyx-lab/OEI-*`）一一对应。
> 受 CLAUDE.md §2 铁律约束；本附录不是新 PRD 来源。

### K.1 Onyx / ECE 连接器（OEI-003）

| 能力 | 位置 | 状态 | 备注 |
|---|---|---|---|
| `ContentEnginePort` Protocol | `src/ece/connectors/onyx/port.py` | 已交付 | 3 个方法：`search` / `engine_status` / `list_projects` |
| `EngineStatus` / `EngineDocument` / `EngineProject` Pydantic 模型 | 同上 | 已交付 | 领域层零 Onyx 依赖（grep `import onyx` = 0 命中） |
| `MockContentEngineAdapter`（离线确定性） | `mock_adapter.py` | 已交付 | `ECE_CONTENT_ENGINE=mock` 时使用（默认） |
| `OnyxContentEngineAdapter`（真实 HTTP） | `onyx_adapter.py` | 已交付 | 调用 Onyx `/api/admin/llm/provider` / `/api/user/projects` / `/api/user/projects/files/{id}` / `/api/search` / `/api/version` |
| `get_content_engine()` selector | `selector.py` | 已交付 | 读 `ECE_CONTENT_ENGINE` + `ECE_ONYX_BASE` + `ECE_ONYX_COOKIE_FILE` |
| `GET /engine/status` 状态页（含引用渲染） | `src/ece/api/engine_status.py` + `main.py` | 已交付 | `?q=` 触发 search + ECE 自己渲染引用卡片（绕开 Onyx UI 不渲染引用的 bug） |

### K.2 验收证据（OEI-003 VERDICT.md §7.3 二轮）

- A1 / A2 / A3 / A4 / A5 / A6 / A7 / A8 / A9 / A10 / A11 / A12 全部 PASS
- A8 无回归：`634 passed / 28 failed / 5 errors` baseline vs after 一致（28+5 是 ECE 仓 pre-existing，非 OEI-003 引入）
- A4 真实 Onyx 引用渲染：HTML 含 `v4.7.8` + `methodology-framework.md`（独立由 codex 复跑确认）

### K.3 收尾债（移交 OEI-004 / 用户）

- [ ] `docs/API.md` 新增 `/engine/status` 章节 — **OEI-004 step 4 完成**
- [ ] `tests/unit/test_content_engine_port.py`（DB 无关的 adapter 单测）— 留给后续刀，避免 OEI-003 pytest 环境坑
- [ ] `ece/` 仓真实改动 commit（不含 `._*` 垃圾、`.mypy_cache`、mutation-evidence 历史 dirty）— **OEI-004 step 7 完成**

---

## 附录 L — Consulting Knowledge Library × 内容引擎合并（KC-001 / OEI-006，2026-09-24）

> 登记 KC-001（咨询知识库视图）与 OEI-006（接真实检索）的交付边界。
> 说明：KC-001 本身的交付此前**未**在 TASKS.md 登记，本条为本附录首次登记（覆盖 KC-001 现状 + OEI-006 增量）。
> 主线对应 `../onyx-lab/OEI-006/`；受 CLAUDE.md §2 铁律约束；本附录不是新 PRD 来源。

### L.1 交付物

| 能力 | 位置 | 状态 | 备注 |
|---|---|---|---|
| 静态目录（36 个 file-backed 种子对象） | `src/ece/consulting/`（`service.py` + 种子 JSON） | 已交付（KC-001） | 无 DB / 无 LLM / 无 embedding |
| `GET /api/v1/consulting/library` | `src/ece/consulting/router.py` | **本刀改为 `async`** | 静态结果先算，引擎合并只**追加**字段 |
| 引擎合并策略（纯函数 + 四态） | `src/ece/consulting/engine_merge.py` | **本刀新增** | `merge_engine()` / `to_engine_items()`；`DEFAULT_TOP_K=8` |
| 新增契约 `EngineItem` / `EngineMergeStatus` | `src/ece/consulting/models.py` | **本刀新增** | 只允许新增，静态字段语义未动 |
| SPA 视图 D 引擎分组 | `demos/spa/index.html` + `app.js` + `styles.css` | **本刀新增** | 复用既有详情抽屉；虚线边框蓝条卡片 |
| 契约文档 | `docs/API.md` §11 | **本刀新增** | `engine_items` / `engine_status` 字段表 + 四态语义 + 实测示例 |
| DB 无关单测（24 条） | `tests/unit/test_consulting_engine_merge.py` | **本刀新增** | 映射 / 合并 / 四态 / 异常路径 / 契约同构 / 端点级静态隔离 |

### L.2 契约要点（消费者须知）

- 静态侧 `items/total/limit/offset/facets` **语义与字段零变化**，既有消费者不受影响；引擎结果只走**新增**字段。
- `engine_status` 四态是策略：`ok`（问了答了）/ `unavailable`（问了失败）/ `disabled`（没问，非 onyx 模式）/ `skipped`（`q` 为空）。
- **fail-closed**：非 `onyx` 模式一律 `disabled` 且不打检索 —— mock 适配器返回内置样例，冒充"你已索引的文档"属谎报。
- 引擎内部字段（`link` / `content` / `citation_id` / `raw`）**不出现在响应**。
- 分页只作用于静态侧；引擎侧固定 `top_k=8`。

### L.3 验收证据

- 见 `../onyx-lab/OEI-006/evidence/01..12-*`；`02/03` 为 onyx 模式真实取证，`04` 降级（200 + 静态不变 + `unavailable`），`05` 空态，`06` 契约同构，`07` SPA 可见性自查。
- A8 契约同构：mock 与 onyx（真实 `/api/search` 命中）经**同一** `EngineItem` 模型校验通过。

### L.4 已知限制 / 移交

- **时延**：`ok` 路径取决于内容引擎，Onyx 实测稳态 ≈4.2s、冷启动首查可达 15s（ECE 适配器超时 60s）。经 `scripts/cut_045_local_origin.py` 反代时其上游超时仅 **10s**，冷启动首查可能 `502`（重试即可）—— 属自查链路特性，非接口缺陷。
- **相关性**：Onyx `/api/search` 返回**最近邻**而非相关性过滤，无意义 query 也会返回整库前 N 条；因此"引擎零命中"在已索引项目上并不可自然到达，该分支由单测确定性覆盖。UI 文案宜表述为"相关文档"而非"命中"。
- **未做**（OEI-006 范围外）：上传管道（OEI-007）、权限壳层（OEI-008）、LLM Chat 生成答案。
- **移交建议**：`make seed-fixtures` 未包含 `scripts/seed_v0_spike_fixture.py`（第 4 个 fixture），导致 `test_cut_045_local_origin_smoke` 在干净环境上失败；建议补入 Makefile（本刀 §7 未授权改 `Makefile`，故仅登记不修改）。

---

## 附录 M — Consulting Knowledge Library × 真实上传入库（OEI-007，2026-09-24）

> 登记 OEI-007：把客户的真实咨询文档拖进 ECE → 走内容引擎抽取 + 索引 →
> 立刻在「引擎召回」分组里被检索到。**静态侧语义零变化**（附录 L 的 §L.2
> 契约要点继续生效），新功能只走新增字段与新增端点。

### M.1 交付物

| 能力 | 位置 | 状态 | 备注 |
|---|---|---|---|
| Port 写路径扩展 `upload_document` / `document_status` | `src/ece/connectors/onyx/port.py` + `onyx_adapter.py` + `mock_adapter.py` | 已交付 | `EngineDocumentStatus` 模型；document_id = `user_file.id`（UUID），与搜索侧 `engine_doc_id` 分属两个命名空间 |
| ECE 上传端点 `POST /api/v1/consulting/documents` | `src/ece/consulting/router.py` + `metadata.py` | 已交付 | 多文件、per-file 拒绝、白名单、4 MiB/16 MiB 上限 |
| ECE 状态端点 `GET /api/v1/consulting/documents/{id}` | 同上 | 已交付 | 200 / 404（id 未知） / 502（引擎不可达） |
| 咨询元数据确定性建议器 | `src/ece/consulting/metadata.py` | 已交付 | 词表严格来自 36 个种子对象；越界静默丢弃 |
| SPA 视图 D 上传区 + 最近上传行表 | `demos/spa/index.html` + `app.js` + `styles.css` | 已交付 | 复用既有详情抽屉；上传成功后自动触发 library 检索 |
| DB 无关单测（32 条） | `tests/unit/test_consulting_documents.py` | 已交付 | 白名单、大小、元数据、Port 写路径、上传/状态端点、引擎降级、静态侧零变化 |
| 二进制样本 (docx) 入库 + 召回 | `evidence/09-binary-format.json` | 已交付 | stdlib `zipfile + XML` 构造；`pyproject.toml` 与 `uv.lock` diff 为空 |

### M.2 步骤 0 处置

- `Makefile` 的 `seed-fixtures` 已补上 `scripts/seed_v0_spike_fixture.py`（**采用「纳入 Makefile」方案**；TASK §4 step 0 给的二选一之一）。
- `tests/integration/test_cut_045_local_origin_smoke.py` 的 skip 守卫补上了"无 DB"判断 —— 没有 `DATABASE_URL` 时显式 skip 而非失败（这是 TASK §4 step 0.2 的明确要求；之前版本曾在此类环境上 fail 而非 skip）。
- 处置完跑 `make seed-fixtures && make test` → **705 passed / 0 failed**（与基线持平）。

### M.3 已知限制 / 移交

- **时延**：上传响应（`upload_document`）<1s；引擎抽取 + 索引通常 **5-15s**；检索查询稳态 **4.2s**，冷启动首查可达 **15s**。经反代链路时 `cut_045_local_origin.py` 的上游超时仅 **10s**，冷启动首查会 502；自查用「先直连做热启动」规避。
- **相关性**：Onyx `/api/search` 仍按**最近邻**而非相关性过滤（A8 / §L.4 已记），故「上传 → 立即可召回」必须**等索引完成 + 短暂的索引传播时间**。证据 05 通过多查询 + 多等待（5/15/30/60s）验证。
- **幂等策略**：每次上传生成独立的 `document_id`（不静默合并）；SPA 的去重靠"一张卡 = 一个 `engine_doc_id`"自然完成。
- **未做**（OEI-007 范围外）：上传历史可视化、批量导入、定时同步、权限壳层（OEI-008）。
- **移交**：建议下一刀把 SPA 引擎分组文案从「相关文档」调整为「已索引文档」（与 OEI-006 §L.4 一致）。

### M.4 与既有咨询元数据的连接

OEI-006 引入的 `engine_status` 四态继续生效：
- 上传成功且文档已被引擎索引后 → `engine_status="ok"` 且 `engine_items` 包含新文档；
- 引擎不可达 → `engine_status="unavailable"`（静态侧零影响）；
- `ECE_CONTENT_ENGINE` 非 `onyx` → `engine_status="disabled"`（mock 模式的"未问"状态，**故意**不展示 mock 内置样例）；
- 空 query → `engine_status="skipped"`。

## 附录 N — 身份穿透到内容引擎（OEI-008，2026-09-25）

> 让每一次引擎调用都带上"是谁在问"，并把手抄的环境变量 selector 换成 Port 自述的
> `engine_name`。**本刀不做权限过滤**（OEI-009 范围），只把身份**送到边界为止**，
> 并把"送不过去"这件事写成文档。

### N.1 交付物

| 交付物 | 位置 | 状态 | 说明 |
|---|---|---|---|
| `EngineCallerContext` + Port 契约 | `src/ece/connectors/onyx/port.py` | 已交付 | 冻结 dataclass（`user_ref`/`roles`/`department`/`is_management`/`org_id`/`source`）；五个方法全部收 `caller`；新增 `engine_name` Protocol 属性 |
| 两个 caller 构造器 | `src/ece/connectors/onyx/caller.py`（新） | 已交付 | `caller_from_request_headers`（廉价，只读）/ `caller_from_db_identity`（查 DB，写路径） |
| 适配器身份 + 审计 | `mock_adapter.py` / `onyx_adapter.py` | 已交付 | 同一套 `_audit(what, *, caller, result, **extra)`；**成功路径也记**；匿名上传在发 HTTP 前即拒 |
| 消除 selector 镜像 | `src/ece/consulting/engine_merge.py` | 已交付 | 删除 `_engine_switch_is_onyx()` 与 `os.environ.get("ECE_CONTENT_ENGINE")`，改读 `engine.engine_name` |
| 四个调用点接线 | `src/ece/api/engine_status.py` + `src/ece/consulting/router.py` | 已交付 | library / engine-status / upload / document-status 各自接上 caller |
| DB 无关单测（20 条） | `tests/unit/test_content_engine_identity.py`（新） | 已交付 | 契约、`display()`、审计、匿名拒绝、`engine_name` 派发回归钉 |
| 文档 | `docs/API.md` §13（新） | 已交付 | 契约表、四调用点匿名策略、CE 权限限制、审计形态 |

### N.2 匿名策略（四调用点）

| 调用点 | 匿名行为 |
|---|---|
| `GET /api/v1/consulting/library` | 允许，记 `<anonymous>`，照常检索 |
| `GET /engine/status` | 允许，记 `<anonymous>` |
| `POST /api/v1/consulting/documents` | **403** `identity-required` |
| `GET /api/v1/consulting/documents/{id}` | 允许（只读轮询） |

### N.3 已知限制 / 移交

- **CE 无法下推权限**：社区版 Onyx `/api/search` 无 ACL 参数，`caller` 只能用于审计，
  不能裁剪结果。故引擎召回分组里存在"跨域片段可见"的窗口。缓解方向（5 条，
  **未实施**）见 `onyx-lab/OEI-008/evidence/07-ce-permission-limitation.md`。
  → **移交 OEI-009**（权限过滤算法）。
- **审计是进程内的**：`audit_log` 只活在进程里，不落 `src/ece/audit/` 那张表。
  per-call 落库会引入"每次检索一次 DB 写"，本刀**故意不承担**该成本。
- **未做**：权限过滤、记忆、多租户（分别是 OEI-009 / OEI-010 / 非目标）。

### N.4 步骤 0 处置（TASKS.md 对账）

- 以代码证据逐条核对 Sprint 勾选项：**30 条**由未勾选改为已勾选并标注
  `[已核实 OEI-008 第 0.2 步]`；**3 条**标记 `[未实现, v0 范围外]`
  （S0.3 CI 流水线、S4.4 性能基准、S6.5 私有化验收）。
- 对账脚本与逐条判据见 `onyx-lab/OEI-008/evidence/00b-tasks-reconcile.txt`。

## 附录 O — 权限与审计接线（OEI-009，2026-09-25）

把"引擎召回也受 ECE 权限约束"这条线接上 `附录 K §K.3` 移交的"权限过滤算法"
与 `附录 N §N.3` 移交的"OEI-009"。三件事：

### O.1 引擎文档登记表（`engine_documents`，迁移 0009）

- 新表 `(engine_name, engine_filename)` 唯一；`engine_filename` 是
  服务端受控名 `ece-<docref>-<slug>.<ext>`，**不是**用户传的 filename。
- `engine_document_id`（Onyx user_file UUID）**仅写侧溯源**；
  `src/ece/consulting/registry.py` 注释里写明绝不做读侧键。
- 演示 3 份回填（步骤 1.4）以原 title 建行（不改名、不重传），`classification='public'`，
  幂等。

### O.2 结果级授权（步骤 2）

- `src/ece/consulting/permissions_filter.py` 是这条线的**唯一**入口。
- `source_type='user_file'` 旁路守卫；`(engine_name, title)` 查不到
  → fail-closed（不暴露存在）。
- 匿名 = 仅 `public`（A6 + 矩阵边缘）。
- 主体只来自凭据（不接受 body 自选）。
- 多 chunk → 同 title → 去重一张卡。

### O.3 时间盒授权（步骤 3）

- `check_permission(..., now=<date>)` 形参；`now=None` → UTC today（生产路径）。
- `valid_from <= now < valid_to`（半开）；`NULL` 视为 ±∞。
- deny + allow 两侧都看；既有用例断言不动（修改一律走 OEI-009 R-系 返工）。

### O.4 org scope 最小落位（步骤 4，OEI-010 hook）

- `Identity.org_id` / `PermissionScope.org_id` 加进 dataclass。
- 不改 `_subject_matches`（subject_type='org' 是 OEI-010 的活）。
- `tests/unit/test_org_scope.py::test_user_level_object_visible_to_owner_only`
  钉住"两条 scope 都能被表达"的最小判定。

### O.5 三份设计文档（步骤 5，**只写不实现**）

- `onyx-lab/OEI-009/workspace/09-design-engine-audit.md` — 引擎审计持久化
  （3 选项 + 持久化/采样/分区表代价 + 失败路径），推荐 3.C（分区表 + p=1.0 + 90 天）。
- `onyx-lab/OEI-009/workspace/10-design-org-scope.md` — scope 模型定稿
  + 组织级记忆写入权限 4 候选（A 管理员 / B 域经理 / C 同行评审 / D 版本化任意写）。
- `onyx-lab/OEI-009/workspace/11-design-assembly-step6.md` — `assembly.py`
  第 6 步改走 `ContentEnginePort` 的接法 + 侧信道风险 + 冷启动回落策略。

### O.6 改动文件清单（OEI-009）

| 类别 | 文件 |
|---|---|
| 新表 / 迁移 | `src/ece/migrations/versions/0009_engine_documents.py` |
| 新模块 | `src/ece/consulting/registry.py`、`src/ece/consulting/permissions_filter.py` |
| 改 | `src/ece/permissions/engine.py`（timebox + org_id）、`src/ece/identity/parser.py`（anonymous/from_engine_caller）、`src/ece/consulting/engine_merge.py`（接 sql_engine + identity）、`src/ece/consulting/router.py`（project_id form + 受控名 + register）、`scripts/check_api_docs.py`（编号标题）、`docs/API.md §13.6`、`docs/DATA_MODEL.md §3.1 §4.1` |
| 新测试（DB 无关） | `tests/unit/test_engine_documents_registry.py`、`tests/unit/test_check_permission_timebox.py`、`tests/unit/test_engine_merge_filter.py`、`tests/unit/test_org_scope.py` |
| 测试 fixture 装配 | `tests/unit/test_consulting_engine_merge.py::test_library_exposes_the_engine_group_in_onyx_mode`（加 register 调用，断言一字未改） |
| 凭据工装 | `onyx-lab/OEI-009/workspace/{backfill_demo_docs,step26_demo_falsifiable,step22_fail_closed,step33_timebox_e2e,step25_engine_status_branches}.py` |
| 设计文档 | `onyx-lab/OEI-009/workspace/{09,10,11}-*.md` |
| 证据 | `onyx-lab/OEI-009/evidence/{00a,00b,00-credentials,01,04,05,06,07,08}-*` |

### O.7 验收（A0–A14，对照 `OEI-009/TASK.md §5`）

| ID | 状态 | 证据 |
|---|---|---|
| A0 步骤 0 三项收尾 | PASS | `00a`（webhook 12×0）+ `00b`（api-docs 4→0）+ 步骤 0.3（scratch project id=2，演示项目仍 4=3+1 step26 文档） |
| A0b 凭据前置 | PASS | `00-credentials.txt`（200/200/200） |
| A1 映射契约落实 | PASS（合法停手 + 重启分支） | `01-engine-doc-key-mapping.json` + VERDICT §3 排除法裁定 `title` |
| A1′ 受控文件名 | PASS | `tests/unit/test_engine_documents_registry.py::test_deterministic_n5`（N=5 同名）+ step26 实际引擎收到 `ece-…md`（`05-per-result-filter-matrix.json`） |
| A2 登记表落位 | PASS | 迁移 `0009` 升 + `UNIQUE (engine_name, engine_filename)` + `04-backfill-demo-docs.json` |
| A3 3 份回填幂等 | PASS | `04-backfill-demo-docs.json`（第二次跑零新增） |
| A4 结果级授权 | PASS | `05-per-result-filter-matrix.json`（alice=4, anon=3, bob=3） |
| A5 fail-closed | PASS | `06-fail-closed.json`（probe 对 3 个身份全部不可见） |
| A6 无侧信道 + 匿名=public | PASS | `05` + `06` + `07-side-channel.txt`（静态 sha 三分支相同 = 引擎不影响静态；过滤项分布按 §13.6.3 规则计数但不暴露） |
| A7 static 零变化 + 3 分支不变 | PASS | `07-side-channel.txt`（ok/unavailable/no_hit 三状态实测 + static sha 三分支一致） |
| A8 时间窗 | PASS | `08-timebox-acl.json`（A=4, B=3 过期, C=4 恢复）+ `tests/unit/test_check_permission_timebox.py` 12 个边界 |
| A9 org scope 最小落位 | PASS | `tests/unit/test_org_scope.py`（Identity.org_id 存在、PermissionScope.org_id 存在、check_permission 不读 org_id、user-level 可见性规则 + `test_no_memory_table_or_interface_added` 守卫） |
| A10 三份设计文档 | PASS | `workspace/{09,10,11}-*.md` |
| A11 测试与收尾 | PASS | 49 个新 DB 无关测试 + 5 个集成证据；详见 §3 / §6 of REPORT |
| A12 文档 + 提交 | 待 commit（no push） | §7 |
| A13 合规 | PASS | 0 凭据值落盘；未碰 Onyx / compose / .env / 9 容器 restarts=0；未改 36 个种子对象与三域业务断言；未 push |
| A14 无用户截图 | PASS | 全部机器可校验（HTTP 状态 + JSON 内容 + sha + 索引查询输出） |

### O.8 转出（移交下一刀 / 当前未做）

- **引擎调用审计持久化**（OEI-009 §5.1 设计未实现）→ 列入 OEI-010 之前的某刀。
- **`check_api_docs.py` 与迁移同源的回归钉**：若 §11/§12 改章节标题，
  解析器必须同步；不是本刀范围，是 §13.6.1 落地后的伴生约束。
- **org scope 完整化**（`_subject_matches` 加 `'org'` 分支）→ OEI-010。
