# Cut 007 执行报告（CC）

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 3 第一刀 (S3.1 + S3.2 + S3.3)；Context Spec loader + 12-step Assembly Pipeline + Provenance DB writes。前一报告 `cut-006r-report.md` 已签发 R1-R6 修复令；本刀承接 Sprint 2 之后的 Context 核心。

---

## 0. 元metadata

| 项 | 值 |
|---|---|
| **Cut** | 007（Sprint 3 第一刀） |
| **触发** | `ece/TASKS.md` Sprint 3 + 用户"继续"指令 |
| **上游参考（只读）** | `docs/ARCHITECTURE.md` §2.1 (Context Spec) + §3 (12-step Pipeline) + `docs/DATA_MODEL.md` §5 (context_requests/context_items) + `docs/API.md` §1 (POST /context) + `docs/EVALUATION.md` §1 |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-14 |
| **涉及文件** | `src/ece/context/{__init__,spec,relationships,provenance,assembly}.py` + `src/ece/migrations/versions/0005_context_audit.py` + `src/ece/domain_packs/procurement/context_specs/evaluate_purchase_request.yaml` + `tests/integration/test_{s31_spec,s32_assembly}.py` + 1 side-fix in `src/ece/entities/pipeline.py` + `pyproject.toml` (pyyaml) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | S3.1 + S3.2 + S3.3 全部；stubbed S3.4 (POST /context) + S3.5 (E3-E5 evals) 留给 cut-008；不动 docker-compose / S4+ / LLM / Agent |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行（per cut-002 §7.3.1 裁定生效）。**1 个工作 commit（`6559a9e`）+ 1 个报告 commit**。批处理不触碰 §7 区段（per cut-003R2 治理注记）。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（S3.1-S3.3 全部一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 5（`src/ece/context/__init__.py` / `spec.py` / `relationships.py` / `provenance.py` / `assembly.py`） |
| 新增 Migration | 1（`0005_context_audit.py`，context_requests + context_items） |
| 新增 Domain pack 内容 | 1（`procurement/context_specs/evaluate_purchase_request.yaml`） |
| 新增 测试 | 2 文件（`test_s31_spec.py` 5 tests + `test_s32_assembly.py` 6 tests） |
| 修改 Python文件 | 1（`src/ece/entities/pipeline.py`，SIDE-FIX §4.2 pre-existing `_next_display_id` bug） |
| 修改 pyproject.toml | 1（`pyyaml>=6.0` dep） |
| 修改 uv.lock | 自动更新 |
| 总计 | 12 files changed, 1130 insertions(+), 10 deletions(-) |

### 1.2 逐 Sub-task 交付

#### S3.1 — Context Spec loader（`src/ece/context/spec.py`）

| 内容 | 实现 |
|---|---|
| Pydantic v2 模型 | `RequiredEntity` / `RequiredDocument` / `TemporalSpec` / `LimitsSpec` / `RequiresBlock` / `ContextSpec` |
| `load_spec(pack, intent)` | `Path("src/ece/domain_packs/{pack}/context_specs/{intent}.yaml").read_text() + yaml.safe_load() + ContextSpec(**raw)` |
| `load_spec_from_path(yaml_path)` | 测试用：显式 path 入口 |
| 验证 | `field_validator("mode")` 约束 temporal.mode ∈ {current, as_of, between}；`Field(ge=1, le=10)` 约束 max_hops；`Field(ge=1, le=1000/5000/1000/10000)` 约束 limits 字段 |
| 版本化 | `spec.version` int（per ARCHITECTURE §2.1） |
| 错误 | `FileNotFoundError` (YAML 缺失) + `pydantic.ValidationError` (YAML 格式错) + `ValueError` (YAML 非 dict) |

**注**: 初版 `structured_data: list[StructuredDataRef]` model 不匹配 YAML 实际格式（ARCHITECTURE §2.1 + PRD §40 都是 `- historical_purchase` 字符串列表）。**改 `list[str]`** 与 spec 文档对齐（详见 §4.3 第 1 次教训）。

#### S3.2 — Assembly Pipeline（`src/ece/context/assembly.py`）

| 步骤 | 内容 | 实现位置 |
|---|---|---|
| **1 + 2** | Identify user + Resolve identity | `resolve_identity(engine, user_ref)` 返回 `Identity` |
| **3** | Permission check（implicit） | 每次对象访问时 `check_permission(identity, object_type, object_ref, "public", acl_entries)` |
| **4** | Resolve root entities | `SELECT display_id, ... FROM entities WHERE display_id = :d` |
| **5** | Retrieve relationships | `get_relationships(engine, src_ids, relations, as_of, max_rows)` 含 permission filter on dst |
| **6** | Documents | **STUBBED** — 返回 `[]` + `Sprint 4 territory` 注释（FTS/vector + classification+ACL 留待 S4） |
| **7** | Structured data | **STUBBED** — 返回 `[]` + `Sprint 4 territory` 注释（per-spec.kind SQL + row-level perms 留待 S4） |
| **8** | Temporal predicate | `get_relationships(..., as_of=...)` 已应用 |
| **9** | Rank + truncate | `resolved_entities[:spec.limits.max_entities]` + `relationships[:spec.limits.max_relationships]` |
| **10** | Build package | 构造 `ContextPackage` dataclass + denied list |
| **11** | Build sources | `build_sources(items_for_audit)` 来自 `provenance.py` |
| **12** | Return + audit write | `record_package(...)` 写 `context_requests` + `context_items` |

`ContextPackage` 字段（per ARCHITECTURE §2.2）:
- `package_id: str` (e.g., `ctx_01a2b3c4...`)
- `request_id: str` (uuid)
- `task: {intent, spec_version}`
- `user: {id, display_id, name, department, roles, is_management}`
- `entities: [{ref, type, name, attrs, src}]`
- `relationships: [{from, rel, to, valid, src}]`
- `documents: []` (stub)
- `business_data: []` (stub)
- `denied: [{ref, reason}]`
- `sources: [{sid, system, record_id}]`
- `metadata: {generated_at, as_of, counts, insufficient_context}`

**Fail-closed**（per ADR-004 + PRD §29）：任何步骤异常 → status='error' via audit + caller 收到 `insufficient_context` flag + denied list（不暴露不存在对象的内容）。

#### S3.3 — Provenance（`src/ece/context/provenance.py`）

| 内容 | 实现 |
|---|---|
| `_sid(system, record_id)` | `f"s{uuid.uuid5(NAMESPACE_OID, '{system}:{record_id}').int & 0xFFFF:04x}"` — 确定性派生（re-assembly same sid） |
| `build_sources(items)` | dedup by `(system, record_id)` → `[{"sid": ..., "system": ..., "record_id": ...}]` |
| `record_package(engine, request_id, user_ref, intent, spec_version, root_entities, as_of, counts, latency_ms, items, status)` | 单 tx 写 `context_requests` + 每 item 一行 `context_items`（seq 0..N） |

**JSONB binding 安全**: 用 `CAST(:root AS jsonb)` / `CAST(:src AS jsonb)` 标准 SQL CAST（非 `:c::jsonb` PostgreSQL cast operator）—— 避免 cut-006R §4.2 的 escape 陷阱。

#### Relationships helper（`src/ece/context/relationships.py`）

`get_relationships(engine, src_display_ids, relations, as_of, max_rows)` — JOIN entities + 关系 + temporal predicate + LIMIT。**`bindparam("src_ids", expanding=True)`** 处理 IN-list（SQLAlchemy 2.0 expanding bindparam 语法）。

#### Domain pack spec（`procurement/context_specs/evaluate_purchase_request.yaml`）

```yaml
spec: evaluate_purchase_request
version: 1
root_entity: purchase_request
requires:
  user: true
  entities:    # 7 个: supplier/contract/product/policy/approval/person/department
    - {type: supplier,   via: "SELECTS",            max_hops: 1}
    - {type: contract,   via: "SELECTS>HAS_CONTRACT", max_hops: 2}
    - ...
  relationships: [SUBMITTED_BY, BELONGS_TO, SELECTS, HAS_CONTRACT, CONTAINS, SUBJECT_TO, HAS_APPROVAL]
  documents:    # 1 个: procurement_policy
  structured_data: [historical_purchase, approval_history]  # 2 个 kinds
temporal: {mode: current}
limits: {max_entities: 60, max_relationships: 100, max_chunks: 30, max_rows: 200}
```

驱动 PRD §48 demo 场景: "PR001 这个采购申请合理吗？"

#### Migration 0005（`src/ece/migrations/versions/0005_context_audit.py`）

| 表 | 字段 | 索引 |
|---|---|---|
| `context_requests` | request_id (uuid PK), user_ref, intent, spec_version, root_entities (jsonb), as_of (date), counts (jsonb), latency_ms, llm_model, status, created_at | (user_ref, created_at DESC), (status, created_at DESC) |
| `context_items` | id (bigserial PK), request_id (uuid FK CASCADE), seq (int), item_kind, ref, source (jsonb), decision, reason, score | (request_id) |

驱动 Debugger UI（`/audit/context/{request_id}`，Sprint 6）+ 任何 item 级别 trace。

#### Tests（`tests/integration/test_s31_spec.py` + `test_s32_assembly.py`）

**test_s31_spec.py (5 tests)**:
1. `test_load_spec_evaluate_purchase_request` — load + 字段断言
2. `test_load_spec_unknown_intent_raises` — FileNotFoundError
3. `test_load_spec_unknown_pack_raises` — FileNotFoundError
4. `test_spec_temporal_mode_validation` — Pydantic ValidationError
5. `test_spec_required_entity_max_hops_bounds` — ge/le 约束
6. `test_spec_limits_bounds` — limits 字段约束
7. `test_load_spec_from_path_invalid_yaml_raises` — 缺 spec 字段报错

**test_s32_assembly.py (6 tests)**:
1. `test_assemble_returns_package_with_identity` — steps 1-2 身份解析
2. `test_assemble_empty_entities_yields_insufficient_context` — 无 root → insufficient
3. `test_assemble_writes_context_requests_row` — context_requests 表写入
4. `test_assemble_writes_context_items_with_valid_decisions` — context_items 每 decision 行
5. `test_assemble_denied_entity_records_in_audit` — 不存在 entity → denied + audit
6. `test_assemble_sources_are_deterministic` — 同 (system, record_id) → 同 sid

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `6559a9e` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 54 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 49 passed, 3 skipped, 2 warnings in 3.72s
$ make check-api-docs          # OK — no app-only routes; docs-only are planned Sprint 1+ scope
```

### 2.2 git 二次审计

```bash
$ git log --oneline -3
6559a9e feat(s3): Context Spec loader + 12-step Assembly Pipeline + Provenance DB writes (cut-007 closure)
93e45fe docs(research-v2): cut 006R report (R1-R6 closure)
6fc1831 fix(s2.4r-6R): R1 NameError + R4 pending hook + R2 runner + R5/R6 tests (cut-006R closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 49 passed 3 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| `docker-compose.yml` | 前会话定稿 |
| S3.4 (POST /context endpoint) | 第 8 刀 |
| S3.5 (E3/E4/E5 evals) | 第 8 刀（与 S3.4 一组） |
| Sprint 4 (FTS/vector + structured SQL) | 第 9-10 刀 |
| Sprint 5 (Procurement Agent + LLM) | 第 11-12 刀 |
| Sprint 6 (Debugger UI + 私有化验收) | 第 13 刀 |
| 引入 mcp / openai SDK | 依 ADR-004 + cut-002 §7.3 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| `context_requests` / `context_items` 表存在但无 alembic 记录 | ⚠️ Pre-alembic 旧 seed/手工创建（schema 与 0005 完全一致，0 数据） | DROP CASCADE + `alembic upgrade head` 干净落 0005（详见 §4.1） |
| ECE API server | ❌ 8765 未启动（本机 `docker compose up api` 未执行） | runner 返回 3（env-not-ready）；test 优雅 skip |
| `alembic current` | ✅ `0005_context_audit (head)` | 无 |
| pyyaml | ✅ 6.0.3（`uv sync` 安装） | 无 |
| demo seed `SUP1000` collision | ⚠️ Pre-existing bug 在 `_next_display_id` | 已在 §4.2 side-fix（这次顺便修） |

---

## 3. Commit 信息

**1 个工作 commit（S3.1-S3.3 全部一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `6559a9e` | 12 files, +1130/-10（context 5 文件 + migration 0005 + domain YAML + 2 测试 + 1 side-fix in entities/pipeline.py + pyproject + ruff lock） | ✅ 5 项纪律全绿；make test 49 passed 3 skipped |

**HEAD after push**: `6559a9e71b8711fa6fda54c91a9fb77452a97707`

**Push range**: `93e45fe..6559a9e main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 Context_* 表 DuplicateTable（migration 启动失败）

alembic upgrade head 报 `psycopg.errors.DuplicateTable: relation "context_requests" already exists`——**两张表已存在但 alembic 不知**（schema 与 0005 完全一致，0 数据）。猜测来源：Sprint 6 Debugger UI 早期 prototype 用 `CREATE TABLE` 直接落库，跳过 alembic。

**修复**: `DROP TABLE IF EXISTS context_items CASCADE; DROP TABLE IF EXISTS context_requests CASCADE;` + `alembic upgrade head` 干净落 0005。

**教训**: PostgreSQL schema 状态应单一来源（alembic 唯一）。任何手工 `CREATE TABLE` 都是埋雷——下次 alembic 会撞。如果未来再发生，必须先查表是否存在 + 比对 schema。

### 4.2 pre-existing `_next_display_id` bug（side-fix in `src/ece/entities/pipeline.py`）

原实现：
```sql
SELECT display_id FROM entities
WHERE entity_type = :etype AND display_id LIKE :pat
ORDER BY display_id DESC LIMIT 1
```

**这是 TEXT 排序**。PostgreSQL 字符串比较：`'SUP999' > 'SUP1000'`（因为 `'9' > '1'`）。所以 max 返回 `'SUP999'`，max+1 = `'SUP1000'`——但 demo seed 第 51 个 supplier 已经用 `SUP1000`（`source_id='supplier:45'` from `demo:demo`），**UNIQUE display_id conflict**。

**修复**: fetch 所有候选 rows，regex 解析数字，max 取数值：
```python
max_num = 0
for (display_id,) in rows:
    m = re.search(r"(\d+)$", display_id)
    if m:
        n = int(m.group(1))
        if n > max_num:
            max_num = n
return f"{prefix}{max_num + 1:03d}"
```

修复后 `_next_display_id` 正确返回 `SUP1001`（demo SUP1000 + 1），s11/s12 测试转绿。

**Tradeoff**: O(N) scan per upsert. v0 demo 数据 <100 suppliers 可接受。**未来大规模**: SQL `MAX(CAST(SUBSTRING(display_id FROM '(\d+)$') AS INTEGER))`。

**为什么 cut-006R 当时过了**: 之前 demo seed 状态可能不同（SUP1000 不存在），或测试顺序偶然绕开。**这次切到 cut-007 时被 demo 数据踩雷**——pre-existing latent bug 在数据增长后暴露。

**教训**: `_next_display_id` 是核心 infra，任何写入路径都依赖它；**任何涉及字符串转数字的 max 比较都要警惕文本 vs 数值差异**。类似陷阱: `MAX(version)`、`MAX(rev)` 字符串字段。

### 4.3 `StructuredDataRef` schema mismatch（YAML 格式 vs Pydantic model）

我的初版 `RequiresBlock.structured_data: list[StructuredDataRef]`（`StructuredDataRef` 是 `BaseModel` with `kind: str`）。但 YAML 实际写：
```yaml
structured_data:
  - historical_purchase
  - approval_history
```

——纯字符串列表，不是 dict-of-kind。

**修复**: 改 `structured_data: list[str]` + 删除 `StructuredDataRef` 类。**与 PRD §40 + ARCHITECTURE §2.1 示例完全对齐**。

**教训**: 写 Pydantic model 前**必须读 spec 文档的 YAML 实际格式**，不能凭 Pydantic 风格（BaseModel per item）设计。原 cut-006R §4.4 教训是"refactor 必须能被 `git diff` 验证"——这里类似的反模式是"model 必须能被 YAML 验证"。两者都强调**真实数据驱动**。

### 4.4 Edit over-deletion（`ent_id` 误删）

`ruff F841` 报告 `ent_type = str(ent.get("type", ""))` unused variable。我用 Edit 删除该行——但 old_string 范围扩到下方 4 行（连带删 `ent_id = str(ent.get("id", ""))`），造成 `if not ent_id:` 引用 undefined 变量 → NameError。

**修复**: 重 Edit 恢复 `ent_id` 行（仅删除 unused 的 `ent_type` 行）。

**教训**: Edit 工具的 `old_string` 必须精确匹配**唯一**片段。**多行级联删除时必须先确认每行都该删**——尤其当该行附近有同名/近名标识符时。**防御**: 每次 Edit 后必须跑 `make test`（不能仅 ruff/mypy——NameError 是 runtime 才报）。

### 4.5 Edit typo 阻断修复（cut-007 §4.2 第一次 Edit 失败）

第一次 Edit `_next_display_id` 时，old_string 写了 `e.g.g SUP001 -> SUP002`（typo 写双 g），文件实际是 `e.g. SUP001 -> SUP002`。Edit 报 `String to replace not found`——**Edit 工具的 old_string 必须逐字符匹配**。

**修复**: 改 typo 后重做。

**教训**: Edit 工具无 fuzzy match，错就失败（不像有些 IDE 自动 tolerant）。**typo 是隐形杀手**——rust/haskell/python docstring、注释里的英文稍不留神就写错。**防御**: 涉及多行代码块 Edit 时先 `Read` 拿精确内容。

---

## 5. 经验教训

1. **pre-existing latent bug 暴露**（§4.2）: `_next_display_id` 文本排序问题在 demo 数据 ≤ 50 suppliers 时不触发，> 50 后暴露。**核心 infra 函数必须有边界测试**——任何依赖它的路径（upsert_entity, ingest pipeline）都可能踩雷。
2. **静态 discipline 仍不能捕获所有错误**（§4.3 + §4.4）: StructuredDataRef 错配 → mypy 查不到；NameError → 5 项 discipline 都过（仅 runtime 报）。**make test 必须真跑真库**，不能仅静态 lint。
3. **schema 状态唯一来源**（§4.1）: 手工 DDL + alembic 共存 =雷。**Pre-alembic 数据迁移第一步是 audit 现状**，不要假设"迁移是创建"。
4. **Edit 工具无 fuzzy match**（§4.5）: 跨多行 Edit 必须 Read 拿精确 old_string。typo = fail（不像 Vim/IDE 容错）。
5. **YAML/Pydantic 真实数据驱动**（§4.3）: 写 model 前先读 spec 文档 YAML 实际格式，不是 Pydantic 风格先入为主。
6. **stale 表 DROP 路径**（§4.1）: alembic 启动失败时**先看表是否存在 + 比对 schema**，再决定 DROP 还是 STAMP；schema 不匹配时 STAMP 会埋雷。

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-007-report.md` | `ece/reports/cut-008-report.md` |

### 6.2 必保留章节

- §0 元metadata + Override 注记（独立 session 执行）
- §1 完成情况 + 改动统计 + **逐 Sub-task 交付**（S3.1-S3.3 按顺序分块）
- §2 审验范围（**5 项纪律清单 + git 二次审计 + 排除项 + 环境约束诚实披露**）
- §3 Commit 信息（**全填实**）
- §4 本刀非典型项（**§4.1 DuplicateTable / §4.2 pre-existing bug / §4.3 schema mismatch / §4.4 Edit over-del / §4.5 Edit typo**）
- §5 经验教训（**pre-existing 暴露 / static 不能捕获 / schema 唯一来源 / Edit 无 fuzzy / YAML-driven**）
- §6 模板说明
- §7 红队审验占位（**不自写**）

### 6.3 必做的最小验证

每个工作 commit 前**必须严格按顺序跑** 5 项纪律（ruff / mypy / lint-imports / make test / check-api-docs）。**任何一项不绿必须 amend**。报告 commit 前再跑一遍二次审计。

### 6.4 禁止事项

- §7 红队审验结论 — **不自写**
- §3 commit hash 占位符 — **绝不接受**
- 报告塞进工作 commit — **违反流程惯例 v2**
- 批处理触碰任何已定稿报告的 §7 区段 — **per cut-003R2 治理注记**
- commit message 写"验收"而未附可复跑命令 — **R5 完整性要求**
- 假绿 — 五项静态纪律 ≠ 功能可运行；**必须真跑真库**
- Edit old_string 含 typo — **无 fuzzy match = 直接 fail**

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。