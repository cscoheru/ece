# ADR-003: MVP 不引入 Neo4j / 图数据库

- 状态：Accepted（2026-09-04）

## 决策

关系存 PostgreSQL `relationships` 表，多跳查询用 SQL（v0 spec 最大 max_hops=2）。不部署 Neo4j/Memgraph/JanusGraph。

## 理由

v0 要验证的是 **Context Model 是否成立**（PRD §25），不是图引擎性能。合成数据规模（数百实体/数千关系）下 SQL 毫秒级完成。

## 升级触发条件（任一满足则重开决策）

1. spec 常态化出现 ≥4 跳展开且 SQL p95 > 500ms（加索引/物化后仍超）；
2. 引入图算法需求（路径分析、社区发现、影响传播）；
3. 关系表 > 10^7 行且多跳查询成为主要延迟源。

## 后果

- 正：零额外运维；数据模型与权限/溯源共用一套 SQL 事务。
- 负：若触发升级需写 data-migration（关系表 → 图），预计 1–2 天，可接受。
