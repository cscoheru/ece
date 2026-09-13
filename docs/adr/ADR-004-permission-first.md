# ADR-004: 权限判定先于上下文组装（Permission Before Context Assembly）

- 状态：Accepted（2026-09-04）

## 决策

1. 授权判定唯一发生在 Permission Engine（数据访问层），以 `PermissionScope` 注入所有 Store 读方法，SQL 子查询过滤——**不是取回后丢弃，更不是 prompt 约束**。
2. 判定顺序：deny > user > role > department > classification 默认 > 默认 deny；文档另受 classification 矩阵（DATA_MODEL §3）。
3. Assembly 十二步的第 3 步算出 scope 后全程复用；任何环节不得旁路。
4. 被拒对象在 Package 中仅出现于 `denied[]`（ref + 原因，无内容）。
5. `/actions/execute` 双保险关闭（env + 路由硬编码 403）。

## 理由

PRD P2：LLM 不负责决定用户是否有权访问数据。这是产品最重要的安全边界与最锋利的演示点（"换用户重问"Demo，PRD §48）。E2 套件 Unauthorized Context Exposure = 0 是 CI 一票否决门槛。

## 后果

- 正：安全性质可测试、可审计（context_items 记录每次判定）；间接泄露面收敛为 Agent 输出层（由 E2 专项覆盖）。
- 负：每条查询都携带 scope 子查询，复杂度与少量性能成本——用索引与 PermissionScope 预编译对冲。

## 备选方案

- 取回后过滤（应用层 post-filter）：泄露面扩大到日志/缓存/中间结构，否决。
- LLM prompt 约束：不可验证、可被注入绕过，否决（PRD 明确禁止）。
