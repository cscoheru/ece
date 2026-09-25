# DATA_MODEL — Enterprise Context Engine v0

> 上游：`PRD.md` §10–§14/§17/§22/§27/§28/§31。所有 DDL 以 Alembic 迁移为准，本文是契约。

## 0. 总原则

1. **实体统一存储**：全部业务对象（Person/Department/Supplier/Product/Contract/PurchaseRequest/Approval…）都是 `entities` 一行 + `attributes` JSONB（PRD §10）。采购特有的"历史采购/审批流水"也以实体行存储（`purchase_record` / `approval`），获得统一的关系、权限、溯源能力。性能热点用 JSONB GIN 索引与物化视图解决（触发条件写死在迁移注释里）。
2. **关系是一等对象**：`relationships` 带 temporal 与 provenance（PRD §11）。
3. **一切可溯源**：每行保留 `source_system` / `source_ref`；Context Package 中的每项映射到 `context_items`。
4. **display_id 约定**（人读 ID，非主键）：`U*` 人员、`D*` 部门、`R*` 角色、`SUP*` 供应商、`PRD*` 品目、`CON*` 合同、`PR*` 采购申请、`PO*` 采购单、`APR*` 审批、`REC*` 历史采购记录、`POL-*` 政策文档。

## 1. 实体与解析

```sql
CREATE TABLE entities (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_id      text UNIQUE,                      -- 'SUP001'；可空（合成数据必填）
  entity_type     text NOT NULL,                    -- person|department|role|supplier|product|contract|purchase_request|purchase_order|approval|purchase_record|...
  name            text NOT NULL,
  normalized_name text NOT NULL,                    -- 归一化（去空白/全半角/后缀剥离）用于精确匹配
  source_system   text NOT NULL,                    -- erp|oa|contract|finance|csv:...
  source_id       text NOT NULL,
  attributes      jsonb NOT NULL DEFAULT '{}',      -- 业务字段（金额、数量、部门号、角色列表…）
  status          text NOT NULL DEFAULT 'active',   -- active|merged
  merged_into     uuid REFERENCES entities(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, source_system, source_id)
);
CREATE INDEX idx_entities_type_name ON entities (entity_type, normalized_name);
CREATE INDEX idx_entities_attrs ON entities USING gin (attributes jsonb_path_ops);

CREATE TABLE entity_revisions (        -- 属性历史（Temporal §7）
  id          bigserial PRIMARY KEY,
  entity_id   uuid NOT NULL REFERENCES entities(id),
  attributes  jsonb NOT NULL,
  valid_from  timestamptz NOT NULL,
  source_system text NOT NULL,
  reason      text
);

CREATE TABLE entity_aliases (          -- Entity Resolution 落点（ARCHITECTURE §6）
  id            bigserial PRIMARY KEY,
  entity_id     uuid NOT NULL REFERENCES entities(id),
  alias         text NOT NULL,
  norm_alias    text NOT NULL,
  source_system text,
  source_ref    text,
  method        text NOT NULL,          -- exact|normalized|alias|rule|embedding|llm|manual
  confidence    numeric(4,3) NOT NULL DEFAULT 1.0,
  status        text NOT NULL DEFAULT 'confirmed',  -- confirmed|pending（<0.9 或 llm 需人工）
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_aliases_norm ON entity_aliases (norm_alias);
```

**硬规则**：`method='llm'` 产生的 alias 一律 `status='pending'`；只有 `confirmed` 参与 Assembly。

## 2. 关系（Temporal）

```sql
CREATE TABLE relationships (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  src_entity_id uuid NOT NULL REFERENCES entities(id),
  relation      text NOT NULL,          -- MEMBER_OF|HAS_ROLE|BELONGS_TO|SUBMITTED_BY|SELECTS|CONTAINS|HAS_CONTRACT|REFERENCES|SUBJECT_TO|HAS_APPROVAL|...
  dst_entity_id uuid NOT NULL REFERENCES entities(id),
  valid_from    date,                   -- NULL = -∞；区间 [from, to)
  valid_to      date,                   -- NULL = +∞
  source_system text NOT NULL,
  source_ref    text,
  confidence    numeric(4,3) NOT NULL DEFAULT 1.0,
  attributes    jsonb NOT NULL DEFAULT '{}',
  created_at    timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
);
CREATE INDEX idx_rel_src ON relationships (src_entity_id, relation);
CREATE INDEX idx_rel_dst ON relationships (dst_entity_id, relation);
-- temporal 查询：应用层组装谓词 (valid_from IS NULL OR valid_from <= :d)
--                              AND (valid_to IS NULL OR valid_to > :d)
```

允许的关系三元组由领域包的 `ontology.yaml` 声明（如 `purchase_request SELECTS supplier`）；入库时校验，未声明组合 → 拒绝并记 ingestion 错误。

## 3. 权限（PRD §13/§28）

```sql
CREATE TABLE acl_entries (
  id           bigserial PRIMARY KEY,
  subject_type text NOT NULL,           -- user|role|department
  subject_ref  text NOT NULL,           -- display_id：'U001' / 'R:procurement_manager' / 'D03'
  object_type  text NOT NULL,           -- entity|document|engine_document
  object_ref   text NOT NULL,           -- display_id / document id / 'engine_document:<id>'
  effect       text NOT NULL,           -- allow|deny
  valid_from   date, valid_to   date,
  source_system text NOT NULL,
  note         text
);
CREATE INDEX idx_acl_object ON acl_entries (object_type, object_ref);
CREATE INDEX idx_acl_subject ON acl_entries (subject_type, subject_ref);
```

- 判定顺序（ARCHITECTURE §5）：deny > user > role > department > 文档 classification 默认 > deny。
- 文档 classification 默认矩阵（seed 固化，可被 acl_entries 覆盖）：
  `public→全员；department→本部门+上级部门+management；finance→finance+management；procurement→procurement+management；management/confidential→management + 显式 allow`。

### 3.1 时间盒生效（OEI-009）

`valid_from` / `valid_to` 列自 `0001_initial.py` 起就存在；OEI-009
把它们真正接入 `check_permission` 判定（deny + allow 两侧）：

```
valid_from IS NULL  → -∞
valid_to   IS NULL  → +∞
effective iff valid_from <= now < valid_to      -- 半开区间（左侧含、右侧不含）

判定时点由 check_permission(..., now=<date>) 形参控制；
  now=None 时取 UTC today（生产路径，行为对既有数据集不变）。
```

`subject_type='org'`（OEI-010 候选）：`_subject_matches` 加一行
`if st == "org" and sr == identity.org_id: return True`。OEI-009
最小落位只把 `Identity.org_id` / `PermissionScope.org_id` 字段加上，
**不**修改 `_subject_matches`——属于 OEI-010 范围。

## 4. 文档与分块

```sql
CREATE TABLE documents (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_id     text UNIQUE,           -- 'POL-2026-03' / 'DOC-0007'
  title          text NOT NULL,
  doc_type       text NOT NULL,         -- procurement_policy|contract|quote|report|approval_doc|other
  source_system  text NOT NULL,
  file_path      text NOT NULL,         -- data/demo 下相对路径
  classification text NOT NULL DEFAULT 'department',
  content_sha256 text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE doc_chunks (
  id          bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index int  NOT NULL,
  text        text NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
  embedding   vector(512),              -- 默认 bge-small-zh-v1.5(512d)；换模型=新列+回填（迁移模板见 alembic）
  token_count int,
  UNIQUE (document_id, chunk_index)
);
CREATE INDEX idx_chunks_tsv ON doc_chunks USING gin (tsv);
CREATE INDEX idx_chunks_vec ON doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- 中文检索：`simple` 分词 + 应用层 bigram 兜底 + 向量主导；`zhparser` 为可选增强（ADR-009 附录）。
- Embedding 提供方：`ECE_EMBED_PROVIDER=local|api`（local=sentence-transformers 进程内；api=OpenAI 兼容 `/embeddings`）。**同一部署只用一个模型**，换模型必须回填，禁止混维。

## 4.1 引擎文档登记表（OEI-009）

`engine_documents` 表是 **ECE 对"已送进引擎的文档"的来源与权限记录方**。
注意：与 `documents` 表解耦——`documents` 是 ECE 原生 ingest 路径
（带 `doc_chunks` / FTS / vector，被 `context/assembly.py` 读），而
`engine_documents` 只承担"由 ECE 主导上传并维护权限"的子集。

迁移：`0009_engine_documents.py`。

```sql
CREATE TABLE engine_documents (
    id                  bigserial PRIMARY KEY,
    engine_name         text NOT NULL,           -- 'onyx' (Port.engine_name)
    engine_project_id   int    NOT NULL,
    -- 读侧唯一键：与 /api/search 结果的 `title` 精确匹配。
    -- 新上传 = 'ece-<docref>-<slug>.<ext>'（ECE 服务端派生）；
    -- 回填的旧文档 = 历史 title 原样（不改名、不重传）。
    engine_filename     text NOT NULL,
    -- 给人看的原名（可能与 engine_filename 不同；新上传一定有别）。
    original_filename   text NOT NULL,
    -- 写侧溯源 = Onyx user_file.id (UUID)。**仅写侧用，绝不参与读侧 lookup**。
    -- 注释在 src/ece/consulting/registry.py 写明，禁止后人重新推出错误契约。
    engine_document_id  text,
    title               text,
    content_sha256      text,
    classification      text NOT NULL DEFAULT 'public',
                                              -- public/internal/department/restricted/management
                                              -- /confidential/finance/procurement
    uploaded_by         text NOT NULL,         -- user_ref；anonymous 上传被路由层拒
    department          text NOT NULL DEFAULT '',
    org_id              text,                  -- OEI-010 hook；当前不参与 SELECT-side 谓词
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (engine_name, engine_filename)
);
CREATE INDEX idx_engine_docs_project  ON engine_documents (engine_project_id);
CREATE INDEX idx_engine_docs_uploader ON engine_documents (uploaded_by);
CREATE INDEX idx_engine_docs_lookup   ON engine_documents (engine_name, engine_filename);
```

**读侧 lookup 契约**（写进代码注释，`src/ece/consulting/registry.py`）：

```python
# Lookup key = (engine_name, engine_filename), NOT engine_document_id.
# engine_document_id is the Onyx user_file.id (UUID), returned by upload.
# It is NEVER returned by /api/search, so it CANNOT be the read-side key.
# Source of this rule: OEI-009 VERDICT.md §3 (exclusion of citation_id,
# document_id, link, content_sha256 on Onyx CE v4.7.8).
```

**回填语义**（步骤 1.4）：历史 3 份演示文档以它们**当前**的 title 直接
建行（不改名、不重传）。`engine_filename` = `original_filename` = 原
title。`classification` 默认 `public`（保留"匿名也能看到"的演示行为）。

**幂等性**：`register()` 用 `ON CONFLICT (engine_name, engine_filename)
DO UPDATE SET engine_document_id = EXCLUDED.engine_document_id`——
第二次跑同输入，行数不变。

## 4.2 记忆表（OEI-010）

`memories` 表是**持久上下文记忆**：跨请求、跨会话留存的"关于某个主体的事实"。
与 `documents` / `engine_documents` 的区别是**主体不同**——那两张表描述"文
档"，这张表描述"**人**（`scope='user'`）或**组织**（`scope='org'`）"。

迁移：`0010_memories.py`（`down_revision = '0009_engine_documents'`）。

```sql
CREATE TABLE memories (
    id             bigserial PRIMARY KEY,
    -- 作用域。两值封闭集，DB 层 CHECK 兜底，不靠应用自觉。
    scope          text NOT NULL,              -- 'user' | 'org'
    -- 归属。scope='user' → user_ref；scope='org' → org_id。
    -- 即"这条记忆属于谁"，与"谁能读"是两件事（见下）。
    owner_ref      text NOT NULL,
    statement      text NOT NULL,              -- 记忆正文（自然语言陈述）
    -- 分级。本刀全部为 'restricted' → 默认拒绝：**没有 ACL 行 = 谁都读不到**。
    classification text NOT NULL DEFAULT 'restricted',
    source         text NOT NULL,              -- 'explicit:api' 等
    source_ref     text,                       -- 外部引用（可空）
    confidence     numeric(3,2),               -- 0..1，CHECK 兜底
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz,                -- 半开区间：expires_at <= now 即失效
    deleted_at     timestamptz,                -- 软删；NULL = 未删
    CONSTRAINT ck_memories_scope
        CHECK (scope IN ('user', 'org')),
    CONSTRAINT ck_memories_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    -- 去重键：同一主体对同一句话只存一行。POST 用它做 ON CONFLICT DO NOTHING，
    -- 因此重复创建是幂等的（返回原行，created=false，不动 updated_at）。
    CONSTRAINT uq_memories_scope_owner_ref_statement
        UNIQUE (scope, owner_ref, statement)
);
-- 列序与迁移 0010_memories 一致：(scope, owner_ref)。此前这里误写成
-- (owner_ref, scope)（OEI-010 的文档笔误，OEI-011 步骤 0 订正）。
CREATE INDEX idx_memories_scope_owner ON memories (scope, owner_ref);
CREATE INDEX idx_memories_deleted_at  ON memories (deleted_at);
CREATE INDEX idx_memories_expires_at  ON memories (expires_at);
```

### 可见性规则（读侧）

读发生在**权限判定之后**，且**逐条**判定：候选行先按 `scope` + 活跃度收窄，
再对**每一行**调用 `check_permission`（对象类型 `memory`，对象引用
`memory:<id>`，`classification` 取该行自身的值）。

| `scope` | `owner_ref` | 可见者 |
| --- | --- | --- |
| `user` | `user_ref` | 仅该 `user_ref` 本人（同 org 的他人也看不到） |
| `org` | `org_id` | 该 org 的成员——实际上由 ACL 行决定，见下 |

**ACL 不是可有可无的补充，而是唯一的读入口。** `classification='restricted'`
意味着默认拒绝：一条记忆若没有任何 `subject_type`/`subject_ref` 命中的 allow
行，**连它自己的 `owner_ref` 都读不到**。所以"写入"必须同时落一行 allow，
否则写进去的就是一条谁都看不见的记忆（`POST /api/v1/memory` 在同一事务里做
这两件事）。

### 写权限对象 `memory_scope`（写侧）

写权限不挂在 `memories` 行上，而挂在一个**作用域对象**上：

| 字段 | 值 |
| --- | --- |
| `object_type` | `memory_scope` |
| `object_ref` | `user:<user_ref>` 或 `org:<org_id>` |
| `classification` | `restricted`（→ 默认拒绝） |

于是**「谁能给谁写记忆」是数据，不是代码**：候选 A（本刀采用）只往
`acl_entries` 里插了两类行——`('user', <自己>, 'memory_scope', 'user:<自己>')`
和 `('role', 'org_admin', 'memory_scope', 'org:<org>')`。换政策只需改这几行
数据，`check_permission` 一行不用动（依据见
`onyx-lab/OEI-010/workspace/design-memory-policy.md`）。

**两道门，缺一不可**（这是"主体只来自凭据"的落地）：

1. **主体门**：`body.owner_ref` 必须等于**凭据**解析出的主体。不符 → 403，
   **绝不改写成调用者**。"我是 org_admin 所以能给别的 org 写"在这一门被挡住
   ——`org_admin` 只覆盖**自己那个 org**（`owner_ref == identity.org_id`）。
2. **授权门**：对上面的 `memory_scope` 对象调 `check_permission`。

注意 `owner_ref` 对 org scope 存的是 org id 本身，而 ADR-004 的
`PermissionScope.org_id` 来自 `ECE_USER_ORGS` 环境变量、**与
`entities.attributes.org_id` 是两条独立来源**；本刀让 `Identity.org_id` 走
后者（`resolve_identity`），未改动前者（`tests/integration/test_s7_orgs.py`
的断言仍成立）。

## 5. 审计与溯源（PRD §22/§31）

```sql
CREATE TABLE context_requests (
  request_id   uuid PRIMARY KEY,
  user_ref     text NOT NULL,
  intent       text NOT NULL,
  spec_version int,
  root_entities jsonb NOT NULL,
  as_of        date,
  counts       jsonb NOT NULL,          -- {entities:n, relationships:n, chunks:n, rows:n, denied:n}
  latency_ms   int,
  llm_model    text,                    -- agent 阶段回填
  status       text NOT NULL,           -- ok|insufficient_context|error
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE context_items (            -- Package 每一项的 trace（Debugger 数据源）
  id           bigserial PRIMARY KEY,
  request_id   uuid NOT NULL REFERENCES context_requests(request_id) ON DELETE CASCADE,
  seq          int NOT NULL,
  item_kind    text NOT NULL,           -- user|entity|relationship|document_chunk|business_row
  ref          text NOT NULL,           -- 'PR001' / 'POL-2026-03#12'
  source       jsonb NOT NULL,          -- {system, record_id, field|doc, page}
  decision     text NOT NULL,           -- allowed|denied
  reason       text,                    -- 'acl:department_denied' / 'spec:required' / 'rank:distance=1'
  score        numeric(8,4)
);
CREATE INDEX idx_citems_req ON context_items (request_id);

CREATE TABLE ingestion_runs (
  id          bigserial PRIMARY KEY,
  connector   text NOT NULL,            -- csv:suppliers | json:prs | docs:folder
  status      text NOT NULL,            -- running|done|failed
  stats       jsonb,                    -- {created, updated, skipped, errors[]}
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
```

## 6. 实体关系图（文本）

```text
entities 1──* entity_aliases / entity_revisions
entities *──relationships──* entities        （src/dst 自引用）
acl_entries → (entities | documents)         （by display_ref）
documents 1──* doc_chunks
context_requests 1──* context_items
ingestion_runs （独立）
```

## 7. 迁移与种子策略

- Alembic：`make rev "..."` 生成；**已应用的迁移只许追加新迁移，不许修改**。
- 种子顺序（scripts/seed.py，幂等，按 source 增量 upsert）：
  `departments → persons(+roles) → suppliers → products → contracts → purchase_records → purchase_requests → approvals → relationships → acl_entries → documents(→chunks→embeddings)`。
- 合成数据集规模与对抗性用例要求见 PRD §27/§28（同名人员、同供应商多名称、历史组织变更、权限边界、不完整资料必须存在）。
- 删除策略：v0 无硬删除；`entities.status='merged'` + `merged_into` 实现归一合并。

## 8. 数据所有权与主权（部署级约束）

- 全部数据仅存于部署环境内（Postgres 卷 + 本地文件）；无外部回传、无 SaaS 遥测。
- 导出（`scripts/export_audit.py`）仅输出审计与 trace，不含业务原文——用于向客户安全团队证明"AI 看过什么"。

