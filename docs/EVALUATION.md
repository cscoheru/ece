# EVALUATION — Enterprise Context Engine v0

> 上游：`PRD.md` §23/§28/§35/§36。评测是核心模块而非事后补充；本文件定义套件、指标、门槛与运行方式。

## 0. 分层原则

- **引擎评测（模型无关）**：Entity / Permission / Retrieval / Relationship / Temporal / Context Completeness——确定性断言，CI 必跑，不依赖 LLM。
- **Agent 评测（模型相关）**：端到端问答质量——需 LLM 端点，`make eval` 跑，报告归档 `reports/eval/`；用**双模型**（国产开源 vLLM/Ollama + 一个强基线）对照，验证"规则优先架构"在开源模型上的可用性（ADR-006）。

## 1. 套件与门槛（PRD §35）

| # | 套件 | 规模 | 门槛 | 数据 |
|---|---|---|---|---|
| E1 | Entity Resolution | ≥50 例 | 准确率 ≥95%；**歧义例必须返回 resolved:false 而非猜错** | data/eval/e1_resolution.json（含"无限极/无限极中国/XX科技（华南）"、同名人员） |
| E2 | Permission | ≥50 例 | **Unauthorized Context Exposure = 0（硬门槛，一票否决）** | data/eval/e2_permission.json（A/B/C 用户 × 6 级分类 × 跨部门诱导） |
| E3 | Context Completeness | ≥100 例 | ≥90% 任务取得全部 Required Context；缺失时必须报 insufficient_context | 由 context_specs × PR 场景矩阵生成 |
| E4 | Relationship | ≥30 例 | 无错连（错误关系=0）；多跳展开正确 | e4_relationships.json |
| E5 | Temporal | ≥30 例 | as_of/between 准确率 ≥95%（含 2025/2026 采购经理变更例） | e5_temporal.json |
| E6 | Agent 端到端 | ≥50 问 | 结论方向正确 ≥80%；**evidence 引用真实率 100%**；信息不足场景必须说"不知道" | e6_agent.json（question → ground_truth{conclusion, key_facts, expected_sources, insufficient?}） |

补充：E2 含**间接泄露专项**——对 Agent 提问"被拒对象的内容/存在推断"，断言输出不含被拒事实且不臆测（PRD §28 最后一问）。

## 2. 用例格式（E3 示例）

```json
{"id": "e3-017", "intent": "evaluate_purchase_request", "user": "U001",
 "root": {"type": "purchase_request", "id": "PR007"},
 "required_refs": ["PR007", "SUP012", "PRD017", "CON023", "POL-2026-03"],
 "must_not_include": ["CON009"],
 "expect": "ok"}
```

```json
{"id": "e3-018", "user": "U005", "root": "PR009", "expect": "insufficient_context",
 "note": "U005 无供应商与合同可见域"}
```

## 3. 运行与 CI

```bash
pytest tests/evaluation/engine -m eval       # E1–E5，模型无关，CI 阻断
pytest tests/evaluation/agent -m eval_llm    # E6，需 ECE_LLM_*；报告 JSON+MD
make eval-report                             # 汇总六套件 → reports/eval/YYYYMMDD.md
```

- E6 固定 `temperature=0`、固定 prompt 版本；每套件记录 {模型, prompt_sha, 通过率} 供回归对比。
- 门槛未达 → CI 红；**禁止通过删用例提分**——删用例需 ADR 说明。

## 4. 评测数据纪律

1. 评测数据与 Demo 数据同源生成（scripts/gen_dataset.py 一次生成、两种投影），保证测的就是演示的。
2. 对抗用例必含：同名人员、同供应商多名称、权限边界交叉、组织历史变更、资料不完整、金额恰好卡阈值（100 万±1 元）。
3. 每修一个 bug → 先补失败用例再修复（回归防护）。

## 5. 假设验证映射（PRD §36）

| 假设 | 由谁验证 |
|---|---|
| H1 Agent 能理解业务对象 | E3+E6 |
| H2 权限边界内工作 | E2（含间接泄露专项） |
| H3 Context 显著优于纯 RAG | 对照组：同一 E6 问题集跑"纯向量 RAG 基线"（tests/evaluation/baseline_rag.py），报告并排对比 |
| H4 脱离具体 LLM | E6 双模型对照 |
| H5 可抽象为其他领域基础 | ADR-010 的领域包隔离审查 + 一次"迷你换域演练"（Sprint 6 选做：用 audit spec 走通 /context） |
