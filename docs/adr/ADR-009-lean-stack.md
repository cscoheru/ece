# ADR-009: v0 技术栈瘦身——缓交 OpenSearch 与 Redis

- 状态：Accepted（2026-09-04，修订 PRD §24 建议）

## 决策

PRD §24 建议栈中的 OpenSearch 与 Redis 在 v0 **不引入**：

- 检索：Postgres FTS（generated tsv + 应用层 bigram）+ pgvector 承担（ADR-002）；
- 缓存：进程内 LRU（PermissionScope 编译结果、identity 解析）承担；
- 队列：不需要（ingestion 同步执行）。

## 理由

solo 开发 + 私有化交付约束下，每多一个服务 = 部署复杂度、资源占用（OpenSearch JVM 默认 1G+ 内存）、升级面各翻一倍，而 v0 数据规模（500 文档/数万 chunk）远未触及 Postgres 检索能力边界。PRD §44 Rule 4（禁止提前引入复杂基础设施）适用。

## 升级触发条件（任一满足则重开决策）

1. FTS 中文召回成为 E3 检索子集瓶颈且 zhparser+bigram 无法解决；
2. chunk > 5×10^5 或向量检索 p95 > 300ms；
3. 出现多进程/多副本部署需求（缓存需共享）。

## 后果

- 正：`docker compose up` 两容器即全栈；客户机器最低 4GB 内存可跑。
- 负：中文关键词召回弱于专用引擎——v0 以向量主导 + bigram 兜底；差距在 E3 中量化监控。
