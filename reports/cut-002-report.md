# Cut 002 执行报告（CC）

> **模板说明**: 本文件按根仓 `docs/track_b/clines-review-cycle-001.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。

---

## 0. 元数据

| 项 | 值 |
|---|---|
| **Cut** | 002 |
| **触发** | 用户第二刀指令（2026-09-13）：基于根仓 `docs/track_b/execution-plan.md §4` + `docs/track_b/track-a-decisions.md §2`（ADR-004 审计链），要求修订 `ece/TASKS.md` |
| **上游参考（只读，位于根仓）** | `/Users/kjonekong/projects/domainAgentECE/docs/track_b/execution-plan.md §4`<br/>`/Users/kjonekong/projects/domainAgentECE/docs/track_b/track-a-decisions.md §2` |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1，Anthropic） |
| **日期** | 2026-09-13 |
| **涉及文件** | `ece/TASKS.md`（修改）+ `ece/reports/cut-002-report.md`（新建，本文件） |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | 仅改 `ece/TASKS.md`（2 处）+ 新建 `ece/reports/cut-002-report.md`；不写任何产品代码；不动 `ece/src/`、`ece/docs/`、根仓 `domainAgentECE/*` |

> **Override 注记**: 本刀修改了 ece/ 仓文件（原 ROOT CLAUDE.md / 用户早期 setup 提示"不要在本仓操作它"）。本刀用户明确授权此操作，override session-level 约束。后续 刀是否恢复原约束需用户明示。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 修改文件数 | 1（`ece/TASKS.md`） |
| 新增文件数 | 1（`ece/reports/cut-002-report.md` — 本文件） |
| 修复项总数 | 2（R1: S4.5 新增；R2: S4.2 措辞修正） |
| 涉及行 | S4.2（line 40）+ S4.5 插入（after line 42） |
| Commit | 见 §3 |

### 1.2 逐条修复（file:line + 修复前后）

| # | 文件:行号 | 关联 | 修复前 | 修复后 |
|---|---|---|---|---|
| **R1** | `ece/TASKS.md:43-47`（S4.5 新增） | 根仓 `execution-plan.md §4` | （无 S4.5） | `- [ ] S4.5 MCP Tool Layer（K7，设计=根仓 execution-plan.md §4）：src/ece/mcp/{server,transport,auth}.py；暴露 4 工具 search / get_record / create_task / send_message，后两个仅 Preview 不执行；每个 tool call 强制经 PermissionScope（auth.py），不得绕过权限引擎；Claude Code 接入：\`claude mcp add ece-context -- python -m ece.mcp.server\`（仓库根目录执行）；mcp SDK 依赖本任务动工时引入 pyproject（S0.1 不加）。`<br/>`  验收：...E2=0 不破；离线 stdio 可用。` |
| **R2** | `ece/TASKS.md:40`（S4.2 措辞） | 根仓 ADR-003（SQL 子查询层强制，不是 post-filter） | `Query Planner：keyword(FTS+bigram)/vector/structured/relationship 四路 + Entity Linking + 权限后置过滤 + merge/rank` | `Query Planner：... + Entity Linking + 权限 SQL 下推（四路召回各自查询内做 PermissionScope 过滤，先过滤、后排序/截断；denied 仅计数） + merge/rank` |

---

## 2. 审验范围

### 2.1 自检 grep（本仓 ece/）

```bash
# 1. 旧措辞必须彻底清除
$ grep -n '权限后置过滤' ece/TASKS.md
[空]

# 2. S4.5 必须存在（任务行 + 验收行）
$ grep -n 'S4.5' ece/TASKS.md
43:- [ ] S4.5 MCP Tool Layer...
45:  验收：`python -m ece.mcp.server`...（含 "S4.5" 不直接命中但任务包含 S4.5 标识）

# 3. S0.1 未被改动（计数应为 2：任务行 + Sprint 0 标题引用）
$ grep -c 'S0.1' ece/TASKS.md
2
```

**实际输出见 Bash 报告。**

### 2.2 git 二次审计（任何人可复现）

```bash
# 1. 看 commit 详情
git show <commit> --stat

# 2. 看改动 diff
git diff <prev>..<this> -- ece/TASKS.md

# 3. 验证 S4.2 措辞已修正
git show <this>:ece/TASKS.md | grep -n '权限 SQL 下推'

# 4. 验证 S4.5 已新增
git show <this>:ece/TASKS.md | grep -n 'S4.5 MCP Tool Layer'
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| `ece/src/` | 用户明确禁止产品代码 |
| `ece/docs/`（ADR / PRD / ARCHITECTURE / DATA_MODEL / API / EVALUATION） | 用户明确禁止动产品文档 |
| `ece/tests/` | 不在改动范围 |
| `ece/TASKS.md` 其他段落 | 仅 S4.2 + S4.5 两处改动 |
| 根仓 `domainAgentECE/*` | 本刀在 ece/ 仓执行，不动根仓 |

### 2.4 跨 Sprint 依赖（给后续 刀 参考）

| 项 | 说明 |
|---|---|
| **S4.5 → S5.3** | `create_task` / `send_message` 工具的 Preview-only 行为需 S5.3 `/actions/preview` 配合实现（不允许 S4.5 提前 execute） |

---

## 3. Commit 信息

```
[main <hash>] tasks: add S4.5 MCP Tool Layer + fix S4.2 permission wording (per root track_b spec)
 1 file changed, <N> insertions(+), <N> deletions(-)
```

**Pushed**: `<prev>..<this> main -> main` ✅

**Commit hash**: 见下方报告

---

## 4. 本刀特有的非典型项

| 项 | 说明 |
|---|---|
| **跨仓操作** | 本刀从 `domainAgentECE` session 修改 `ece/` 仓文件（override ROOT CLAUDE.md "不要在本仓操作它" session-level 约束）。本刀用户明确授权 |
| **报告路径不同** | 根仓 cycle-001 报告在 `docs/track_b/clines-review-cycle-001.md`，本刀报告在 `ece/reports/cut-002-report.md`（仓独立） |
| **自检 grep 数量** | 用户指定 3 条 grep（`权限后置过滤` / `S4.5` / `S0.1` 计数），与 cycle-001 模式不同 |
| **范围声明差异** | cycle-001 范围仅 `docs/track_b/`；本刀范围仅 `ece/TASKS.md` + `ece/reports/` |

---

## 5. 经验教训

1. **跨仓 vs 同仓操作**: 本刀跨仓（根仓 session 改 ece/）。后续 刀需在元数据中明示仓归属
2. **同仓或跨仓模板是否统一**: 当前 cycle-001（根仓）+ cut-002（ece）模板结构一致，但命名不同（`cycle-NNN` vs `cut-NNN`）。后续可考虑统一命名规范
3. **S4.5 跨 Sprint 依赖**: `create_task` / `send_message` Preview-only 行为依赖 S5.3 Actions Preview 实现，需同步更新 S5.3 验收点（如尚未明确）
4. **OVERRIDE 注记**: 跨 session-level 约束的操作必须在 §0 显式声明，便于审计

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本 Cut | 后续 Cut |
|---|---|
| `ece/reports/cut-002-report.md` | `ece/reports/cut-NNN-report.md`（NNN 递增，从 002 起） |

> **注意**: 命名与根仓 `docs/track_b/clines-review-cycle-NNN.md` 不同（cycle vs cut）。后续是否统一由用户决定。

### 6.2 必保留章节

- §0 元数据 + override 注记（若跨仓或破约束）
- §1 完成情况 + 改动统计 + file:line 修复前后
- §2 审验范围（自检 grep + git 命令 + 排除项）
- §3 Commit 信息
- §4 本刀非典型项（可选）
- §5 经验教训（可选）
- §6 模板说明
- §7 红队审验占位（**不自写**）

### 6.3 必做的最小验证

每个 刀 commit 后必须做自检 grep，退出码 1 = PASS（无匹配）。

### 6.4 禁止事项

- §7 红队审验结论 — **不自写**，由 Cline 填写

---

## 7. 红队审验结论（Cline 待写）

<!-- Cline 红队审验结论待写入 -->
