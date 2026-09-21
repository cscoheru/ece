# Cut-041 Report — S4.5 MCP Tool Layer 抢救补完

> **作者**: Claude（Opus 5）
> **日期**: 2026-09-21
> **触发**: V0 Spike 六步全闭合（Codex 裁定 2026-09-21 STOP）后 user 选 (a) S4.5 抢救 + (b) 客户访谈包并行；本报告仅覆盖 (a)。
> **范围锁**: 不引入新 Kernel 对象 / Adapter / Runtime；不改既有引擎文件 / spec / fixture / seeder；仅修 DoD 缺口。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 041（Sprint 4 S4.5 抢救补完） |
| **触发** | V0 Spike STOP 后 user go + 审计 cut-011 缺口 |
| **上游参考（只读）** | TASKS.md line 43-44（S4.5 DoD 字面） + `src/ece/mcp/{auth,tools,server}.py`（cut-011 既有实现） + `tests/integration/test_s5_mcp.py`（既有 8 测试，互补不重叠） |
| **审验者** | **Codex（待审验）** — 本文件不自写审验结论 |
| **执行者** | Claude（Opus 5） |
| **日期** | 2026-09-21 |
| **改动文件** | `src/ece/mcp/transport.py` (NEW, 19 行) + `tests/integration/test_mcp_server.py` (NEW, 132 行, 5 测试) + `TASKS.md` (EDIT, 单行 `[ ]` → `[x]`) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | 仅补 cut-011 当年漏掉的 DoD 文件清单；不触碰 Sprint 5/6、E6、LLM 接入、`actions/execute` 翻转、4 工具实现 |

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（transport.py + 测试 + TASKS 一组） |
| 报告 commit 数 | **1**（本文件） |
| 新增 Python文件 | 2（`src/ece/mcp/transport.py` + `tests/integration/test_mcp_server.py`） |
| 修改文件 | 1（`TASKS.md`） |
| 新增 测试 | 5（DoD 字面 4 条验收全覆盖 + transport import 探针） |
| 总计 | 3 files changed, 158 insertions(+) |

### 1.2 缺口分析（cut-011 漏什么 → cut-041 补什么）

| TASKS.md S4.5 DoD 字面 | cut-011 当年状态 | cut-041 处置 |
|---|---|---|
| `src/ece/mcp/server.py` | ✅ 实现（cut-011, 4 工具注册, `mcp.run()` 默认 stdio） | 不动 |
| `src/ece/mcp/auth.py` | ✅ 实现（cut-011, `check_user_permission` + `object_exists`） | 不动 |
| `src/ece/mcp/transport.py` | ❌ **缺失**（cut-011 报告 §1.2 自报"4 mcp modules"实际只 3 个） | **NEW**：薄壳 stdio 入口（19 行） |
| `tests/integration/test_mcp_*.py` | ❌ **缺失**（cut-011 写的 8 测试在 `test_s5_mcp.py`，不符合 DoD 文件名模式） | **NEW**：`test_mcp_server.py` 5 测试（132 行） |
| `pyproject.toml` `mcp>=1.0` | ✅ 已声明（cut-011 line 15） | 不动 |
| `python -m ece.mcp.server` 启动注册 4 工具 | ✅ 功能具备 | 测试 #1 验证（实测 4 工具名一致） |
| 权限强制 / 404 防探测 / preview-only | ✅ `test_s5_mcp.py` 8 测试覆盖工具行为 | **新增互补 5 测试**：覆盖 DoD 字面 + 协议层注册验证 + 404 envelope 形式化 |
| 离线 stdio 可用 | ✅ 默认 stdio | `transport.py` 显式 stdio；stdin 探针实测收到 MCP initialize 响应 |

**审计校正**：cut-011 报告 §1.2 自报"4 mcp modules + 2 test files"——前者 3 个，后者不在 `test_mcp_*.py` 模式。本刀**严格按 DoD 字面**重新对齐。

---

## 2. 实现细节

### 2.1 `src/ece/mcp/transport.py`（19 行）

薄壳 stdio 入口。**关键设计选择**：
- 不引入新 transport 抽象（违反铁律 3）
- 不改 `server.py` 既有 `mcp.run()` fallback（避免 SDK 行为差异风险）
- 直接 import 既有 `mcp` 实例 + 显式传 `transport="stdio"` 提升语义可读性

```python
def main() -> None:
    """Explicit stdio entry; same effect as `python -m ece.mcp.server`."""
    mcp.run(transport="stdio")
```

### 2.2 `tests/integration/test_mcp_server.py`（5 测试）

| # | 测试 | DoD 字面覆盖 | 与 `test_s5_mcp.py` 关系 |
|---|---|---|---|
| 1 | `test_server_registers_four_tools` | "启动注册 4 工具" | **全新**（协议层；S5_MCP 走直接 import tools，未触 MCP 协议） |
| 2 | `test_auth_check_user_permission_denies_unknown_user` | "权限强制"（负向） | **全新**（独立测 `auth.check_user_permission` 返回 False 路径；S5_MCP 走 `get_record_tool` 间接） |
| 3 | `test_auth_check_user_permission_allows_known_user_on_public_object` | "权限强制"（正向） | **全新**（独立测 `auth.check_user_permission` 返回 True 路径） |
| 4 | `test_get_record_404_anti_probing_returns_uniform_envelope` | "get_record 404 防探测" | **形式化补强**：S5_MCP 间接测了 forbidden/not_found；本测试显式断言 envelope **字段无泄漏**（`type`/`name`/`attrs`/`src` 不出现在 error 路径上） |
| 5 | `test_transport_module_imports_and_exposes_main` | "离线 stdio 可用"（import 契约） | **全新**（验证 DoD 字面文件存在且可调用 `main()`） |

**风格沿用 S5_MCP**：无 marker / dict key 检查 / `_demo_pr_display_id` helper 复制（避免既有文件隐式变动） / `pytest.skip` 兜底。

### 2.3 TASKS.md 单行编辑

`line 43`: `- [ ]` → `- [x]`，行末追加 `[cut-041 完成 2026-09-21: transport.py + tests/integration/test_mcp_server.py 5 测试齐备; 与既有 test_s5_mcp.py 互补不重叠]`。

---

## 3. 提交

```
[pending — auto-push per CLAUDE.md 修订 2026-09-14]
```

---

## 4. 红 → 绿 → 验证证据

### 4.1 目标测试

```
uv run pytest tests/integration/test_mcp_server.py -v
→ 5 passed in 0.73s
```

### 4.2 既有 MCP 测试无回归

```
uv run pytest tests/integration/test_s5_mcp.py tests/integration/test_mcp_server.py -v
→ 13 passed in 0.77s  (8 + 5)
```

### 4.3 全量回归

```
make test
→ 415 passed, 3 skipped, 0 failed  (79.04s)
```

V0 Spike 终态 410+3 → S4.5 闭合 **415+3**（+5 测试，零退化）。

### 4.4 E2 Permission 不破（TASKS.md DoD 字面）

```
uv run python scripts/run_e2_permission.py
→ Total cases: 61, Failures: 0, Exposures: 0
→ *** PASS: 0 Unauthorized Exposure, 0 permission failure ***
```

### 4.5 静态检查

```
uv run ruff check src/ece/mcp/ tests/integration/test_mcp_server.py
→ All checks passed!

uv run mypy src/ece/mcp/
→ Success: no issues found in 5 source files

uv run lint-imports
→ Contracts: 2 kept, 0 broken (Domain pack isolation KEPT / Engine core isolation KEPT)
```

### 4.6 stdio 启动验证

```
echo '{"jsonrpc":"2.0","method":"initialize",...}' | python -m ece.mcp.transport
→ {"jsonrpc":"2.0","id":1,"result":{"capabilities":{...},"serverInfo":{"name":"ECE Context Engine",...}}}
→ exit=0
```

实测 MCP initialize 协议握手成功，serverInfo.name 与 `MCPServer("ECE Context Engine")` 实例化一致——`transport.py` 不是空壳。

---

## 5. 范围锁对账

| 范围锁项 | 状态 |
|---|---|
| 不引入新 Kernel 对象 | ✅ 未触碰 |
| 不引入新 Adapter / Runtime | ✅ 未触碰 |
| 不改既有引擎文件 | ✅ `auth.py`/`tools.py`/`server.py` 零改动 |
| 不改 spec / fixture / seeder | ✅ 未触碰 |
| 不引入 LLM | ✅ 未触碰 |
| 不改 E1-E5 数据集 | ✅ 未触碰 |
| 不通过修改 expected 迎合实现 | ✅ 5 测试的 expected 与既有实现完全对齐 |
| 不扩 schema | ✅ 未触碰 |
| 不翻转 `actions/execute` 关闭 | ✅ 未触碰（`create_task_tool` 仍 `preview=True`） |
| TASKS.md 翻勾 | ✅ 仅 line 43（S4.5）一行；Sprint 5/6 保持 `[ ]` |

---

## 6. 已知遗留（移交，不在本刀范围）

1. **V0 Spike 4 项遗留**（Codex S6 裁定记入"已知疣子"）：① `package_id` 编码疣子 ② Z1/Z2 fixture 形状过滤 ③ §11 三处示意文案 ④ demo 客户化三缺口。**未触动**。
2. **`test_s5_mcp.py` 与 `test_mcp_server.py` 共存**：前者是 cut-011 遗产（互补覆盖工具行为），后者是 DoD 字面对齐（覆盖协议层 + 形式化 envelope）。**未合并**——避免隐式改动既有测试文件（S6 纪律）。
3. **Sprint 5/6**（Procurement Agent + E6 + Debugger/Demo）：**未触碰**，等 user 授权。
4. **(b) 客户访谈包**：与本刀并行起草中，**不耦合**，完成后另出报告。

---

## 7. 本阶段**未做**的事

- 未改任何既有实现文件（`auth.py`/`tools.py`/`server.py` 零改动）；
- 未引入新 transport 抽象 / 新 SDK 依赖 / 新 schema；
- 未触碰 LLM 接入 / `actions/execute` 翻转 / Sprint 5/6；
- 未扩 `test_s5_mcp.py`（cut-011 既有 8 测试未改动）。

---

**Author**: Claude（Opus 5）
**Date**: 2026-09-21
**Status**: cut-041 完成，等审验。**审验通过前不进入 Sprint 5 或其他 spike 外工作**。
