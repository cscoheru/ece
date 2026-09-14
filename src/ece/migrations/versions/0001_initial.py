"""S0.5 initial migration — covers docs/DATA_MODEL.md §1-§5.

Per PRD §27 + DATA_MODEL § 末段:
- 必须含 pgvector extension (vector 列需要)
- 全部 entity/relationship/docs/chunks/ingestion_runs/context_* 表 + 索引
- §6 是文本图、§7/§8 是策略 → 不纳入迁移

DATA_MODEL § 编号映射 (Cline 刀 4R 注: 此前记串,本迁移按数据架构领域重整):
- entities / entity_aliases / entity_revisions → "实体与解析" 章节 (DataModel.md §1)
- relationships                  → "关系 (Temporal)" 章节 (§2)
- documents / doc_chunks        → "文档与分块" 章节 (§3)
- acl_entries                   → "权限" 章节 (§3 末段 — 文档分类默认矩阵相关)
- ingestion_runs                → "审计与溯源" 章节 (§5 末段)
- context_requests / context_items → "Context Package" 章节 (§5)

按迁移顺序书写,无 § 编号标注 — 业务领域 → 表分组。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. pgvector extension (vector 列需要)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. entities (§1)
    op.execute("""
        CREATE TABLE entities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            display_id text UNIQUE,
            entity_type text NOT NULL,
            name text NOT NULL,
            normalized_name text NOT NULL,
            source_system text NOT NULL,
            source_id text NOT NULL,
            attributes jsonb NOT NULL DEFAULT '{}',
            status text NOT NULL DEFAULT 'active',
            merged_into uuid REFERENCES entities(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (entity_type, source_system, source_id)
        )
    """)
    op.execute("CREATE INDEX idx_entities_type_name ON entities (entity_type, normalized_name)")
    op.execute("CREATE INDEX idx_entities_attrs ON entities USING gin (attributes jsonb_path_ops)")

    # 3. entity_aliases (§1)
    op.execute("""
        CREATE TABLE entity_aliases (
            id bigserial PRIMARY KEY,
            entity_id uuid NOT NULL REFERENCES entities(id),
            alias text NOT NULL,
            norm_alias text NOT NULL,
            source_system text,
            source_ref text,
            method text NOT NULL,
            confidence numeric(4, 3) NOT NULL DEFAULT 1.0,
            status text NOT NULL DEFAULT 'confirmed',
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_aliases_norm ON entity_aliases (norm_alias)")

    # 4. entity_revisions (§1 — temporal)
    op.execute("""
        CREATE TABLE entity_revisions (
            id bigserial PRIMARY KEY,
            entity_id uuid NOT NULL REFERENCES entities(id),
            attributes jsonb NOT NULL,
            valid_from timestamptz NOT NULL,
            source_system text NOT NULL,
            reason text
        )
    """)

    # 5. relationships (§2 — temporal)
    op.execute("""
        CREATE TABLE relationships (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            src_entity_id uuid NOT NULL REFERENCES entities(id),
            relation text NOT NULL,
            dst_entity_id uuid NOT NULL REFERENCES entities(id),
            valid_from date,
            valid_to date,
            source_system text NOT NULL,
            source_ref text,
            confidence numeric(4, 3) NOT NULL DEFAULT 1.0,
            attributes jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from)
        )
    """)
    op.execute("CREATE INDEX idx_rel_src ON relationships (src_entity_id, relation)")
    op.execute("CREATE INDEX idx_rel_dst ON relationships (dst_entity_id, relation)")

    # 6. documents (§3 — text + chunks via vector)
    op.execute("""
        CREATE TABLE documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            display_id text UNIQUE,
            title text NOT NULL,
            doc_type text NOT NULL,
            source_system text NOT NULL,
            file_path text NOT NULL,
            classification text NOT NULL DEFAULT 'department',
            content_sha256 text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE doc_chunks (
            id bigserial PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index int NOT NULL,
            text text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
            embedding vector(512),
            token_count int,
            UNIQUE (document_id, chunk_index)
        )
    """)
    op.execute("CREATE INDEX idx_chunks_tsv ON doc_chunks USING gin (tsv)")
    op.execute("CREATE INDEX idx_chunks_vec ON doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    # 7. ingestion_runs (§3)
    op.execute("""
        CREATE TABLE ingestion_runs (
            id bigserial PRIMARY KEY,
            connector text NOT NULL,
            status text NOT NULL,
            stats jsonb,
            started_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )
    """)

    # 8. context tables (§4 / §5 — Context API + Audit/Debugger)
    op.execute("""
        CREATE TABLE context_requests (
            request_id uuid PRIMARY KEY,
            user_ref text NOT NULL,
            intent text NOT NULL,
            spec_version int,
            root_entities jsonb NOT NULL,
            as_of date,
            counts jsonb NOT NULL,
            latency_ms int,
            llm_model text,
            status text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE context_items (
            id bigserial PRIMARY KEY,
            request_id uuid NOT NULL REFERENCES context_requests(request_id) ON DELETE CASCADE,
            seq int NOT NULL,
            item_kind text NOT NULL,
            ref text NOT NULL,
            source jsonb NOT NULL,
            decision text NOT NULL,
            reason text,
            score numeric(8, 4)
        )
    """)
    op.execute("CREATE INDEX idx_citems_req ON context_items (request_id)")

    # 9. acl_entries (§5 — Permission)
    op.execute("""
        CREATE TABLE acl_entries (
            id bigserial PRIMARY KEY,
            subject_type text NOT NULL,
            subject_ref text NOT NULL,
            object_type text NOT NULL,
            object_ref text NOT NULL,
            effect text NOT NULL,
            valid_from date,
            valid_to date,
            source_system text NOT NULL,
            note text
        )
    """)
    op.execute("CREATE INDEX idx_acl_object ON acl_entries (object_type, object_ref)")
    op.execute("CREATE INDEX idx_acl_subject ON acl_entries (subject_type, subject_ref)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS acl_entries")
    op.execute("DROP TABLE IF EXISTS context_items")
    op.execute("DROP TABLE IF EXISTS context_requests")
    op.execute("DROP TABLE IF EXISTS ingestion_runs")
    op.execute("DROP TABLE IF EXISTS doc_chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS relationships")
    op.execute("DROP TABLE IF EXISTS entity_revisions")
    op.execute("DROP TABLE IF EXISTS entity_aliases")
    op.execute("DROP TABLE IF EXISTS entities")
    op.execute("DROP EXTENSION IF EXISTS vector")
