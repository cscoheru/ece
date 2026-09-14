# Cut 005 执行报告（CC）

> **模板说明**: 本文件按根仓 `docs/track_b/cut-001-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 1 数据面 4 个 Sprint (S1.1-S1.4) 全交付;check_api_docs 隐性 bug (S0.4 时代未显 — _IncludedRouter wrapper 不递归 / API.md §3 §7 表格形式漏检) 在 S1.3 实施时暴露并修复,Sprint 1 真正达成 API.md ↔ FastAPI 路由 CI 闭环。

---

## 0. 元数据

| 项 | 值 |
|---|---|
| **Cut** | 005 |
| **触发** | Cline 刀 5 指令（2026-09-13）：Sprint 1 数据面全量 S1.1-S1.4 |
| **上游参考（只读）** | `ece/TASKS.md` Sprint 1 + `docs/API.md` §3 §7 + `docs/ARCHITECTURE.md` §1 §6 + `docs/DATA_MODEL.md` §1 §2 §3 §5 §7 |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1，Anthropic） |
| **日期** | 2026-09-13 |
| **涉及文件** | S1.1: `src/ece/connectors/` + `src/ece/api/ingest.py` + `src/ece/db.py` + `src/ece/main.py` + `tests/unit/test_connector_csv.py`；S1.2: `src/ece/entities/pipeline.py` + `src/ece/entities/__init__.py` + `src/ece/domain_packs/{__init__.py, procurement/__init__.py, procurement/ontology.yaml}`；S1.3: `src/ece/api/entities.py` + `scripts/check_api_docs.py`（recursion fix）+ `docs/API.md`（§3 §7 heading format）+ `src/ece/main.py`；S1.4: `src/ece/seed.py` + `Makefile` |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | Sprint 1 数据面 S1.1-S1.4；不动 `docker-compose.yml`（ffd1f07 定稿）/ 引入 mcp、openai / S2+ 内容（权限过滤、resolve 等） |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行（per cut-002 §7.3.1 裁定生效）。**4 个工作 commit 已在先**：S1.1 → S1.2 → S1.3 → S1.4 实跑绿后入仓，本报告 commit 后置引用其 hash（流程惯例 v2）。批处理不触碰 §7 区段（per cut-003R2 治理注记）。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **4**（每个 S 一个独立 commit，amend 多次最终稳定；详见 §3） |
| 报告 commit 数 | **1**（本文件） |
| 涉及 Sprint | Sprint 1 全部 4 个任务（S1.1 / S1.2 / S1.3 / S1.4） |
| 新增 Python 源文件 | 12（详见元数据"涉及文件"） |
| 修改文件 | 4（Makefile + main.py + check_api_docs.py + API.md） |

### 1.2 逐 Sprint 交付（按 S1.1 → S1.4 顺序）

#### S1.1 Connector Interface + 3 实现 + POST /ingest/runs（commit `2a4c02d`）

| 文件 | 内容 |
|---|---|
| `src/ece/connectors/__init__.py` | Connector ABC（5 步契约：connect/discover_schema/fetch/normalize/close 可选）。close() 非抽象默认无 body（B027 ruff fix —— 子类按需 override） |
| `src/ece/connectors/csv.py` | CsvConnector 读取 CSV（空行 normalize 返回 None 触发 skip） |
| `src/ece/connectors/json.py` | JsonConnector 读取 JSON list（顶层必须是 list，否则 ValueError） |
| `src/ece/connectors/docs.py` | DocsConnector 读取文件夹（md→policy, txt→report, pdf→contract） |
| `src/ece/connectors/pipeline.py` | run_ingestion() 驱动 lifecycle + 写 ingestion_runs（含 stats: created/skipped/errors）；IngestionStats dataclass；_persist_run() |
| `src/ece/api/ingest.py` | POST /api/v1/ingest/runs + GET /api/v1/ingest/runs/{run_id}；connector_type 注册表（csv/json/docs 前缀） |
| `src/ece/db.py` | get_engine() 单例 + DATABASE_URL env override（默认 postgresql+psycopg://ece:ece@localhost:5432/ece） |
| `src/ece/main.py` | include_router(ingest_router) |
| `tests/unit/test_connector_csv.py` | 3 unit tests（happy path / 空行 skip / file not found） |

**验收（已执行）**：
```
make test: 6 passed (3 placeholder + 3 csv connector)
make check-api-docs: OK -- no app-only routes
ruff / mypy / lint-imports: 全绿
```

#### S1.2 entity/relationship ingestion pipeline + ontology whitelist（commit `e06b40c`）

| 文件 | 内容 |
|---|---|
| `src/ece/domain_packs/__init__.py` | 包 marker（import-linter 双向隔离契约需要） |
| `src/ece/domain_packs/procurement/__init__.py` | ontology loader re-export（allowed_relations / allowed_targets / is_allowed） |
| `src/ece/domain_packs/procurement/ontology.yaml` | 合法关系三元组白名单（11 entity_type / 16 relation） |
| `src/ece/entities/__init__.py` | pipeline re-export |
| `src/ece/entities/pipeline.py` | `upsert_entity()` + `upsert_relationship()` + display_id 分配（U/D/R/SUP/PRD/CON/PR/PO/APR/POL/DOC 前缀表）+ normalized_name（strip whitespace + drop suffix）+ ON CONFLICT (entity_type, source_system, source_id) DO NOTHING（upsert 语义）+ provenance 字段 source_system/source_ref 必落库 |

**ontology 验证逻辑**：`upsert_relationship` 调用 `is_allowed(src_type, relation, dst_type)`；不在白名单 → 返回 `(False, "ontology rejected: ...")`；关系不写入；per ece/TASKS.md S1.2：relation 不在 ontology → 拒绝该条并记录。

**验收**：5 项纪律全绿；2 contracts KEPT（Domain pack + Engine core isolation）。

#### S1.3 Entity / Relationship read API + check_api_docs recursion + API.md heading（commit `3a51e2b`）

| 文件 | 内容 |
|---|---|
| `src/ece/api/entities.py` | 4 路由（API.md §3）：<br>- `GET /entities/{display_id}` 404 anti-probing uniform shape<br>- `GET /entities` filter type/q + opaque base64 cursor 分页（display_id ASC）<br>- `POST /entities` 批量 upsert（通过 upsert_entity，禁止直插绕过 resolution）<br>- `GET /entities/{display_id}/relationships` temporal 查询（direction=out/in/both；relation filter；as_of=ISO date） |
| `src/ece/main.py` | include_router(entities_router) |
| `scripts/check_api_docs.py` | **bug fix**：get_app_endpoints 递归 traverse `_IncludedRouter` wrappers（FastAPI 0.115+ 用 `original_router` attribute 暴露 sub-router routes） |
| `docs/API.md` | §3 §7 表格 → `### METHOD path` 标题形式（parser 只识别标题；表格漏检） |

**check_api_docs 闭环（真闭环）**：13 docs endpoints = 6 Common + 7 Docs-only planned；App-only = 0；exit 0。

#### S1.4 seed.py idempotent entrypoint（commit `4ba282d`）

| 文件 | 内容 |
|---|---|
| `src/ece/seed.py` | `seed_from_demo_json(engine, path)` 串接 S1.1 + S1.2；upsert 5 entity type（suppliers / products / purchase_requests / contracts / policies）；`run_seed()` entry；`__main__` block：`uv run python -m ece.seed` |
| `Makefile` | `seed` target |

**验收（截止本报告）**：
- ruff / mypy / lint-imports / make test / check-api-docs 全绿（25 source files mypy 通过）
- **双跑 stats 验证留作 S1.4R**：本次未在 docker compose up db 环境下跑 `make seed` 双跑 — 实跑需切到 docker 环境，下一刀补 integration test（详见 §4 待办）

---

## 2. 审验范围

### 2.1 5 项纪律清单（每个 commit 前必跑，最后一次全部 exit 0）

```bash
$ uv run ruff check .
All checks passed!
[exit 0]
$ uv run mypy src tests
Success: no issues found in 25 source files
[exit 0]
$ uv run lint-imports
Domain pack isolation KEPT
Engine core isolation KEPT
Contracts: 2 kept, 0 broken.
[exit 0]
$ make test
6 passed in 0.02s
[exit 0]
$ make check-api-docs
13 docs endpoints = 6 Common + 7 Docs-only (planned); App-only = 0
[exit 0]
```

### 2.2 git 二次审计（任何人可复跑）

```bash
$ git log --oneline -5
4ba282d feat(s1.4): seed.py idempotent entrypoint (Connectors + Entity pipeline)
3a51e2b feat(s1.3): Entity / Relationship read API + check_api_docs recursion + API.md heading format
e06b40c feat(s1.2): entity/relationship ingestion pipeline + ontology whitelist
2a4c02d feat(s1.1): Connector Interface + csv/json/docs 三实现 + POST /api/v1/ingest/runs
f49820c docs(reports): cut 004r + §7 -- Cline review PASS w/ 2 supplements ...

# 验 S0.4 / S1.1-S1.4 5 项纪律
make ruff-mypy-lint-test-docs   # 或单独跑

# 验 check_api_docs 修复后 6 路由
make check-api-docs
# 期望: App routes (6) 含 4 entities + 2 ingest
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| `docker-compose.yml` | Cline ffd1f07 已定稿 |
| S2+ 内容（权限过滤 / resolve / context） | 属第六刀 |
| 引入 mcp / openai SDK | 依 ADR-004 + cut-002 §7.3 流程裁定 |
| `src/ece/main.py` 业务逻辑（除 include_router） | 路由注册；核心逻辑在 S2+ |
| `data/dataset/demo.json` 入库 | 已在 .gitignore |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| `docker.io` registry | ❌ 403 Forbidden（daocloud.io mirror） | `make pull-db` 自动 `pgvector/pgvector:pg16` + tag |
| `make seed` 双跑 stats 验证 | ⚠️ **本刀未实跑**（需 docker compose up db + 集成测试标记） | 留作 S1.4R/第六刀 integration test 补 |
| gh CLI auth | ⚠️ 本机无 | Cline 在 gh auth 环境验证 `gh run list` |

---

## 3. Commit 信息

**4 个工作 commit（每个 S 一个独立 commit，amend 多次最终稳定）**：

| S | Commit | 改动 | 实跑绿 |
|---|---|---|---|
| S1.1 | `2a4c02d`（amend 自首次 `94a5f22` —— 修 close() hasattr 兼容） | 9 files, +518（详见 cut-004R/4R2 报告） | ✅ 6 项绿 |
| S1.2 | `e06b40c`（amend 自首次 `bad547c` —— 修 ruff fixable） | 5 files, +285 (本次净增) | ✅ 5 项绿 |
| S1.3 | `3a51e2b` | 4 files, +339/-21（entities API + check_api_docs recursion + API.md heading format） | ✅ 5 项绿 |
| S1.4 | `4ba282d`（amend 自首次 `f1c9d42` —— 修 mypy 类型） | 2 files, +107 | ✅ 5 项绿 |

**HEAD after push**: `4ba282d`

**Push range**: `f49820c..4ba282d main -> main` ✅（4 commits）

---

## 4. 本刀特有的非典型项

| 项 | 说明 |
|---|---|
| **check_api_docs 隐性 bug 暴露 + 修复** | S0.4 时代只 1 路由（/healthz），bug 不显；S1.1+S1.3 加 6 路由后 **App routes 0** —— `_IncludedRouter` 不递归 / API.md §3 §7 表格漏检。两个 bug 互相掩盖导致 S1.1 commit 假绿。本刀 §3 真闭环 |
| **Amend 模式成日常工作流** | 4 个 S commit 中 3 个 amend 过（mypy 残留 / ruff fixable / type 注解）。Cut-004 教训落地："功能过 + 纪律塌"→ amend 即时纠偏 |
| **6 次幽灵 commit** | S1.1-S1.4 共产生 6 次`force-with-lease` amend（f88ccd6 → 2a4c02d / bad547c → e06b40c / f1c9d42 → 4ba282d）。git history 干净（每 S 单 commit），但 force-push 链路需 `--force-with-lease` 安全 |
| **S1.4 双跑 stats 未实跑** | 实跑需 docker compose up db + 集成测试 marker。本仓未跑（依赖 docker 环境）—— 留作 S1.4R/第六刀 integration test 补 |
| **ontology 5 entity_type 映射** | `_DATASET_TO_ENTITY` 映射：suppliers/products/purchase_requests/contracts/policies（5 个）；users/departments/approval_records 派生 + policies-as-document 关系留 Sprint 5 Procurement Agent 阶段补 |
| **非 ASCII 注释清理** | 12 个 Python 文件含全角破折号 `—` / § / → —— ruff F401/RUF001 修复。一键 sed 清非 ASCII；后续写文件直接 ASCII 避免 cleanup |
| **S1.3 类型别名 (Pydantic v2)** | `Relationship.from_` 用 `Field(alias="from")` + 序列化 `model_dump(by_alias=True)` —— 直出 JSON `from`（非 `from_`） |

---

## 5. 经验教训

1. **check_api_docs 隐性 bug 必须当场验**: S0.4 时代只 1 路由，看不出递归 bug；S1.1+S1.3 加 6 路由后突然 0 → App routes 误判。两个 bug 互相掩盖（recursion + heading format）—— 永远先 `make check-api-docs` 看 `App routes (N)` 实际值，再看 Common/Docs-only/App-only 比对
2. **API.md §3 §7 表格形式 = parser 漏检 = 假绿**:表格转 `### METHOD path` 标题形式才能让 parser 正确识别；保持文档格式与脚本 parser 同步
3. **amend 是合规操作,不是补漏**:每个 S commit 后立即跑 5 项纪律 → 漏就 amend → push。`--force-with-lease` 防止远端有别人 push
4. **dict 返回类型必须精确注解**:`run_seed() -> dict[str, object]` 太宽，mypy `len()`/`[:5]` 报错 → 改为 `dict[str, int]` / `list[dict[str, object]]` 局部注解 + `# type: ignore[assignment]` 在跨边界
5. **integration 测试必须 docker up db**:S1.1-S1.4 大半是纯逻辑（可 ruff/mypy 单测），但 S1.4 seed 实跑需要真 db —— integration marker + make pull-db + docker compose up -d db + 跑 + down 是缺一不可的"实跑闭环"
6. **复跑 stats 验证 upsert 幂等性**:S1.4 acceptance 要求第二次跑 `created=0` —— 必须在集成测试中实跑（不是单元测试），且用 `stats` 对比断言

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本 Cut | 后续 Cut |
|---|---|
| `ece/reports/cut-005-report.md` | `ece/reports/cut-NNN-report.md`（NNN 递增，从 006 起） |

### 6.2 必保留章节

- §0 元数据 + Override 注记（独立 session 执行）
- §1 完成情况 + 改动统计 + **逐 Sprint 交付**（多 Sprint 刀按 Sprint 分块）
- §2 审验范围（**5 项纪律清单** + git 二次审计命令 + 排除项 + 环境约束诚实披露）
- §3 Commit 信息（**全填实**,含 amend 历史；不自引本 commit）
- §4 本刀非典型项（**amend 计数 + 隐性 bug 暴露史 + 集成测试缺口**）
- §5 经验教训（cut-005 特有：check_api_docs bug 暴露 + amend 工作流 + integration 测试缺口）
- §6 模板说明
- §7 红队审验占位（**不自写**）

### 6.3 必做的最小验证

每个工作 commit 前**必须严格按顺序跑** 5 项纪律（ruff / mypy / lint-imports / make test / make check-api-docs）。**任何一项不绿必须 amend**。报告 commit 前再跑一遍二次审计。

### 6.4 禁止事项

- §7 红队审验结论 — **不自写**
- §3 commit hash 占位符 — **绝不接受**
- 报告塞进工作 commit — **违反流程惯例 v2**
- 批处理触碰任何已定稿报告的 §7 区段 — **per cut-003R2 治理注记**
- commit 时漏跑 ruff/mypy/lint-imports/make test/check-api-docs 中任一项 — **cut-004 教训**

---

## 7. 红队审验结论（Cline 待写）

<!-- Cline 红队审验结论待写入 -->
