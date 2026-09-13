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
  object_type  text NOT NULL,           -- entity|document
  object_ref   text NOT NULL,           -- display_id / document id
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

