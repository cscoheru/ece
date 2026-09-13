# ADR-010: 领域包隔离与 Context Specification 版本化

- 状态：Accepted（2026-09-04）

## 决策

1. 目录与依赖铁律：一切领域逻辑（context spec、ontology 三元组、领域规则、Agent prompt、评测用例、数据投影）只存在于 `src/domain_packs/<domain>/`；`src/ece/` 引擎核心**零领域 import**（CI 用 import-linter 强制）。
2. `Task → Context Specification`（YAML）是引擎与领域之间的一级契约，带 `version`；spec 变更走 git 评审，评测集与 spec 版本绑定。
3. 领域包注册制：`pyproject` entry-point 或 registry.py 显式注册，引擎启动时加载。

## 理由

红队 v3 的核心未定项：**领域选择（采购 vs 审计/合规）悬而未决，待客户访谈裁决**。该架构把"商业不确定性"隔离进一个目录，使访谈结论可以以"换包"方式落地，而非重写引擎。同时 spec 版本化让评测可回归（E3 与 spec_version 绑定）。

## 验证方式

- Sprint 0 CI 加 import-linter 契约（ece ✗→ domain_packs）。
- Sprint 6 选做换域演练（audit spec 走通 /context）作为 H5（PRD §36）的实证。

## 后果

- 正：换域成本上限明确（新包 1–2 周）；引擎成为可跨领域复利的资产（正是 PRD §42 的壁垒假设）。
- 负：早期多一层抽象（spec loader / registry）约 1 天成本——接受。
