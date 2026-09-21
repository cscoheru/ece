# Demo 环境 Checklist (2026-09-30 现场演示)

> **作者**: Claude（Opus 5）
> **日期**: 2026-09-22
> **场景**: user 自带笔记本 → 客户会议室 HDMI, V0 spike 6 步现场演示 (~45 min)
> **原则**: 失败早暴露, 不在客户机前 debug

---

## T-1 天（09-29, demo 前一天）

### 笔记本准备

- [ ] macOS 系统更新已重启（避免 Docker Desktop 卡住）
- [ ] Docker Desktop 运行中（图标栏显示鲸鱼）
- [ ] 当前 shell 在 `~/projects/domainAgentECE/ece/` 目录
- [ ] 网络可用（pull 镜像 + 同步依赖）

### 试跑一遍（~10 min）

```bash
cd ~/projects/domainAgentECE/ece
bash scripts/run-demo.sh
```

**预期输出**: `[1/5] → [5/5]` 全部绿灯, 末尾打印"Demo 环境就绪！"

**如果失败**:
| 失败点 | 排查 |
|---|---|
| uv sync 失败 | 网络问题 / `~/.local/bin/uv` 不在 PATH（`export PATH="$HOME/.local/bin:$PATH"`）|
| docker compose 失败 | Docker Desktop 未启动 / 端口占用（5432）|
| postgres 30s 未就绪 | 内存不足 / 上一轮未清理（`docker compose down -v` 重来）|
| seed 失败 | 旧 DB 状态：`make rev + make gen-dataset + make db-upgrade + make seed`|
| S6 测试 fail | V0 spike 状态被破坏, 不要在客户机前 fix, 退回 09-22 现场排查 |

---

## T-30 min（09-30, 到达客户会议室）

### 物理准备

- [ ] 笔记本充电（demo 期间满电, 不要让客户看到电池焦虑）
- [ ] HDMI 线 / 投影测试（接客户会议室屏幕, 调到 1080p）
- [ ] **断网**（V0 spike 承诺离线运行, 断网是真实能力证明, 不是限制）

### 命令序列（粘贴执行, ~3 min）

```bash
cd ~/projects/domainAgentECE/ece
bash scripts/run-demo.sh
```

**等看到 "Demo 环境就绪！" 后开始 6 步演示**

---

## T-0（演示开始）

### Step 1: 三件证据开篇（5 min）

```bash
uv run pytest tests/evaluation/test_s6_determinism.py -v
uv run pytest tests/evaluation/test_s6_evidence_reversal.py -v
uv run python scripts/run_e2_permission.py
```

**讲稿**:
> "ECE V0 的三件证据, 对应客户最关心的三个问题:
> ① 规则没偏 → 同一查询跑 10 次 byte-equal
> ② 权限不漏 → 61 个权限测试 0 失败
> ③ 决策可追溯 → 一行 SQL 反查决策依据"

---

### Step 2: 张三 PR + POL-2026-03（8 min）

**前置**: 在另一 terminal 启动 MCP stdio

```bash
# terminal A
uv run python -m ece.mcp.transport
```

**terminal B**: 启动 Claude Desktop 或 Cline, 配置 ece MCP stdio

**demo query** (在 Claude Desktop 里问):
> "列出 demo 公司最近一个月 100 万+ 的采购申请, 按金额降序"

**预期**: 出现张三类 PR(>100万) + POL-2026-03 政策对照

**讲稿**:
> "张三(采购经理)提交的 PR, 触发 POL-2026-03 政策阈值检查。
> 这里 V0 用的是确定性规则引擎, 不是 LLM 猜的——所以审计师问'为什么这单没过', 可以反查。"

---

### Step 3: 比价完整性检查（5 min）

**demo query**:
> "对 PR-2024-001 检查比价完整性: 如果只有 2 家报价会怎样?"

**预期**: 系统阻断, 报错"必须 ≥3 家独立比价"

**讲稿**:
> "这是 ECE 拦截的最常见漏洞——比价流于形式, 实际只有 2 家报价。
> V0 直接在数据访问层拦住, 不是事后告警。"

---

### Step 4: Evidence 一行 SQL 反查（3 min）

```bash
uv run python -c "
from ece.db import get_engine
from sqlalchemy import text

with get_engine().connect() as conn:
    # 找出张三 PR 的决策依据
    rows = conn.execute(text('''
        SELECT entity_id, properties->>'decision_reason' as reason
        FROM entities
        WHERE properties->>'submitter' = '张3'
        LIMIT 3
    ''')).fetchall()
    for r in rows:
        print(f'{r[0]}: {r[1]}')
"
```

**讲稿**:
> "审计师问'这条决策的依据是什么', 我一行 SQL 就能反查。
> V0 的 Evidence 不是黑箱, 是 SQL 可读的。"

---

### Step 5: Permission denied 零副作用（3 min）

**demo query** (用未知 user token):
```bash
curl -H "X-User-Id: unknown_visitor" http://localhost:8000/context/search?q=PR
```

**预期**: 401 / 403, DB 无副作用（`docker compose logs db | tail -5` 无新 INSERT）

**讲稿**:
> "即使被越权访问, 系统最坏也是 no-op——不会返回脏数据, 不会污染 DB。
> 这是 V0 的 E2=0 测试覆盖的: 61 个权限用例全部拒绝+无副作用。"

---

### Step 6: Audit trail（3 min）

```bash
uv run python scripts/export_audit.py
```

**预期**: CSV 输出每条 context_request 的 (user, query, decision, trace_id)

**讲稿**:
> "每条决策都可追溯, 这是合规审计的基本要求。
> V0 的 audit trail 是内置的, 不是补丁。"

---

## 答疑准备（10 min buffer）

**客户最常问的 5 个问题 + 你的回答**（按 demo-script.md §5）:

| 客户问题 | 你的回答 |
|---|---|
| "你们怎么保证规则没偏？" | "S6 确定性测试, 同一查询跑 10 次 byte-equal" |
| "审计师问系统是否越权？" | "E2=0 测试, 61 个权限用例全部拒绝+无副作用" |
| "决策依据怎么反查？" | "一行 SQL, 上面刚演示" |
| "能不能接我们真实的 OA / ERP？" | "V0 用 CSV/JSON/本地, 接 OA 是 POC 后的事" |
| "价格多少？" | "按 PR 量, 我们 E15 谈过——下一轮细谈" |

---

## 故障兜底（如果演示中卡壳）

| 卡壳点 | 兜底动作 |
|---|---|
| docker 起不来 | "抱歉环境问题, 我们有录屏可以发您"（这时再求录屏）|
| postgres 连接超时 | `docker compose restart api` 等 10s 重试 |
| MCP stdio 无响应 | 重启 Claude Desktop |
| SQL 反查 0 行 | "这一 PR 没决策记录, 我换一个 demo PR"（演示回退）|
| 客户追问未实现功能 | "这个 V0 没覆盖, 我们有 Roadmap——可以约下一次" |

**核心纪律**: **永远不要在客户机前 debug 超过 5 分钟**。超 5 分钟就说"我们回到这个问题, 邮件答复您",保持演示节奏。

---

## 演示后 24h 内必做

- [ ] 写一份 meeting notes（关键反馈 + next step）
- [ ] 如果客户同意 POC:起草 POC 协议
- [ ] 如果客户犹豫:发"演示录屏 + 异步问询"（重拾 09-23 异步探针逻辑）
- [ ] 更新 `interview-001.md` §10 状态

---

**Author**: Claude（Opus 5）
**Date**: 2026-09-22
**Status**: 就绪, user 自跑验证 T-1 天 09-29