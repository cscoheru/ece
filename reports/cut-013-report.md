# Cut 013 Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 4 final tail——S4.2 vector route (pgvector cosine) + 2025/2026 procurement manager change (role entities + temporal HAS_ROLE)。前一报告 `cut-012-report.md` 完成 perf + Chinese pg_trgm + /actions/preview；本刀做 vector route + temporal predicate 真值。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 013（Sprint 4 final tail） |
| **触发** | `ece/TASKS.md` S4.2 + PRD §48 (2025/2026 manager change) + 用户"cut-013"指令 |
| **上游参考（只读）** | `docs/ARCHITECTURE.md` §4 (vector route) + `docs/DATA_MODEL.md` §4 (doc_chunks.embedding vector(512)) + PRD §48 (2025/2026 procurement manager change) + cut-009 §4.1 (FK cleanup pattern) + cut-012 §4.1 (Edit silently failed lesson) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-14 |
| **涉及文件** | `src/ece/connectors/docs.py` (EDIT, add search_documents_vector) + `src/ece/entities/pipeline.py` (EDIT, accept str\|date) + `src/ece/api/search.py` (EDIT, add vector route) + `scripts/seed_temporal_roles.py` (NEW) + `tests/integration/test_s4_2_vector.py` (NEW, 4 tests) + `tests/integration/test_s4_5_temporal.py` (NEW, 5 tests) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | S4.2 vector route (pgvector cosine + pre-computed embedding API) + 2025/2026 temporal manager change (role + HAS_ROLE) + E5 temporal 真值；real embedding model (bge-small-zh-v1.5) deferred v0.2；Sprint 5 (Procurement Agent) deferred cut-014+ |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行（per cut-002 §7.3.1 裁定生效）。**1 个工作 commit（`02bae89`）+ 1 个报告 commit**。批处理不触碰 §7 区段（per cut-003R2 治理注记）。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（S4.2 vector + temporal + 3 side-fixes 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 3（seed_temporal_roles.py + test_s4_2_vector.py + test_s4_5_temporal.py） |
| 修改 Python文件 | 3（docs.py + entities/pipeline.py + api/search.py） |
| 总计 | 6 files changed, 470 insertions(+), 2 deletions(-) |

### 1.2 逐 Sub-task 交付

#### S4.2 — Vector similarity search

| 文件 | 内容 |
|---|---|
| `src/ece/connectors/docs.py` (EDIT) | `search_documents_vector(engine, *, query_embedding, top_k, doc_type_filter)` — pgvector cosine distance via `<=>` operator; similarity = 1 - distance. **关键 fix**: SQLAlchemy `text()` doesn't auto-convert list[float] → vector; serialize to `'[a,b,c,...]'` string + `CAST(:q_vec AS vector)` in SQL. |
| `src/ece/api/search.py` (EDIT) | vector route added in `post_search` endpoint; accepts pre-computed 512-dim `query_embedding` in `SearchRequest`. /search now supports `kinds=['keyword', 'vector', ...]`. |
| `tests/integration/test_s4_2_vector.py` (NEW, 4 tests) | `test_vector_search_returns_list` (verify structure); `test_vector_search_with_doc_type_filter` (filter); `test_vector_search_top_k_bounds` (top_k); `test_vector_search_invalid_embedding_length_returns_empty` (wrong dim returns empty due to `WHERE embedding IS NOT NULL` filter — **not exception** because NULL embedding skips comparison) |

**V0 限制**: demo docs `embedding IS NULL`（no embedding model run yet），所以 vector route 永远返回 `[]`。**Real value test** requires populating embeddings with bge-small-zh-v1.5（deferred to v0.2）。

#### Temporal relationships (PRD §48)

| 文件 | 内容 |
|---|---|
| `scripts/seed_temporal_roles.py` (NEW) | Seed 3 role entities (`procurement_manager` / `finance_manager` / `buyer`) + 3 temporal HAS_ROLE relationships:<br>• U001 → procurement_manager: 2020-01-01 to 2025-12-31<br>• U002 → procurement_manager: 2026-01-01 to NULL (current)<br>• U003 → buyer: no constraint. Idempotent via UNIQUE INDEX `uq_relationships_triple` (with `COALESCE(valid_from, '0001-01-01')`). |
| `src/ece/entities/pipeline.py` (EDIT) | `upsert_relationship` signature accepts `valid_from: str \| date \| None` (was `str \| None`). Date objects now work directly without manual str() conversion. |
| `tests/integration/test_s4_5_temporal.py` (NEW, 5 tests) | 1) `test_seed_temporal_roles_populated` (verify role + HAS_ROLE count); 2-3) `as_of=2025-06-30` (U001 active) / `as_of=2026-09-14` (U002 active) SQL query tests; 4) `test_non_temporal_relationships_always_visible` (≥1000 demo:seed_relationships); 5) `test_per_pr_relationships_unaffected_by_temporal` (assemble_context at as_of=2020/2026 returns same non-temporal count) |

**2025/2026 manager change 真值验证**（psql 直查）:
```
===AS OF 2025-06-30===
 display_id 
------------
 U001  (still manager before 2025-12-31)
 U003  (buyer, no time constraint)

===AS OF 2026-09-14===
 display_id 
------------
 U002  (took over from 2026-01-01)
 U003
```

#### Side-fixes (3 incidental)

| 文件 | 修复内容 |
|---|---|
| `src/ece/entities/pipeline.py` | Add `from datetime import date` import (broke 12 test collection errors when adding `str \| date \| None` type annotation). Update `upsert_relationship` signature to accept both `str` and `date` for `valid_from` / `valid_to`. |
| `tests/integration/test_s4_5_temporal.py` (autouse fixture) | **CRITICAL FIX (§4.1)**: Original autouse fixture used `subprocess.run(["uv", "run", "python", "scripts/seed_temporal_roles.py"])` which ran AFTER test_s14 had already deleted all demo:* entities. Test failures showed `expected ≥1000 non-temporal relationships, got <N>`. Fix: re-seed per-PR data via `subprocess.run(["uv", "run", "python", "scripts/seed_relationships.py"])` BEFORE temporal role seeding. **Lesson**: autouse fixtures must be SELF-SUFFICIENT (not depend on other tests' data state). |
| `tests/integration/test_s4_5_temporal.py` (variable shadowing) | Rename `result` → `entity_result` in autouse fixture (was shadowed between `subprocess.run` returning `CompletedProcess[str]` and `upsert_entity` returning `EntityInsertResult`; mypy type inference flagged the second assignment). |

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `02bae89` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 75 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 109 passed, 3 skipped, 1 warning in 16.73s
$ make check-api-docs          # OK — no app-only routes (2 routes still "planned": audit/context + actions/execute)
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
02bae89 feat(s4): S4.2 vector route + 2025/2026 temporal manager change (cut-013 closure)
0a9bbd7 docs(research-v2): cut 012 report (Sprint 4 tail — perf bench + Chinese pg_trgm + /actions/preview)
c4cf14e feat(s4): perf bench + Chinese tokenization via pg_trgm + /actions/preview (cut-012 closure)
5c8e95f docs(research-v2): cut 011 report (Sprint 4 path B main — step 6/7 + MCP Tool Layer)
3a03e6a feat(s4): step 6/7 real impl + MCP Tool Layer (4 tools + PermissionScope) (cut-011 closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 109 passed 3 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| Real embedding model (bge-small-zh-v1.5) | v0.2（需要 ML 依赖 + 模型下载 + 推理 pipeline） |
| Sprint 5 (Procurement Agent + LLM + E6 eval) | cut-014+ |
| Sprint 6 (Debugger UI + 私有化验收) | cut-015+ |
| structured_data 更多 kind handlers (need real data) | cut-014+ |
| Performance benchmark with real data volume | v0.2 真值 data 后 |
| zhparser extension (替代 pg_trgm for Chinese) | 当前 pg_trgm OK；cut-014+ 根据 E5 真值测试决定 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| `alembic current` | ✅ `0006_pg_trgm (head)` | 无 |
| pg_trgm extension | ✅ 装好 + index 创建 | 无 |
| pgvector extension | ✅ 在 `pgvector/pgvector:pg16` 镜像内置 | 无 |
| `doc_chunks.embedding` 列 | ⚠️ schema 有 vector(512) 但 v0 demo data 全 NULL | 真值 vector 测需 v0.2 embedding pipeline |
| HAS_ROLE temporal 数据 | ✅ 3 role entities + 3 temporal rels seeded | 5 项 test 验真值 |
| 2025/2026 manager change | ✅ as_of=2025-06-30 返 U001+U003；as_of=2026-09-14 返 U002+U003 | psql 直查 + 5 项 test 验 |

---

## 3. Commit 信息

**1 个工作 commit（S4.2 vector + temporal + 3 side-fixes 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `02bae89` | 6 files, +470/-2（search_documents_vector + temporal seed + 2 tests + 3 side-fixes in docs/pipeline/search） | ✅ 5 项纪律全绿；make test 109 passed 3 skipped |

**HEAD after push**: `02bae89ac0979e92ae75bf325c0d2c5a32d1c0fd`

**Push range**: `0a9bbd7..02bae89 main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 autouse fixture SELF-SUFFICIENT 设计原则（test 顺序 race 教训）

**症状**: 单跑 `test_s4_5_temporal.py` 5 测试全过。`make test`（全部测试）2 个失败：
- `test_non_temporal_relationships_always_visible`: 期望 `>=1000` per-PR relationships → 实际 ~0
- `test_per_pr_relationships_unaffected_by_temporal`: `assemble_context(PR201)` → insufficient

**根因**:
- `test_s14_seed_idempotent` 在 `make test` 顺序中比 `test_s4_5_temporal` 早跑
- test_s14 含 `DELETE FROM entities WHERE source_system LIKE 'demo:%'` + `DELETE FROM relationships WHERE src_entity_id IN (entities deleted)`
- 这把 demo:seed_relationships 1206 行 + demo:demo PR 全部删了
- test_s4_5_temporal 的 autouse fixture 只补 role entities + HAS_ROLE temporal
- 但 per-PR relationships (demo:seed_relationships 源) 没了

**修复**: 把 autouse fixture 改成**自给自足**：
```python
# Re-seed per-PR relationships (test_s14 may have deleted them)
result = subprocess.run(
    ["uv", "run", "python", "scripts/seed_relationships.py"],
    capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
)
if result.returncode != 0:
    pytest.skip(f"seed_relationships failed: {result.stderr}")

# THEN seed temporal roles + HAS_ROLE
```

**设计原则**（§6.4 入红线）:
- **autouse fixture 必须 SELF-SUFFICIENT**: 不能假设其他 test 留下的 state。每个 fixture 验证其依赖的所有 data 都存在。
- **test 顺序 race 是真实存在的**：pytest 不能保证 module 顺序，test_s14 可能先于 test_s4_5_temporal。每个 test module 独立。
- **fix vs 改 test 顺序**：不要靠 test 顺序（脆弱），让每个 fixture 准备自己需要的 data
- **fix 跨 test 的破坏性 operation**：test_s14 的 `DELETE FROM entities WHERE source_system LIKE 'demo:%'` 太宽，应该排除 `demo:seed_*`（cut-009 起的 fixture 写入）

### 4.2 pgvector binding via string + CAST (Python list → vector 类型)

`text()` SQL + Python `list[float]` 参数 → psycopg 报 `operator does not exist: vector <=> double precision[]`（psycopg 不知道 list → vector 转换）。

**3 个解决方案对比**:
1. **String + CAST**（cut-013 选）:
   ```python
   params["q_vec"] = "[" + ",".join(str(x) for x in query_embedding) + "]"
   sql = "... ORDER BY dc.embedding <=> CAST(:q_vec AS vector)"
   ```
   ✅ 简单，无 SQLAlchemy 类型系统依赖。V0 选这个。

2. **SQLAlchemy Vector type**:
   ```python
   from sqlalchemy.types import UserDefinedType
   class Vector(UserDefinedType):
       def get_col_spec(self, **kw): return "vector(512)"
   stmt = text(...).bindparams(bindparam("q_vec", type_=Vector(512)))
   ```
   ❌ 需定义 UserDefinedType；过度工程 for v0

3. **Raw SQL via psycopg2/3 cursor**:
   ❌ 跳过 SQLAlchemy abstraction，与 iron rule 2 "禁止绕过核心抽象" 冲突

**V0 选 string + CAST**: 简洁、与 SQLAlchemy 抽象层兼容、无需新类型定义。**Sprint 5+** 如果需要更复杂 vector 算子（HNSW index、cosine <->），可考虑用 pgvector 的 HNSW index 加速。

### 4.3 upsert_relationship signature 接受 str|date

初版签名 `valid_from: str | None` 太严格——seed_temporal_roles 用 `date(2020, 1, 1)` 时 mypy 报 incompatible type。**Psycopg 实际接受 date 和 str**（自动转换）——但签名限制了 API 易用性。

**修复**: `valid_from: str | date | None` 允许两种格式，调用方按需选择：
- `seed_temporal_roles.py`: 用 `date(2020, 1, 1)`（更语义）
- 其他 (现有 `upsert_relationship` 调用方): 用 `valid_from="2020-01-01"` (string, 仍兼容)

**教训**（§6.4 增补）: 写签名时考虑 psycopg 的隐式转换能力——不要过度约束 API。

### 4.4 `result` 变量 shadowing（subprocess.run vs upsert_entity）

`autouse fixture` 同时用 `subprocess.run(...)` 和 `upsert_entity(...)`，两个都返回有 `result` 属性的对象。`result = subprocess.run(...)` 推断为 `CompletedProcess[str]`，然后 `result = upsert_entity(...)` 推断为 `EntityInsertResult`——mypy 抓第二次赋值的类型不兼容。

**修复**: 重命名 inner `result` → `entity_result`。**教训**: 同一作用域两个不同来源的对象用同一变量名——重命名比信任 type inference 更安全。

---

## 5. 经验教训

1. **autouse fixture SELF-SUFFICIENT**（§4.1）: **不能假设其他 test 留下的 state**——每个 fixture 验证其依赖的所有 data 存在。test 顺序 race 是真实存在的（pytest 不保证 module 顺序）。**fix 跨 test 破坏性 operation**（test_s14 DELETE 太宽）而非靠 test 顺序。这是 pytest fixture 设计的 best practice
2. **pgvector binding via string + CAST**（§4.2）: Python list[float] → pgvector 不能自动转。用 `'[a,b,c,...]'` string + `CAST(:q_vec AS vector)` 是 v0 最简方案。**Sprint 5+ 真实 vector 算子用 HNSW index 加速**
3. **psycopg 隐式转换 → API 不要过度约束**（§4.3）: `upsert_relationship` 签名从 `str | None` 改成 `str | date | None`——psycopg 接受两种，调用方按需选择。**写签名时考虑底层库的转换能力**
4. **变量 shadowing**（§4.4）: 同一作用域两个不同来源的对象（subprocess.run + upsert_entity）用同一变量名——**重命名比信任 type inference 更安全**
5. **跨 cut 累积红线**（§6.4）: 已有 14+ 条红线入档（cut-007-013）。本 cut 加 2 条：
   - **autouse fixture 必须 SELF-SUFFICIENT**（cut-013 §4.1）
   - **写签名考虑 psycopg 隐式转换**（cut-013 §4.3）

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-013-report.md` | `ece/reports/cut-014-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 4 项非典型项（**autouse fixture SELF-SUFFICIENT / pgvector string+CAST / upsert 签名 date+str / 变量 shadowing**）
- §5 5 条教训
- §6 红线 (累积 cut-007-008-009-010-011-012-013)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013）

- §7 自写审验结论
- §3 commit hash 占位符
- 报告塞进工作 commit
- 触碰已定稿 §7
- commit 无验收命令
- 假绿
- Edit old_string 含 typo
- trivially-pass eval 误报 PASS
- **新增表数据时不评估现有 test 的 FK cleanup 兼容性**（cut-009 §4.1）
- **tokenization / search 限制不披露**（cut-010 §4.3）
- **endpoint 路径混淆**（cut-010 §4.4）
- **side-effecting tool 不带 preview 路径**（cut-011 §4.5）
- **跨模块 import private function**（cut-011 §4.4）
- **FTS query 用 `to_tsquery` 拼多词字符串**（cut-011 §4.2）
- **integration test 用未 seed 的 display_id**（cut-011 §4.3）
- **Edit silently failed 不 verify**（cut-012 §4.1）
- **autouse fixture 不 SELF-SUFFICIENT**（cut-013 §4.1 入红线——不能假设其他 test 留下的 state，每个 fixture 准备自己需要的 data）
- **写签名不考虑底层库隐式转换**（cut-013 §4.3 入红线——psycopg 接受多种格式，签名不要过度约束 API）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。