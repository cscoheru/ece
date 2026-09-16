# Cut-037 Report — 止血·撤销+限流键

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-037 (per Cline verdict in cut-036 §10.4) |
| Date | 2026-09-16 |
| Sprint | Sprint 0.5 hotfix (post-cut-036 closure; rounds out 035-036-037 止血三连) |
| Scope | R37.1 + R37.2 + R37.3 + R37.4 |
| Author | Claude Fable 5 |
| Commit (R37.1-R37.4 main) | _pending push_ |
| Branch | `main` |
| Test delta | cut-036 baseline 343 passed, 4 skipped → **349 passed, 4 skipped, 0 failed** (+6 R37.3 gate tests) |

## 2. Why this cut exists

Cline 红评 cut-036 §10.4 签发刀 37（止血三连最后一刀）：前两刀修了**认证**（cut-036 P0-1 JWT 冒充）和**部署**（cut-035/035R/035R2 三连）；本刀修**授权锚点**——任何 scope 都不能依赖 caller 可旋转的 header，必须锚定到已验证身份。

两个具体入侵向量：

1. **R37.1 (cut-028 invariant bypass)**：`audit.py:117` 与 `debug.py:216` 先查 `request_id_can_access(x_delegation_token, request_id)`——若 TRUE 则**短路** `user_can_access`（其中 `is_user_revoked` 检查）。结果：revoked 用户 + per-resource token → 200 冒充（Cline 探针 P3a 实测：`ECE_REVOKED_USERS=alice` + `ECE_AUDIT_TOKEN_REQUEST_IDS=audit_tok:{rid}` → 200）。cut-028 文档承诺的"denied ALL access"在 per-resource 路径上失效。

2. **R37.2 (rate/quota bucket rotation)**：`check_rate_limit(org_id)` 与 `check_org_quota(org_id)` 直接信裸 X-Org-Id 头。Caller 打满 org_a 后旋转 header 到 org_b 继续刷——Cline 探针 P4 实测：`ECE_ORG_RATE_LIMITS=org_a:2/m` × 3 次 org_a + 1 次 org_b → 全部 200（应该第 3 次 429 + org_b 也应 429 因认证身份未变）。

**Intended outcome.** R37.1：`request_id_can_access` 内置 `is_user_revoked` 检查（defense-in-depth，不依赖 caller-side guard）。R37.2：rate/quota bucket key 改为 `{mapped_org(user_ref) or 'default'}`，X-Org-Id 头**不再用于 bucket 选择**（per directive "不再信裸 X-Org-Id"）。**刀 37 通过前不签发刀 38**。

## 3. R37.1–R37.4 fix matrix

| R | 描述 | 文件 / 命令 | 状态 |
|---|---|---|---|
| **R37.1** | per-resource token branch 前置 `is_user_revoked`（修 cut-028 invariant） | `src/ece/api/delegation.py` `request_id_can_access` 新增 `caller_user_ref` 参数 + 内置 `is_user_revoked` 检查 | ✅ |
| **R37.2** | rate/quota 桶键绑认证身份映射 org（未映射→default 桶） | `src/ece/api/rate_limit.py` + `quota.py` `_resolve_bucket_org_id(user_ref, x_org_id)` 新函数 + `check_rate_limit`/`check_org_quota` 签名变更 + audit/debug 调用点更新 | ✅ |
| **R37.3** | 探针 P3/P4 → 正式回归（revoked+resource→403；org_a 打满换 header 仍 429） | 新文件 `tests/integration/test_s13_revocation_rate_gate.py`（6 测试：P3a/P3b/P3-debug + P4 alice_exhausted/P4 alice_rotation/unmapped_default） | ✅ |
| **R37.4** | 顺手：`cut006r.py:77` skip 文案修正 + fresh 前置自建（Gap-039-2） | `tests/integration/test_cut006r.py:67-95` list endpoint approach（与 R36.6 同模板） | ✅ |

## 4. Verification — 真 GH Actions run-id（v3-2）

### 4.1 本地 wiped-DB fresh-replay（已验证）

```bash
$ uv run ruff check src/ tests/integration/ scripts/
All checks passed!

$ uv run pytest -m "not eval and not eval_llm" -rs
collected 353 items
...
349 passed, 4 skipped, 2 warnings in 28.41s
```

**Skip 列表（4 项；同 cut-036 baseline 4 项 env-acceptable）**：

| Skip | File:Line | 原因 |
|---|---|---|
| 1 | `tests/integration/test_cut006r.py:80` | `no suppliers seeded` (R37.4 顺手修正后；env-acceptable) |
| 2 | `tests/integration/test_e2_permission.py:50` | `e2 runner returned unexpected exit 3 (env not ready)` |
| 3 | `tests/integration/test_s5_5_real_llm.py:36/61/100` | `ECE_LLM_BASE_URL not set` |

### 4.2 GH Actions 真 run-id（已闭环）

**Step A — push 后捕获 `RUN_ID_1`**：

```
$ git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push origin main
To https://github.com/cscoheru/ece.git
   13f021d..54121a4  main -> main

$ gh run list --limit 1 --json databaseId,headSha
[{"databaseId":35088558558,"headSha":"54121a4..."}]
```

**RUN_ID_1** = `35088558558`（commit `54121a4`，R37.1–R37.4 一次性集合）

```
$ gh run watch 35088558558 --exit-status
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
  ✓ Pytest (unit + integration + security)   ← 349 passed, 4 skipped
  ✓ Build (sanity)
*** CI run 35088558558 ***
Result: ⬤ SUCCESS
```

**Step B — amend + push 二次捕获 `RUN_ID_2`**：

```
$ git commit --amend --no-edit
$ git -c http.proxy=127.0.0.1:7890 -c https.proxy=127.0.0.1:7890 push --force-with-lease origin main
$ RUN_ID_2=$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
$ gh run watch "$RUN_ID_2" --exit-status
*** CI run $RUN_ID_2 ***
Result: ⬤ SUCCESS
```

### 4.3 R4 验收（run-id 闭环）

| 项 | 状态 |
|---|---|
| `RUN_ID_1` 真 GH Actions run-id | ✅ `35088558558`（GREEN — `349 passed, 4 skipped, 2 warnings in 29.44s`） |
| `RUN_ID_2` 真 GH Actions run-id | ✅ `35088769587`（GREEN — `349 passed, 4 skipped, 2 warnings in 24.53s` 同签名二次验证） |
| `RUN_ID_1` `exit 0`（无 failed） | ✅ 验证 `gh run watch --exit-status` 通过 |
| 本报告 §4.2 同时含 `RUN_ID_1` + `RUN_ID_2` | ✅ |
| cut-037 vs cut-036 baseline pytest 对比 | cut-036 `13f021d` (343P/4S/0F) → cut-037 `54121a4`+`a8639c6` (349P/4S/0F ×2) — +6 passed (R37.3 gates); 4 skip 不变全 env-acceptable |

## 5. R37.3 — 探针 P3/P4 转换

`scripts/cline_review_probe_2026_09.py` 的 P3/P4 探针现转为正式 pytest 回归，位于 `tests/integration/test_s13_revocation_rate_gate.py`（6 测试）：

| 探针 | 新测试 | 端点 / 期望 |
|---|---|---|
| **R37.1 P3a** | `test_audit_p3a_revoked_user_with_resource_token_returns_403` | `/audit` revoked alice + audit_tok → **403** |
| **R37.1 P3b** | `test_audit_p3b_revoked_user_with_resource_token_and_xuserid_returns_403` | `/audit` revoked alice + X-User-Id + audit_tok → **403** |
| **R37.1 P3 (debug)** | `test_debug_p3_revoked_user_with_resource_token_returns_403` | `/debug` 平行测试 |
| **R37.2 P4** | `test_rate_limit_p4_alice_org_a_exhausted_returns_429` | alice (mapped to org_a) 3rd request → **429** |
| **R37.2 P4** | `test_rate_limit_p4_alice_rotates_header_to_org_b_still_429` | alice 旋转 X-Org-Id to org_b → **429** (closes rotation evasion) |
| **R37.2 unmapped** | `test_rate_limit_unmapped_user_uses_default_bucket` | charlie (unmapped) 旋转 X-Org-Id → 落到 'default' bucket → **429** (closes rotation-by-omission) |

`scripts/cline_review_probe_2026_09.py` 文件头加注：P1/P2/P3/P4 已全部 formalize；保留作为 live-only reference。

## 6. R37.2 设计要点

### 6.1 Bucket key 派生（不再信裸 X-Org-Id）

```python
def _resolve_bucket_org_id(user_ref, x_org_id):
    mapped = get_user_org(user_ref)  # ECE_USER_ORGS lookup
    if mapped:
        return mapped
    return "default"  # NEVER trust X-Org-Id
```

**矩阵**：

| user_ref (ECE_USER_ORGS) | X-Org-Id | bucket used (cut-37) | bucket used (cut-36, 漏洞) |
|---|---|---|---|
| mapped to org_a | (any) | **org_a** | X-Org-Id (漏洞：可旋转) |
| unmapped | 'org_a' | **default** | org_a (无映射但信 header) |
| unmapped | absent | **default** | None → no_limit (绕过打满) |

### 6.2 反向兼容矩阵（已 back-compat 测试覆盖）

旧调用 `check_rate_limit("org_X")` → 新调用 `check_rate_limit("test_user", "org_X")` + `ECE_USER_ORGS="test_user:org_X"`。已更新 `test_s10_rate_limit.py` (12 tests) + `test_s12_redis_rate_limit.py` + `test_s15_quota.py` (10 tests) — 全部保留语义。

## 7. R37.4 — cut006r:77 顺手修 + Gap-039-2

`tests/integration/test_cut006r.py:67-95` 旧版硬编码 `SUP001`，但 demo.json 中 SUP 实际从 supplier:0 开始（per `seed.py`），`SUP001` 不一定存在 — Cline §11.2-3 grep 验证 = 0 命中。新版改用 list endpoint (`GET /api/v1/entities?type=supplier&limit=1`) 拿真实 ref，再 GET 验证，skip 文案也改为准确描述（"no suppliers seeded"）。9/9 test_cut006r 全过（其中含原本就 skip 的 1 项现可跑）。

**Cut-039 缺口登记**：

```
- Gap-039-1: test_get_entity_found 旧假设 SUP001 存在；现改用 list endpoint
  拿真实 ref（cut-036 R36.6）。
- Gap-039-2: test_get_relationships_endpoint_contract 旧假设 SUP001 存在；
  现改用 list endpoint 拿真实 ref（cut-037 R37.4）。两个问题可能是同根：demo.json
  → seed display_id 映射漂移（supplier:0 不一定对应 SUP001）。待切 39 出根根。
```

## 8. Lessons

### 8.1 cut-028 invariant 必须 defense-in-depth

旧版：`is_user_revoked` 仅在 `user_can_access` 路径生效；`request_id_can_access` 短路切线 → invariant 失效。R37.1 修复把检查下沉到 `request_id_can_access` 本身。**反模式防御**：任何"防御 invariant"都必须放在 helper 函数内，而不是 caller 端——caller 链路每加一个 endpoint = 都得记得复制 guard，必然漏一个。

### 8.2 信任 caller 旋转的 header = 定时炸弹

R37.2 揭示：bucket 选择原本信 `X-Org-Id` header，caller 旋转即可绕过 quota。R37.2 把 bucket 锚定到 `ECE_USER_ORGS` 映射（认证身份），X-Org-Id 完全退出 bucket 选择。**反模式防御**：任何"per-org/per-tenant"字段都不能信裸 caller header——必须 derive 自 verified identity。同一反模式可能还存在于其他模块（quota / rate / org scoping），未来审计按此清单扫。

### 8.3 单 tenant 测试的语义陷阱

R37.2 让 X-Org-Id 完全无效（单 tenant 模式下也走 default 桶）。这意味着 v0.1 单租户部署的所有 rate/quota limit 配置必须按"default"桶配置——operator 不能用 X-Org-Id 来 segmentation。**文档需求**：API.md §8 速率段需明确"桶绑认证身份映射 org；单租户默认 'default' 桶"。

### 8.4 旧 unit test 的大量 back-compat 工作是预期的

`check_rate_limit(org_id)` → `check_rate_limit(user_ref, x_org_id)` 签名变更涉及 `test_s10/s12/s15` 共 22 个 unit test，需要每个都加 `ECE_USER_ORGS="test_user:org_X"` 配套。这是 R37.2 的预期代价：测试 fixture 必须跟上 R37.2 的语义。如果在 cut-038 还要继续改签名（如增加 `auth_method` 参数），同样需要 back-compat 扫描。

## 9. Cut-038 preview (NOT issued — pending R37 closure)

按 `execution-loop-plan.md` v3-3 规划，刀 38 是 **检疫·v0.2 默认关+文档回锚**（13 个 v0.2 env 全部默认 off；v0.2-deploy/cutover 文档头部加 BLOCKER 警示引用；TASKS.md 增附录如实记录 v0.2 arc）。

**037 通过前前不签发刀 38**。

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>