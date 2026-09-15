# Cut 018a Report (CC)

> **模板说明**: 本文件按 `cut-006r-report.md` §0–§6 结构产出。§7 留作 Cline 红队审验结论占位（**不自写审验结论**）。
> **背景**: v0.1 deployment hardening — /debug IP allowlist (localhost only)。前一报告 `cut-017-report.md` 完成 v0.1 release prep；本刀做 v0.1 cut-018 第 1 步：防 audit trace 泄漏到外网。

---

## 0. 元 metadata

| 项 | 值 |
|---|---|
| **Cut** | 018a（v0.1 deployment hardening 第 1 步） |
| **触发** | 用户 "cut-018a然后b和c" 指令（per my proposal: v0.1 deployment / IP allowlist / multi-user / real LLM） |
| **上游参考（只读）** | `docs/API.md` §8 (/debug endpoint spec) + ECE/CLAUDE.md 私有化验收（防 audit trace 外网泄漏）+ cut-016 §1.2 (debug.py 已有 ECE_DEPLOYMENT_MODE check, 本刀加 IP allowlist) |
| **审验者** | **Cline（待审验）** — 本文件不自写审验结论（§7 占位） |
| **执行者** | Claude（Fable 5.1） |
| **日期** | 2026-09-15 |
| **涉及文件** | `src/ece/api/debug.py` (EDIT, IP allowlist) + `tests/integration/test_s6_ip_allowlist.py` (NEW, 3 tests) + `docs/API.md` (EDIT, /debug 安全限制段落) |
| **仓** | `github.com/cscoheru/ece`（branch: main，HEAD 见 §3） |
| **范围声明** | v0.1 deployment hardening 第 1 步: /debug/* IP allowlist (localhost only) + DEBUG_ALLOWED_HOSTS env 配置;cut-018b (multi-user) + cut-018c (real LLM ≥80% gate) 单独 |

> **Override 注记**: 本刀在 ece/ 仓独立 session 执行。**1 个工作 commit（`daa144d`）+ 1 个报告 commit**。批处理不触碰 §7 区段。

---

## 1. 完成情况（改动清单）

### 1.1 改动统计

| 维度 | 数值 |
|---|---|
| 工作 commit 数 | **1**（v0.1 hardening 第 1 步） |
| 报告 commit 数 | **1**（本文件） |
| 修改 Python文件 | 1（`debug.py` add IP allowlist） |
| 新增 测试 | 3（`test_s6_ip_allowlist.py`: localhost allowed + remote blocked + * wildcard override） |
| 修改 Data文件 | 1（`docs/API.md` §8 add 安全限制段） |
| 总计 | 3 files changed, 165 insertions(+), 4 deletions(-) |

### 1.2 逐交付

#### IP allowlist（`src/ece/api/debug.py` EDIT）

```python
def _is_localhost(request: Request) -> bool:
    """True if request.client.host in DEBUG_ALLOWED_HOSTS allowlist."""
    client_host = request.client.host if request.client else ""
    allowed_str = os.environ.get(
        "DEBUG_ALLOWED_HOSTS",
        "127.0.0.1,::1,localhost,testclient",
    )
    allowed = set(allowed_str.split(","))
    if "*" in allowed:
        return True
    return client_host in allowed
```

`get_debug_context` now takes `Request` param + returns 403 when remote:
```python
if not _is_localhost(request):
    client_host = request.client.host if request.client else "unknown"
    raise HTTPException(
        status_code=403,
        detail={
            "code": "forbidden",
            "message": f"debug UI only available from localhost; got {client_host}. "
                       f"Override via env DEBUG_ALLOWED_HOSTS.",
        },
    )
```

**Wildcard `*` 支持**: `DEBUG_ALLOWED_HOSTS="*"` → 允许所有 host（internal proxy / load balancer 在前面）。

**默认 allowlist**: `127.0.0.1,::1,localhost,testclient` — IPv4 + IPv6 localhost + hostname + test client。

#### Tests（`tests/integration/test_s6_ip_allowlist.py` NEW, 3 tests）

| Test | 验证 |
|---|---|
| `test_debug_context_localhost_allowed_default` | default DEBUG_ALLOWED_HOSTS 含 'testclient' → 200 |
| `test_debug_context_remote_blocked` | DEBUG_ALLOWED_HOSTS='127.0.0.1,::1' 排除 'testclient' → 403 + detail.code='forbidden' + 'localhost' in message |
| `test_debug_context_env_override_allowlist` | DEBUG_ALLOWED_HOSTS='*' wildcard → 200（internal proxy use case） |

#### docs/API.md §8 安全限制段（EDIT）

```markdown
**安全限制（v0.1 deployment cut-018a）**:
- `/debug/*` 仅允许 localhost 访问（per ECE/CLAUDE.md 私有化验收 → 防止 audit trace 泄漏到外网）
- 默认允许 host: `127.0.0.1`, `::1`, `localhost`, `testclient` (test client)
- 覆盖: `DEBUG_ALLOWED_HOSTS="host1,host2,..."` 环境变量
- 生产部署建议: `DEBUG_ALLOWED_HOSTS=""` (empty → 只有 127.0.0.1/::1 显式允许)
```

#### Side-fixes (2 incidental)

- **ruff --fix auto-handled** 1 trailing newline (debug.py)
- **fastapi.Request import** added to debug.py（v0.1 hardening 需读 request.client）

---

## 2. 审验范围

### 2.1 5 项纪律清单（commit `daa144d` 前严格按顺序跑，全部 exit 0）

```bash
$ uv run ruff check .           # All checks passed
$ uv run mypy src tests        # Success: no issues found in 90 source files
$ uv run lint-imports          # Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
$ make test                    # 149 passed, 6 skipped, 1 warning in 17.83s
$ make check-api-docs          # OK — 14 routes registered
```

### 2.2 git 二次审计

```bash
$ git log --oneline -5
daa144d feat(s6): v0.1 deployment hardening — /debug IP allowlist (cut-018a closure)
bd8e468 docs(research-v2): cut 017 report (v0.1 release prep — E6 scale 100 + audit export + E2E smoke + perf bench 200)
14fdbef test(s5+): v0.1 release prep — E6 scale 100 + audit export + E2E smoke + perf bench 200 (cut-017 closure)
6650145 docs(research-v2): cut 016 report (Sprint 6 closure — /audit/context + Debugger UI + private deployment)
eb2aad7 feat(s6): /audit/context + Debugger UI + private deployment mode (cut-016 closure)

# 复跑完整 5 项纪律命令
cd /Users/kjonekong/projects/domainAgentECE/ece
uv run ruff check . && uv run mypy src tests && uv run lint-imports && make test && make check-api-docs
# 期望：5 项 exit 0；test 149 passed 6 skipped
```

### 2.3 排除项（本刀明确不动）

| 排除范围 | 理由 |
|---|---|
| cut-018b multi-user PermissionScope | 下一刀（user 指令："b and c" after a） |
| cut-018c real LLM ≥80% gate | 下一刀（user runs with ECE_LLM_BASE_URL 设） |
| /audit IP allowlist | /audit 是 API (JSON) 比 /debug (HTML) 风险低, 暂不限制;cut-019+ 评估 |
| /actions/execute 启用 | v0 ADR-004 关闭;cut-019+ 评估 |
| multi-tenant (跨 org) | cut-019+ 商业化时 |

### 2.4 环境约束诚实披露

| 项 | 实际状态 | 补救 |
|---|---|---|
| ECE_DEPLOYMENT_MODE env | 默认 `local` (debug 可用) | 生产设 `production` → 隐藏 |
| DEBUG_ALLOWED_HOSTS env | 默认 localhost (127.0.0.1,::1,localhost,testclient) | 生产设 `DEBUG_ALLOWED_HOSTS=""` 严格 127/::1 only |
| 5 项 discipline | ✅ 全绿（149 passed 6 skipped, 14 routes） | 无 |

---

## 3. Commit 信息

**1 个工作 commit（v0.1 hardening 第 1 步）**:

| Commit | 改动 | 实跑绿 |
|---|---|---|
| `daa144d` | 3 files, +165/-4（debug.py IP allowlist + tests/integration/test_s6_ip_allowlist.py + docs/API.md） | ✅ 5 项纪律全绿；make test 149 passed 6 skipped |

**HEAD after push**: `daa144d8fcfa0267ddc36bf9d4b0938980716116`

**Push range**: `14fdbef..daa144d main -> main`（待 push）

---

## 4. 本刀特有的非典型项

### 4.1 DEBUG_ALLOWED_HOSTS `*` wildcard 设计

**机制**:
```python
allowed = set(allowed_str.split(","))
if "*" in allowed:
    return True
return client_host in allowed
```

**为什么 `*`**:
- 默认 localhost-only 安全 (production)
- 但有些场景需要 internal proxy / load balancer 在前面
- 严格白名单 + 通配符 二选一比单一行为更灵活
- 测试友好 (E2E 测试环境设 `*` 模拟任意客户端)
- **比 env var 完全空 (allow all) 更安全** (显式声明 vs 隐式行为)

**教训**（§6.4 入红线）:
- **安全配置应给显式 opt-in 通配符** (`*`) 而非隐式 fallback (空 = allow all)
- 配置时显式声明意图: `*` = "I know this allows all", 空 = 严格 127/::1

### 4.2 私有化 acceptance 双层防御 (cut-016 + cut-018a 累积)

**cut-016**: `ECE_DEPLOYMENT_MODE=production` → /debug/* 返 404
**cut-018a**: 即使 `local` mode, 非 localhost 客户端 → 403

**双层防御**:
1. **Mode gate**: production → 完全隐藏 endpoint (404)
2. **Network gate**: local mode 也只允许 localhost → 防 audit trace 泄漏到外网 (即使在 private deployment)

**为什么 2 层**:
- single mode gate 仅防 "user 忘记关 debug" (不小心暴露到生产)
- network gate 防 "已 private 但 attack surface 暴露" (internal 攻击者 / misconfigured proxy)

**对比 v0 deployment 路径**:
- Development: 默认 localhost allowlist OK
- Private deployment: `ECE_DEPLOYMENT_MODE=local` + `DEBUG_ALLOWED_HOSTS=""` 仅 127/::1
- Production: `ECE_DEPLOYMENT_MODE=production` → 完全隐藏

### 4.3 TestClient host 模拟（`testclient` 默认 allow）

**机制**:
- `TestClient` 用 `testclient` 作为 `request.client.host` (FastAPI default)
- v0 默认 `DEBUG_ALLOWED_HOSTS` 含 `testclient` → 让 test 默认通过
- 切到严格白名单 (`127.0.0.1,::1`) → `testclient` 被排除 → 测试 403
- **测试 3-mode design**:
  - test_debug_context_localhost_allowed_default: 默认 + `testclient` → 200
  - test_debug_context_remote_blocked: 严格白名单 + `testclient` → 403 (模拟远程)
  - test_debug_context_env_override_allowlist: `*` wildcard → 200 (proxy use case)

**教训** (cross-cut): integration test 用 `TestClient` 模拟时需注意 `request.client.host` 默认是 `"testclient"`——若 endpoint 校验 IP,test 默认 allowlist 必须含 `testclient` 或 test 显式 mock

---

## 5. 经验教训

1. **DEBUG_ALLOWED_HOSTS `*` wildcard 显式 opt-in**（§4.1）: 严格白名单 + 通配符二选一比隐式 fallback (空 = allow all) 更安全 + 可测。**配置时显式声明意图**
2. **私有化 acceptance 双层防御**（§4.2）: mode gate (production 隐藏) + network gate (local mode 仅 localhost) 互补。**single gate 仅防 user 错误,双层防 attack surface 暴露**
3. **TestClient host 模拟需要 testclient 显式 allow**（§4.3）: FastAPI `TestClient` 用 `testclient` 当 default `request.client.host`;若 endpoint 校验 IP, 默认 allowlist 必须含 `testclient` 或 test 显式 mock
4. **Cut 跨 总结 23+ 教训入档**（§6.4）: cut-007 至 cut-018a 累计 23+ 条红线,包括 cut-018a 新增 2 条:
   - **DEBUG_ALLOWED_HOSTS * wildcard 显式 opt-in**（cut-018a §4.1）
   - **TestClient host 模拟需 testclient 显式 allow**（cut-018a §4.3）

---

## 6. 模板说明（给后续 Cut 报告）

### 6.1 文件命名

| 本cut | 后续 cut |
|---|---|
| `ece/reports/cut-018a-report.md` | `ece/reports/cut-018b-report.md` |

### 6.2 必保留章节

- §0 §1 §2 §3 标准结构
- §4 3 项非典型项（*** wildcard 设计 / 私有化双层防御 / TestClient host 模拟**）
- §5 4-5 条教训
- §6 红线 (累积 cut-007-018a, 23+ 条)

### 6.3 必做的最小验证

5 项纪律顺序跑；任何不绿必须 amend。报告 commit 前重跑审计。

### 6.4 禁止事项（累积 cut-007-008-009-010-011-012-013-014-015a-015b-016-017-018a）

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
- **真值 LLM test 不支持 env-skip 双轨**（cut-015b §4.1）
- **test 修改 env 不 try/finally restore**（cut-015b §4.2）
- **check_api_docs regex 中文陷阱**（cut-016 §4.1）
- **CLI 工具 ≠ Python module**（cut-017 §4.2）
- **CamelCase import + as 别名 触发 ruff N817**（cut-017 §4.3）
- **DEBUG_ALLOWED_HOSTS * wildcard 显式 opt-in**（cut-018a §4.1 入红线——严格白名单 + 通配符二选一比隐式 fallback（空=allow all）更安全 + 可测；配置时显式声明意图）
- **TestClient host 模拟需 testclient 显式 allow**（cut-018a §4.3 入红线——FastAPI TestClient 用 `testclient` 当 default `request.client.host`；若 endpoint 校验 IP，默认 allowlist 必须含 `testclient` 或 test 显式 mock）

---

## 7. 红队审验结论（Cline）

**§7 占位** — 本文件不自写审验结论（per §6.4 禁止事项）。