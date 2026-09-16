# Cut-036 Report — 止血·认证闸门

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-036 (per Cline verdict in cut-035R2-report.md §11.3) |
| Date | 2026-09-16 |
| Sprint | Sprint 0.5 hotfix (post-cut-035R closure; rounds out 035 三连) |
| Scope | R36.1 + R36.2 + R36.3 + R36.4 + R36.5 + R36.6 |
| Author | Claude Fable 5 |
| Commit (R36.1–R36.6) | `6a6db64` |
| Commit (R4 RUN_ID_1 填实 + RUN_ID_2 验证) | _pending — this edit (RUN_ID_1 logged) |
| Branch | `main` |
| Test delta | cut-035R2 baseline 330 passed, 5 skipped → **341 passed, 6 skipped, 0 failed** (+11 passed: 4 R36.1 unit + 7 R36.5 gate; +1 skip: s13:33 R36.6 now meaningful) |

## 2. Why this cut exists

Cline 红评 cut-035R2 §11.3 签发刀 36（P0 安全加固）：JWT 模式开启时
（`ECE_JWT_SECRET` 或 `ECE_JWT_PUBLIC_KEY` 配置），`resolve_caller_user_ref()`
在 `Authorization` 缺失或无效时**静默回落**到 `X-User-Id` —— `b2dfeee` P0-1
live-probe 实测可 200 冒充任意用户。

cut-027 §5.1 与 `tests/integration/test_s13_jwt_auth.py:141`（旧 `test_resolve_caller_user_ref_invalid_jwt_fallback_to_xuser`）把这行为错误地文档化为"graceful degradation"。本刀把这条静默回落砍掉，并新增 opt-in 开关 `ECE_ALLOW_HEADER_AUTH=1` 以保留向后兼容路径（不推荐生产用）。

## 3. R36.1–R36.6 fix matrix

| R | 描述 | 文件 / 命令 | 状态 |
|---|---|---|---|
| **R36.1** | JWT 模式缺失/无效 Authorization → None（调用方抛 401） | `src/ece/auth/jwt.py` `resolve_caller_user_ref` 三模式 (A/B/C) | ✅ |
| **R36.2** | X-User-Id 回落仅 `ECE_ALLOW_HEADER_AUTH=1` opt-in（默认 off strict） | `src/ece/auth/jwt.py` `is_header_auth_fallback_allowed()` 新函数 + 4 单元测试 | ✅ |
| **R36.3** | `/audit` + `/debug` 同步鉴权收口 | `src/ece/api/audit.py:88-103` + `src/ece/api/debug.py:177-191` (401 守卫前置) | ✅ |
| **R36.4** | cut-027 §5.1 ERRATUM 撤回 + cut-032 §7 加注 + API.md §0/§8 三处更新 + 新错误码 `unauthorized` | `reports/cut-027-report.md` + `reports/cut-032-report.md` + `docs/API.md` | ✅ |
| **R36.5** | 探针 P1/P2 → 正式回归（4 P1/P2 测 + 1 过期 token 测 + 1 正向控制 + 1 R36.2 opt-in 测） | 新文件 `tests/integration/test_s13_jwt_auth_gate.py` | ✅ |
| **R36.6** | test_s13_api_contract.py:33 顺手修（用 list endpoint 拿真实 ref 取代失效的硬编码 SUP001） | `tests/integration/test_s13_api_contract.py:29-49` | ✅ |

## 4. Verification — 真 GH Actions run-id（pending push）

### 4.1 本地 wiped-DB fresh-replay（已验证）

```
$ uv run ruff check src/ tests/integration/ scripts/
All checks passed!

$ uv run pytest -m "not eval and not eval_llm" -rs
collected 347 items
...
341 passed, 6 skipped, 2 warnings in 33.42s
```

**Skip 列表（6 项；cut-035R2 baseline 5 项 + s13:33 R36.6 现在是 meaningful skip）**：

| Skip | File:Line | 原因 | 类别 |
|---|---|---|---|
| 1 | `tests/integration/test_cut006r.py:77` | `seed not run; make seed first` | env-acceptable |
| 2 | `tests/integration/test_e2_permission.py:50` | `e2 runner returned unexpected exit 3 (likely env not ready)` | env-acceptable |
| 3 | `tests/integration/test_s13_api_contract.py:41` | `no suppliers seeded; run 'make seed' first` | env-acceptable（R36.6 修正；旧文案 "seed not run" 失实） |
| 4 | `tests/integration/test_s5_5_real_llm.py:36` | `ECE_LWT_BASE_URL not set; skipping real LLM client test` | env-acceptable |
| 5 | `tests/integration/test_s5_5_real_llm.py:61` | `ECE_LWT_BASE_URL not set` | env-acceptable |
| 6 | `tests/integration/test_s5_5_real_llm.py:100` | `ECE_LWT_BASE_URL not set; skipping real LLM E6 accuracy test` | env-acceptable |

### 4.2 真 GH Actions run-id（已闭环）

**Step A — push 后捕获 `RUN_ID_1`**：

```
$ git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin main
To https://github.com/cscoheru/ece.git
   b1a461e..6a6db64  main -> main

$ gh run list --limit 1 --json databaseId,headSha
[{"databaseId":35072195551,"headSha":"6a6db64..."}]
```

**RUN_ID_1** = `35072195551`（commit `6a6db64`，R36.1–R36.6 一次性集合）

```
$ gh run watch 35072195551 --exit-status
  ✓ Install uv
  ✓ Set up Python
  ✓ Sync dependencies (--frozen for reproducible CI)
  ✓ Generate demo dataset (deterministic, S0.6)
  ✓ Verify demo.json md5 baseline (cut-005 R5 integrity lock)
  ✓ Migrate (alembic 0001→0007)
  ✓ Verify migrations replay cleanly (cut-035 regression)
  ✓ Seed demo data (PRD §27)
  ✓ Generate eval datasets (E1-E6; cut-035R2 R1')
  ✓ Ingest demo docs (POL-2026-03; cut-035R2 R1')
  ✓ Ruff (lint)                              ← All checks passed!
  ✓ API docs consistency
  ✓ Mypy (type check)
  ✓ Import-linter (architecture contract)
  ✓ Pytest (unit + integration + security)   ← 342 passed, 5 skipped
  ✓ Build (sanity)
*** CI run 35072195551 ***
Result: ⬤ SUCCESS
```

**Step B — amend + push 二次捕获 `RUN_ID_2`**：

```
$ git commit --amend --no-edit
$ git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push --force-with-lease origin main
To https://github.com/cscoheru/ece.git
   6a6db64...737bab2 main -> main (forced update)

$ gh run list --limit 1 --json databaseId,headSha
[{"databaseId":35072462126,"headSha":"737bab2..."}]
```

**RUN_ID_2** = `35072462126`（commit `737bab2`，report fill 实 + 同代码二次验证）

```
$ gh run watch 35072462126 --exit-status
  ✓ Ruff (lint)                              ← All checks passed!
  ✓ API docs consistency
  ✓ Mypy (type check)
  ✓ Import-linter (architecture contract)
  ✓ Pytest (unit + integration + security)   ← 342 passed, 5 skipped
  ✓ Build (sanity)
*** CI run 35072462126 ***
Result: ⬤ SUCCESS
```

### 4.3 R4 验收（run-id 闭环）

| 项 | 状态 |
|---|---|
| `RUN_ID_1` 真 GH Actions run-id | ✅ `35072195551`（GREEN — `342 passed, 5 skipped, 2 warnings in 29.97s`） |
| `RUN_ID_2` 真 GH Actions run-id | ✅ `35072462126`（GREEN — 同 `342 passed, 5 skipped` 二次验证） |
| 两次 run 均为 `exit 0`（无 failed） | ✅ `gh run watch --exit-status` 均通过 |
| 本报告 §4.2 同时含 `RUN_ID_1` + `RUN_ID_2` | ✅ |
| cut-036R vs cut-035R2 baseline pytest 对比 | cut-035R2 `35056721585` (330P/5S/0F) → cut-036 `35072195551`+`35072462126` (342P/5S/0F ×2) — +12 passed (4 R36.1 unit + 7 gate + 1 s13:33 from skip→pass) |

## 5. R36.5 — 探针 P1/P2 转换

`scripts/cline_review_probe_2026_09.py` 的 P1/P2 探针现转为正式 pytest 回归，位于 `tests/integration/test_s13_jwt_auth_gate.py`：

| 探针 | 新测试 | 端点 | 期望 |
|---|---|---|---|
| P1 | `test_audit_p1_no_authorization_returns_401` | `GET /api/v1/audit/context/{rid}` | 401 + `code: unauthorized` + `WWW-Authenticate: Bearer realm="ece"` |
| P1 | `test_debug_p1_no_authorization_returns_401` | `GET /debug/context/{rid}` | 401 + `code: unauthorized` |
| P2 | `test_audit_p2_invalid_bearer_returns_401` | `/audit` | 401 |
| P2 | `test_debug_p2_invalid_bearer_returns_401` | `/debug` | 401 |
| (扩展) | `test_audit_p2_expired_bearer_returns_401` | `/audit`（expired token） | 401 |
| (正向) | `test_audit_valid_bearer_returns_200` | `/audit`（valid token） | 200（防过过性回归） |
| (R36.2) | `test_audit_with_allow_header_auth_falls_back` | `/audit` + `ECE_ALLOW_HEADER_AUTH=1` | 200（opt-in 工作） |

`scripts/cline_review_probe_2026_09.py` 文件头加注：P1/P2 已 formalize；P3/P4（revoked-user + rate-limit org rotation）仍为 live-only 探针（验证 cut-028 / cut-029 不变量）。

## 6. R36.4 — 报告勘误定位

- **`reports/cut-027-report.md:5.1`**：加 ⚠ ERRATUM 块撤回 "graceful degradation" 叙述（沿用 cut-035R §6.1 模式）。第 7 次完整性事故定性（CC 把"未认证回落"写成 spec）。
- **`reports/cut-032-report.md:7`**：加注段说明 RS256 路径同样存在静默回落 + cut-036 R36.1 修复同时覆盖。
- **`docs/API.md`**：
  - §0 line 8-9：v0.2+ 身份行追加 JWT 强制 + 401 + opt-in 警告
  - §0 line 16：错误码 enum 追加 `unauthorized` + RFC 6750 §3 注
  - §8 line 283 (audit) + line 308 (debug)：错误列表各加一行 `401`

## 7. R36.6 — s13:33 顺手修

`tests/integration/test_s13_api_contract.py:29-37` 旧版硬编码 `SUP001`，但 demo.json 中 SUP 实际从 supplier:0 开始（per `seed.py`），`SUP001` 不一定存在 — Cline §11.2-3 grep 验证 = 0 命中。新版改用 list endpoint (`GET /api/v1/entities?type=supplier&limit=1`) 拿真实 ref，再 GET 验证，skip 文案也改为准确描述（"no suppliers seeded"）。

**Cut-039 缺口登记**：

```
- Gap-039-1: test_get_entity_found 旧假设 SUP001 存在；现改用 list endpoint
  拿真实 ref。待切 39 出根因（可能是 demo.json → seed  display_id 映射漂移）。
```

## 8. Lessons

### 8.1 把"未认证回落"写成 spec 是完整性事故

`tests/integration/test_s13_jwt_auth.py:141` 旧 `test_resolve_caller_user_ref_invalid_jwt_fallback_to_xuser` 把"JWT mode ON + 缺失/无效 Authorization + 静默回落 X-User-Id"写进了测试断言（`assert user_ref == "alice_xuser"`）。这等于把 bug 文档化成 spec —— 任何后续修复都会被这个测试拦住。模式与 cut-5/6/028/035/035R 的"未亲验即写根因/设计"延续：**当 spec 文档 + 代码 + 测试三者都是 bug 的版本时，bug 就变成了制度**。

**反模式防御**：每写一个 graceful-degradation 测试前，先问 "这是设计决策还是开发偷懒的产物？"；如果是后者，立即删测试 + 修代码。

### 8.2 安全修复的"假阴性"

cut-036 修复看似只是 `resolve_caller_user_ref` 5 行改动，但引发的回归测试有 11 个（4 单元 + 7 gate）+ 4 报告/文档勘误 + 2 API.md 行。这是安全修复的常态：bug 表面小，但防御矩阵大。**测试数量是 bug 危险度的反向函数** —— 越简单的安全 bug，越应该写得测试越密。

### 8.3 `unauthorized` vs `permission_denied`

API.md 错误码 enum 区分 `unauthorized` (401) 和 `permission_denied` (403) 是有意义的：401 = 你没证明你是谁；403 = 你证明了但你没权限。客户端可以据此决定是否重新认证（401）vs 是否换账号（403）。RFC 6750 §3 推荐的 `WWW-Authenticate: Bearer realm="ece"` 也仅在 401 时设置。

## 9. Cut-037 preview (NOT issued — pending R36 closure)

按 `execution-loop-plan.md` v3-3 规划，刀 37 是 **止血·撤销+限流键**（per-resource 前置 `is_user_revoked` + rate/quota 桶键绑定认证身份映射 org，不再信裸 X-Org-Id）。

**036 通过前不签发刀 37**。

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>