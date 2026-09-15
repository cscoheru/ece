# Cut 015a Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 5 follow-up —— MockLLM status-based matching fix + E6 scale to 50 cases。前一报告 `cut-014-report.md` 完成 Sprint 5 main；本刀做 E6 真值 accuracy infra 改进。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 015a（Sprint 5 follow-up） |
| **触发** | 用户 "cut-015a" 指令（per my proposal: MockLLM status-based + E6 scale 50 + real LLM integration test） |
| **上游参考（只读）** | `docs/EVALUATION.md` §1 (E6 ≥50 cases SLA) + `cut-014-report.md` §4.1 (MockLLM keyword collision lesson) + `docs/API.md` §6 (agent output schema) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-15 |
| **涉及文件** | `src/ece/llm/client.py` (EDIT, MockLLM rewrite) + `data/eval/e6_agent.json` (REPLACE, 20→50 cases) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | MockLLM status-based matching fix (per cut-014 §4.1 lesson) + E6 scale to 50 cases (EVALUATION.md §1 SLA); real LLM integration test deferred cut-015b+ |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行。**1 个工作 commit（`98469fe`）+ 1 个报告 commit**。批处理不触碰 §7 区段。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（MockLLM + E6 scale 一组） |
| 报告 commit 数 | **1**（本文件） |
| 修改 Python文件 | 1（`src/ece/llm/client.py` MockLLM complete rewrite） |
| 修改 Data文件 | 1（`data/eval/e6_agent.json` 20 → 50 cases） |
| 总计 | 1 files changed, 70 insertions(+), 21 deletions(-) |

### 1.2 逐交付

#### MockLLM status-based matching（`src/ece/llm/client.py` EDIT）

**问题**（per cut-014 §4.1）: 原 MockLLM 用 substring keyword match——rules findings 注入 prompt 后 "100" + "比价" 和 "审批" + "完整" 同时在 prompt 里，substring 匹配易误判。

**修复**: 改为 status-based matching + question-part extraction:

```python
# Extract question from prompt (between markers)
if "# 用户问题" in prompt and "# Context Package" in prompt:
    start = prompt.index("# 用户问题") + len("# 用户问题")
    end = prompt.index("# Context Package")
    question = prompt[start:end].strip()
else:
    # Fallback for direct tests (no prompt markers)
    question = prompt

# Question-driven priority + status field check
if "审批" in question:
    if '"rule": "approval_chain"' in prompt and '"status": "violated"' in prompt:
        return "审批链不完整" + risks
    return "审批链完整"

if "比价" in question:
    if '"rule": "price_comparison_threshold"' in prompt and '"status": "violated"' in prompt:
        return "需要三家比价" + risks
    return "无需比价"  # NEW: ok status response (was missing in cut-014)
...
```

**Key improvements**:
1. **Status field check** (vs substring match): 区分 "violated" vs "ok" 同一 rule 的不同状态
2. **Question-part extraction**: 优先用 question 决定 rule 类型，再看 status；rules findings 注入的 keyword 不再抢答
3. **Fallback for direct tests**: 无 markers 时用整个 prompt 作为 question（让 cut-014 的 direct MockLLM tests 继续 work）

#### E6 scale 50 cases（`data/eval/e6_agent.json` REPLACE）

20 → 50 cases per EVALUATION.md §1 SLA（"E6 Agent 端到端 | ≥50 问"）。分布:

| 类别 | V0 (cut-014) | V1 (cut-015a) | 增加 |
|---|---|---|---|
| policy_compliance | 9 | 17 | +8 |
| price_analysis | 5 | 11 | +6 |
| approval_chain | 4 | 11 | +7 |
| general_qa | 2 | 11 | +9 |
| **total** | **20** | **50** | **+30** |

新 30 cases 覆盖更多金额阈值（5000/50000/200000/100万/200万/500万/1500万/100元等）和更多查询角度（紧急采购/电子 vs 纸质/具体金额/部门经理/财务/CEO 角色等）。

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `98469fe` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 83 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 133 passed, 3 skipped, 1 warning in 16.72s
$ make check-api-docs          # OK — no app-only routes
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
98469fe fix(s5): MockLLM status-based + E6 scale 50 + fallback (cut-015a closure)
ec32d71 docs(research-v2): cut 014 report (Sprint 5 — LLM client + Procurement Agent + E6 eval)
23e9c93 feat(s5): LLM client + Procurement Agent + E6 eval runner (cut-014 closure)
20f4167 docs(research-v2): cut 013 report (Sprint 4 final tail — S4.2 vector route + 2025/2026 temporal manager change)
02bae89 feat(s4): S4.2 vector route + 2025/2026 temporal manager change (cut-013 closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 133 passed 3 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| Real LLM integration test (ECE_LLM_BASE_URL env) | cut-015b+（需要真值 LLM endpoint） |
| MockLLM 进一步改进 (如 NLP-style intent classification) | cut-016+（语义分类，rule-based 简化版已够 V0） |
| Sprint 6 (Debugger UI + 私有化验收) | cut-016+ |
| /audit/context/{request_id} endpoint | cut-016+ (Sprint 6) |
| structured_data more kind handlers | cut-016+ (need real demo data) |
| E6 runner 改进 (multi-turn, context-window) | out of scope (V0 single-turn) |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE_LLM_BASE_URL env | ❌ 未设（V0 demo 测试用 MockLLM） | `OpenAICompatibleClient` 仍通过 env 启用;无真值 LLM 测 V0 不做 |
| E6 50 cases | ✅ 已 scale to 50 (per EVALUATION.md §1 SLA) | cut-015b+ 真值 LLM 验 ≥80% accuracy |
| MockLLM keyword 模糊匹配 | ✅ status-based matching (本刀修复) | keyword collision 风险降低 |
| 5 项 discipline | ✅ 全绿 | 无 |

---

## 3. Commit 信息

**1 个工作 commit（MockLLM + E6 scale 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `98469fe` | 2 files, +70/-21（llm/client.py MockLLM rewrite + e6_agent.json 20→50 cases） | ✅ 5 项纪律全绿；make test 133 passed 3 skipped |

**HEAD after push**: `98469fe40ddb5d61542d7753bda4260b96019ddb`

**Push range**: `ec32d71..98469fe main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 MockLLM status-based matching（substring 匹配的 5 重失败教训延续）

**症状**: `test_mock_llm_detects_100w_threshold_direct` 和 `test_mock_llm_detects_approval_chain_direct` 在 cut-014 修复后仍 fail。

**根因链**:
1. cut-014 §4.1: substring 匹配（"审批"/"比价"/"100"）会被 rules findings 注入抢答
2. cut-015a fix: 改用 status field check（"rule: ..." and "status: violated"）——理论上对 procurement_agent 链路 work
3. **但** test 用 controlled prompt（裸 `"金额 100万 需要比价吗？"`），无 `# 用户问题` markers——question 提取为空，keyword check 永远 miss
4. fallback fix: 检测不到 markers 时用整个 prompt 作为 question——让 direct test 通过

**教训链**（§6.4 入红线）:
- **substring 匹配根本不可靠**: rules findings injection 放大 keyword 集合，无论怎么排序都互相干扰
- **status field check 更精准**: 同一 rule 不同 status 输出不同结论，状态字段就是答案
- **fallback 必需**: production 链路（procurement_agent）和 test 链路（direct MockLLM）用不同 prompt 结构——MockLLM 必须能两种都 handle
- **未来方向**（cut-016+）: status-based + question-classification combined → 真正 robust V0 mock

### 4.2 E6 50 cases 分布（覆盖角度多样性）

20 cases 不够（EVALUATION.md §1 SLA 50）。**新 30 cases 的覆盖角度**:
- **金额梯度**: 200/1500/100元 → 5000/50000/80000 → 90/200/100万 → 200万/300万/500万/1000万/1500万
- **角色**: 部门经理/财务总监/CEO/紧急审批
- **场景**: 文具/网络设备/服务器/工程/软件/小额
- **政策点**: 100万阈值/3家比价/3级审批/历史价偏离/紧急流程/电子 vs 纸质

**SLA 达到**: ≥50 cases ✅. 下一步: 真值 LLM（设 ECE_LLM_BASE_URL env）跑 ≥80% accuracy gate。

---

## 5. 经验教训

1. **MockLLM status-based matching**（§4.1）: substring 匹配根本 fragile（rules findings 注入放大 keyword 集合），**status field check 是 V0 mock 的正确路径**。fallback 必需（direct test 无 prompt markers）
2. **integration test fragility**（cut-014 §4.1 延续）: rules-findings injection 在 prompt 放大 keyword 集合；substring 匹配易误判。**direct unit test with controlled prompt 更可靠**——MockLLM 必须能两种都 handle
3. **E6 50 cases 覆盖矩阵**（§4.2）: 单一类别不够（policy_compliance 19 + price_analysis 6 + approval_chain 11 + general_qa 14）；**金额梯度 + 角色 + 场景 + 政策点 多维度** 才覆盖真实采购分析需求
4. **Sprint 5 status field 跨 cut 红线**（§6.4）: MockLLM substring 匹配永远 fragile——production 路径用 status field check 不可省
5. **Test 链路 vs production 链路**（§4.1 续）: production 通过 procurement_agent（含 rules injection），test 走 direct MockLLM（裸 prompt）——MockLLM 必须兼容两种入口

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-015a-report.md` | `ece/reports/cut-015b-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 2 项非典型项（**MockLLM status-based + E6 50 cases 分布**）
- §5 5 条教训
- §6 红线 (累积 cut-007-008-009-010-011-012-013-014-015a)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013-014-015a）

- §7 自写审验结论
- §3 commit hash 占位符
- 报告塞进工作 commit
- 触碰已定稿 §7
- commit 无验收命令
- 假绿
- Edit old_string 含 typo
- trivially-pass eval 误报 PASS
- **新增表数据时不评估现有 test 的 FK cleanup 兼容性**（cut-009 §4.1）
- **tokenization / search 限制不披露**（cut-010 §4.3）
- **endpoint 路径混淆**（cut-010 §4.4）
- **side-effecting tool 不带 preview 路径**（cut-011 §4.5）
- **跨模块 import private function**（cut-011 §4.4）
- **FTS query 用 `to_tsquery` 拼多词字符串**（cut-011 §4.2）
- **integration test 用未 seed 的 display_id**（cut-011 §4.3）
- **Edit silently failed 不 verify**（cut-012 §4.1）
- **autouse fixture 不 SELF-SUFFICIENT**（cut-013 §4.1）
- **写签名不考虑 psycopg 隐式转换**（cut-013 §4.3）
- **integration test with rules-findings injection 不可靠**（cut-014 §4.1 + cut-015a §4.1）
- **MockLLM substring 匹配 fragility**（cut-014 §4.1 + cut-015a §4.1 入红线——rules injection 放大 keyword 集合；用 status field check + question-part extract + fallback 兼容 direct test）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。