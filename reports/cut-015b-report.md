# Cut 015b Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: Sprint 5 follow-up #2 ——real LLM integration test (ECE_LLM_BASE_URL env → E6 ≥80% accuracy gate)。前一报告 `cut-015a-report.md` 完成 MockLLM status-based matching + E6 scale 50；本刀做真值 LLM test infra。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 015b（Sprint 5 follow-up #2） |
| **触发** | 用户 "cut-015b" 指令（per my proposal: real LLM integration test + ≥80% accuracy gate） |
| **上游参考（只读）** | `docs/EVALUATION.md` §1 (E6 ≥80% accuracy gate) + `cut-015a-report.md` §4.1 (MockLLM fragility lesson) + `cut-014-report.md` §1.2 (LLM client infrastructure) + ADR-006 (LLM Provider Independence) + ECE/CLAUDE.md §4 (LLM via env config) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-15 |
| **涉及文件** | `tests/integration/test_s5_5_real_llm.py` (NEW, 3 tests) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | real LLM integration test (3 tests, all skip if ECE_LLM_BASE_URL not set); Sprint 6 (Debugger UI + 私有化验收) deferred cut-016+ |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行。**1 个工作 commit（`de4d4b6`）+ 1 个报告 commit**。批处理不触碰 §7 区段。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（real LLM test infra 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 1（`tests/integration/test_s5_5_real_llm.py`） |
| 总计 | 1 files changed, 134 insertions(+) |

### 1.2 逐交付

#### Real LLM integration test（`tests/integration/test_s5_5_real_llm.py` NEW, 3 tests）

| Test | 验证 | Skip 行为 |
|---|---|---|
| `test_openai_compatible_client_shape` | POST `/v1/chat/completions` with `ECE_LLM_BASE_URL`; 验证 response 是 valid JSON | ECE_LLM_BASE_URL 未设 → skip |
| `test_get_llm_client_returns_openai_compatible_when_env_set` | `get_llm_client()` 工厂行为：env 设了 → 返回 `OpenAICompatibleClient`（env-var manipulation + restore 模式） | 同上 |
| `test_e6_runner_real_llm_accuracy_above_80_percent` | 跑 `scripts/run_e6_agent.py` subprocess 传 `--base-url`；parse "Accuracy:" line；assert ≥80% (EVALUATION.md §1 SLA) | 同上 |

**Run 真值测试**:
```bash
ECE_LLM_BASE_URL=http://your-llm-endpoint/v1 \
ECE_LLM_API_KEY=your-key \
ECE_LLM_MODEL=your-model \
uv run pytest tests/integration/test_s5_5_real_llm.py
```

`run_e6_agent.py` 早已支持 `--base-url` flag（per cut-014）；无需改动。test 通过 subprocess 传 `--base-url` → runner 设 `ECE_LLM_BASE_URL` env → `get_llm_client()` 返回 `OpenAICompatibleClient` 而非 `MockLLM` → 跑 50 cases 真值 LLM。

#### Skip 行为（核心设计）

V0 CI 无 LLM endpoint — 测试必须 skip（不能 fail）:
```python
def _real_llm_configured() -> bool:
    return bool(os.environ.get("ECE_LLM_BASE_URL"))
```

每个 test 调用 `_real_llm_configured()`，未设时 `pytest.skip(...)` 退出。**这是 V0 → 真值部署的"双轨"**:
- V0 CI: 跑 MockLLM E6 → keyword matching 准确率高
- 真值部署: 设 `ECE_LLM_BASE_URL` → 跑 OpenAICompatibleClient → 测真值 ≥80% accuracy gate

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `de4d4b6` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 84 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 133 passed, 6 skipped, 1 warning in 17.21s
$ make check-api-docs          # OK — no app-only routes (1 still "planned": audit/context/{id})
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
de4d4b6 test(s5): real LLM integration tests for E6 ≥80% accuracy gate (cut-015b closure)
cd4f1a4 docs(research-v2): cut 015a report (Sprint 5 follow-up — MockLLM status-based + E6 scale 50)
98469fe fix(s5): MockLLM status-based + E6 scale 50 + fallback (cut-015a closure)
ec32d71 docs(research-v2): cut 014 report (Sprint 5 — LLM client + Procurement Agent + E6 eval)
23e9c93 feat(s5): LLM client + Procurement Agent + E6 eval runner (cut-014 closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 133 passed 6 skipped (3 cut-015b real-LLM skip)
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| Sprint 6 (Debugger UI + 私有化验收) | cut-016+ |
| /audit/context/{request_id} endpoint | cut-016+ (Sprint 6) |
| E6 真值 ≥80% accuracy 实际数字 | 需要真值 LLM endpoint 配置（用户跑） |
| structured_data more kind handlers | cut-016+ |
| Sprint 4 vector route 真值测试 | cut-016+ |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE_LLM_BASE_URL env | ❌ 未设（V0 demo） | 测试自动 skip；真值部署时 `export ECE_LLM_BASE_URL=...` |
| 5 项 discipline | ✅ 全绿 | 无 |
| E6 ≥80% accuracy 实际数字 | ⚠️ 未跑（无 LLM） | cut-016+ 真值部署时跑 |
| MockLLM 准确率 | ⚠️ 依赖 keyword matching，预期 ≥70% (V0 简化) | 真值 LLM ≥80% (per EVALUATION.md §1) |

---

## 3. Commit 信息

**1 个工作 commit（real LLM test infra 一组）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `de4d4b6` | 1 file, +134/-0（test_s5_5_real_llm.py: 3 tests + skip 模式） | ✅ 5 项纪律全绿；make test 133 passed 6 skipped |

**HEAD after push**: `de4d4b66fcee9c70b69a97901c022986239d582d`

**Push range**: `cd4f1a4..de4d4b6 main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 V0 CI vs 真值部署"双轨" test 模式

**模式**: V0 CI 不配置真值 LLM（节约 cost/network），真值部署时切 env。

**实现**:
```python
def _real_llm_configured() -> bool:
    return bool(os.environ.get("ECE_LLM_BASE_URL"))

def test_e6_runner_real_llm_accuracy_above_80_percent():
    if not _real_llm_configured():
        pytest.skip("ECE_LLM_BASE_URL not set; skipping real LLM E6 accuracy test")
    # ... subprocess run_e6_agent.py with --base-url ...
```

**好处**:
- V0 CI：3 个 real-LLM test 自动 skip，总跑 test 数稳定（133 passed + 6 skipped）
- 真值部署：设 env，3 个 test 激活，verify ≥80% accuracy gate
- 同一 test 代码在 V0 + 真值都跑，**双轨无分支**

**Cut-015a 教训延续**: V0 MockLLM 测 keyword matching 准确率（不可靠）→ 真值 LLM 测 status field 准确率（≥80% gate）→ 同一 test infra 切换，**基础设施级双轨**（比 application code 双轨更优雅）

### 4.2 env-var manipulation + restore 模式（test isolation best practice）

`test_get_llm_client_returns_openai_compatible_when_env_set` 需要在测试里设 `ECE_LLM_BASE_URL` → 调用 `get_llm_client()` → 验证返回 `OpenAICompatibleClient`。但不能污染后续 test。

**Pattern**:
```python
saved_base = os.environ.get("ECE_LLM_BASE_URL")
try:
    os.environ["ECE_LLM_BASE_URL"] = "http://fake-llm:8080/v1"
    client = get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
finally:
    if saved_base is None:
        os.environ.pop("ECE_LLM_BASE_URL", None)
    else:
        os.environ["ECE_LLM_BASE_URL"] = saved_base
```

**关键**:
- `try/finally` 保证 restore（即使 assert fail 也执行）
- 区分 "原 env 没设" vs "原 env 设了" — pop vs restore
- 测试完成不留副作用

**Cut-015a 教训延续** (autouse fixture SELF-SUFFICIENT): test 修改 env 也要 SELF-CONTAINED — restore 后其它 test 看不到修改

---

## 5. 经验教训

1. **V0 CI vs 真值部署"双轨" test 模式**（§4.1）: V0 MockLLM 测 keyword → 真值 LLM 测 status field → 同一 test infra 切换（`ECE_LLM_BASE_URL` env）→ 比 application code 双轨优雅。**未来每个真值依赖的 test 都应支持 skip**
2. **env-var manipulation + restore 模式**（§4.2）: `try/finally` + 区分 pop vs restore → test 不留副作用。**autouse fixture SELF-SUFFICIENT**（cut-013 §4.1）+ env test 隔离（cut-015b §4.2）= test isolation best practice
3. **E6 ≥80% accuracy gate**（per EVALUATION.md §1）: V0 CI auto-skip，**真值部署必跑**。设 `ECE_LLM_BASE_URL` 后 50 cases 应 ≥80% direction match + evidence match。**这是 v0 → 1.0 production cut-over 的关键 gate**
4. **跨 cut 一致性**（cut-014/015a/015b）: MockLLM 改进 + E6 scale + real LLM test = **三层 E6 eval infrastructure**（mock/status/real）。这是 Sprint 5 收口的完整路径
5. **跨 cut 红线**（§6.4）: V0 CI skip 模式 + env-var 隔离 + 真值部署 gate 必跑——累积入红线

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-015b-report.md` | `ece/reports/cut-016-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 2 项非典型项（**V0 CI vs 真值部署双轨 test / env-var manipulation + restore 模式**）
- §5 5 条教训
- §6 红线 (累积 cut-007-008-009-010-011-012-013-014-015a-015b)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013-014-015a-015b）

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
- **MockLLM substring 匹配 fragility**（cut-014 §4.1 + cut-015a §4.1）
- **真值 LLM test 不支持 env-skip 双轨**（cut-015b §4.1 入红线——V0 CI 必须 auto-skip，避免 cost/network；真值部署激活测 ≥80% gate；同一 test infra 切换最优雅）
- **test 修改 env 不 try/finally restore**（cut-015b §4.2 入红线——env test 隔离保证：try/finally + 区分 pop vs restore；autouse fixture SELF-SUFFICIENT 原则延伸）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。