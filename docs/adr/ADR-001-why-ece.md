# ADR-001: 为什么做 Enterprise Context Engine（垂直优先的平台下注）

- 状态：Accepted（2026-09-04）
- 决策人：Founder；评审：Cline（红队）

## 背景

根目录 RED_TEAM_REVIEW v3 结论：可达市场（中国大陆）无 Glean；Glean Partner 路径降级为期权；"做横向中国版 Glean"是死亡陷阱（与 Dify/FastGPT/MaxKB/RAGFlow 及大厂正面竞争）；正确姿势是"工作流优先、上下文随行"。同时 v3 确立主路径 D：私有化部署 + 开源模型 + 垂直领域上下文。

## 决策

1. 自建 ECE 作为**领域无关的窄上下文引擎**：Entity/Relationship/Permission/Temporal/Assembly 五件套 + Context API。
2. v0 只通过 Procurement 领域包验证（ADR-007/010）；横向能力（通用 Connector 平台、多领域、图库）一律延后，触发条件见 ADR-003/009。
3. 部署形态即信任策略：单机 Docker、数据不出域、LLM/OpenAI 兼容可指本地模型（ADR-006）。
4. 商业验证与开发并行：访谈若换领域，引擎不动，换领域包。

## 后果

- 正：与 v3 主路径 D 完全对齐；沉淀 Task→Context Spec、Permission Engine、评测集等可复利资产（PRD §42）；Glean 若未来合作可作 Context Adapter 下游数据面（PRD §39）。
- 负：相比"直接用 Glean"，自担 connector/permission 工程量——用"窄切片 + 合成数据"对冲；相比"纯 RAG 项目"，周期更长——用评测门槛与里程碑（TASKS M1–M3）防失控。

## 备选方案

- 纯 RAG 知识库（Dify/FastGPT 二开）：红海且无权限/关系/时间模型，无法支撑"跨部门企业任务"，否决。
- 等待 Glean Partner 回应再动：已被 v3 降级为非阻塞期权，否决（时间成本不可逆）。
- 只做 Procurement SaaS 不做引擎：丢失可换域资产，访谈结论无法低成本回滚，否决。
