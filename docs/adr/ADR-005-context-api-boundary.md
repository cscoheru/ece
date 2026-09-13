# ADR-005: Context API 作为 Agent 边界

- 状态：Accepted（2026-09-04）

## 决策

Agent（领域包）与引擎之间唯一通道是 Context API：输入 = User Question + Context Package，输出 = 结构化结论 + evidence 引用。Agent 不直连数据库、不自行检索、不持有权限逻辑。

## 理由

1. 安全边界单一（与 ADR-004 叠加）：Agent 拿到的永远是"已授权、已溯源、已打包"的上下文。
2. 可替换性：换 LLM、换 Agent 框架、未来接 Glean（PRD §39，Context Adapter 在 API 之下换数据面）都不动引擎。
3. 可评测性：E3（包完整性）与 E6（Agent 输出）解耦，失败可归因（上下文缺 vs 模型弱）。

## 后果

- 正：领域包薄（规则 + prompt + 输出 schema），换域成本低（ADR-010）；trace 端到端闭环。
- 负：Agent 需要而 spec 未声明的信息拿不到——这是特性不是缺陷：spec 即产品化的领域知识，缺失说明 spec 该迭代。
