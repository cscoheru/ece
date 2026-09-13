# ADR-002: PostgreSQL 作为初始实体/关系存储

- 状态：Accepted（2026-09-04）

## 背景

需要同时承载：结构化业务数据（JSONB 灵活 schema）、关系（多跳查询）、全文检索、向量检索、审计。solo 开发者，运维预算≈0。

## 决策

单一 PostgreSQL 16 实例承担全部：实体/关系/ACL/审计用关系表；业务属性用 JSONB + GIN；文档用 FTS（generated tsv）；向量用 pgvector（ivfflat）。

## 后果

- 正：一个数据库、一套备份、一次 Docker 起动；SQL 递归查询足以覆盖 v0 的 2 跳关系展开；事务保证 ingestion 一致性。
- 负：中文 FTS 弱于专用引擎（用 bigram+向量主导对冲）；ivfflat 召回在 >10^6 chunk 时衰减（v0 数据量 500+ 文档，远未触及）。

## 备选方案

- Postgres + 外部向量库（Milvus/Qdrant）：多一个服务、多一份数据一致性负担，v0 无必要。
- MongoDB：关系查询与事务弱，否决。
