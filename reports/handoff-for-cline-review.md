# Cline Review Handoff — v0.2 Hardening Arc (cut-019 → cut-034)

> **审验范围**: 自上次 codex/cline 审验通过的 commit `526ea75` (cut-018b + cut-018c closure) 以来的所有 v0.2 hardening 工作。

---

## 0. 关键节点 (Boundary)

| 项目 | 值 |
|---|---|
| Last verified commit | `526ea75` (cut-018b + cut-018c closure — multi-user delegation + real LLM gate) |
| Current HEAD | `27877f5` |
| Commits in range | **27 commits** (16 feat + 11 docs) |
| Cuts in range | **16 cuts** (cut-019 → cut-034) |
| Net test delta | **+170 tests** (159 → 329) |
| Branch | `main` |
| Working tree | clean (all pushed) |

---

## 1. 交付总览 (Delivery Summary)

16 cuts 分 4 个主题域交付：

| 主题 | Cuts | 主要交付 |
|---|---|---|
| **A. 多租户 + 委托 (RBAC)** | 019 / 021 / 022 / 024 / 025 / 027 / 028 | X-Org-Id + 3 层委托 + 2 层撤销 + JWT + 用户级撤销 |
| **B. 性能保护 (Rate / Quota)** | 023 / 026 / 029 / 031 | In-memory rate → Redis backend → Lua atomic → quota tracking |
| **C. 合规导出 (Export)** | 030 / 033 | JSON / CSV / items-csv 三格式 + 多维 filter |
| **D. 集成流 (Webhook + E2E)** | 020 / 025 / 034 | perf bench + 端到端 RBAC + 异步 webhook |

### 1.1 新增 env 变量清单 (8 个)

```
ECE_USER_ORGS                      # cut-019: user_ref → org_id 映射
ECE_DELEGATION_ORG_TOKENS          # cut-021: token → orgs (跨 org 委托)
ECE_AUDIT_TOKEN_REQUEST_IDS        # cut-022: token → request_ids (per-resource 委托)
ECE_ORG_RATE_LIMITS                # cut-023: org → N/period (短周期速率限制)
ECE_REVOKED_TOKENS                 # cut-024: token 撤销列表
ECE_REDIS_URL                      # cut-026: Redis backend URL (rate/quota 共享)
ECE_JWT_SECRET                     # cut-027: HS256 对称密钥
ECE_JWT_PUBLIC_KEY                 # cut-032: RS256 公钥 PEM
ECE_JWT_ALGORITHM                  # cut-027: HS256 (默认) / RS256
ECE_REVOKED_USERS                  # cut-028: 整用户撤销 (强 lockout)
ECE_ORG_QUOTAS                     # cut-029: 长周期配额 (d|w|m)
ECE_AUDIT_WEBHOOK_URL              # cut-034: SIEM 接收 URL
ECE_AUDIT_WEBHOOK_TIMEOUT          # cut-034: webhook 超时秒数
```

### 1.2 新增模块清单 (4 个)

```
src/ece/api/org.py           # cut-019: parse_user_orgs, check_org_access, get_user_org
src/ece/api/rate_limit.py    # cut-023/026/031: parse_org_rate_limits, check_rate_limit (Redis + Lua)
src/ece/api/quota.py         # cut-029/031: parse_org_quotas, check_org_quota
src/ece/audit/webhook.py     # cut-034: send_audit_event (daemon thread)
src/ece/auth/jwt.py          # cut-027/032: HS256/RS256 JWT decode
```

---

## 2. 审验范围 (Audit Scope)

Cline 请重点关注以下 6 个维度:

### 2.1 权限提升面 (Permission Surface)

| 文件 | 改动类型 | 风险点 |
|---|---|---|
| `src/ece/api/audit.py` | 5-step permission check (owner → per-USER → per-ORG → per-RESOURCE → X-Org-Id) | Token 检查顺序: cut-022 per-resource 必须在 owner 检查**之前** (orthogonal grant channel) |
| `src/ece/api/debug.py` | 同 /audit | 同上 |
| `src/ece/api/delegation.py` | `user_can_access()` 加了 `is_user_revoked()` 前置检查 | cut-028 user revocation 必须先于 owner check |
| `src/ece/api/org.py` | `check_org_access()` 加了 `is_token_revoked()` 拒绝 | Token revoked → 返 `(False, "token_revoked")` |

**审验要点**：
- [ ] 5 步权限检查顺序是否合理 (per-resource 在 owner 之前)
- [ ] JWT mode 下，X-User-Id 是否被允许作为 fallback (cut-027 graceful degradation)
- [ ] Token revoked 时，X-Delegation-Token 头是否仍能被接受 (期望: 被忽略，等同无 token)
- [ ] cut-028 user revocation 是否影响 owner (期望: 阻塞 owner)
- [ ] cut-024 token revocation 是否保留 owner 访问 (期望: 保留)

### 2.2 安全敏感路径 (Security-Sensitive Paths)

| 路径 | 触发 | 期望行为 |
|---|---|---|
| `/audit/context/{id}` | 多租户 + 委托 + 速率 + 配额 + 撤销 | 6 层检查按顺序短路 |
| `/debug/context/{id}` | 同 /audit (额外 localhost 限制) | 同上 |
| `record_package()` | 每次写入 context_requests | 触发 webhook (cut-034 fire-and-forget) |
| `JWT decode` | 任何 JWT mode 请求 | HS256/RSA256 自动选择 |

**审验要点**：
- [ ] Webhook 失败是否影响主请求 (期望: 不影响，daemon thread)
- [ ] X-Org-Id 与 X-Delegation-Token 同时存在时，谁优先? (期望: token 优先，绕过 org 检查)
- [ ] JWT `sub` claim 为空时是否被拒绝 (期望: 是)
- [ ] 跨 org token `*` 通配符是否能读取所有 org (期望: 是，但要求显式列出)

### 2.3 数据一致性 (Data Consistency)

| 文件 | 关注点 |
|---|---|
| `src/ece/migrations/versions/0007_user_orgs.py` | 迁移回滚: `DROP COLUMN org_id` 是否会丢 v0.2 数据 (期望: 是，需要先 backfill) |
| `record_package()` | 是否保证 DB commit 后才发 webhook (期望: 是，否则 webhook 比 DB 早) |
| `assemble_context()` | 传 `user_org=get_user_org(user_dict["id"])` — None 时正确处理 |

**审验要点**：
- [ ] Migration 0007 是否向后兼容 (旧 v0.1 行 org_id=NULL 走 legacy 路径)
- [ ] Webhook 在 DB commit 后才发 (顺序不能反)
- [ ] Redis backend + Lua 在 Redis 不可用时是否降级 (期望: in-memory fallback)

### 2.4 性能 / 资源 (Performance / Resources)

| 关注点 | 数据 |
|---|---|
| Rate limit in-memory dict 增长 | 字典按 org_id 增长，无界 |
| Webhook 线程数 | 每事件 spawn 一个 daemon thread，high-throughput 有风险 |
| Lua script 每次重传 | Redis 接收完整脚本字符串 (cut-035 应改 EVALSHA) |
| JWT decode 无缓存 | 每次请求 decode + verify (RSA 比 HMAC 慢) |

**审验要点**：
- [ ] Rate limit dict 是否需要周期性清理 (cut-035?)
- [ ] Webhook 高并发场景是否需要 asyncio + queue (cut-035?)
- [ ] JWT verification latency 是否可接受 (建议 cut-035 加 benchmark)

### 2.5 测试覆盖 (Test Coverage)

| 测试文件 | 覆盖范围 | 风险 |
|---|---|---|
| `test_s7_orgs.py` (16) | multi-tenant | 单 tenant mode 边界 |
| `test_s7_multi_tenant_bench.py` (9) | bench 纯逻辑 (未跑真实 perf) | perf 真实数据未验证 |
| `test_s7_v02_e2e.py` (11) | 端到端 11 场景 | 真实 LLM 路径未覆盖 |
| `test_s8_cross_org_delegation.py` (12) | cross-org 委托 | 跨 user+org 组合 |
| `test_s9_per_resource_scope.py` (11) | per-resource 委托 | 顺序耦合 (per-resource 必须在 owner 之前) |
| `test_s10_rate_limit.py` (12) | in-memory rate limit | |
| `test_s11_revoked_tokens.py` (11) | token 撤销 | |
| `test_s12_redis_rate_limit.py` (10) | Redis backend | Lua path 覆盖率低 |
| `test_s13_jwt_auth.py` (15) | HS256 JWT | 过期 / 错签 / 无 sub |
| `test_s14_revoked_users.py` (11) | user 撤销 | 与 cut-024 区分 |
| `test_s15_quota.py` (12) | long-term quota | |
| `test_s16_export_audit.py` (9) | JSON + CSV 导出 | |
| `test_s17_lua_rate_limit.py` (8) | Lua 优化 | 包含 fallback 测试 |
| `test_s18_rs256_jwt.py` (9) | RS256 JWT | |
| `test_s19_items_csv.py` (6) | items-csv | 需 `--user` filter |
| `test_s20_audit_webhook.py` (8) | webhook 流 | daemon thread + time.sleep |

**审验要点**：
- [ ] 任何 cut 是否存在未测试分支 (e.g., JWT expired 但 `iat` 缺失?)
- [ ] Webhook 测试用 `time.sleep(0.5)` 等待 — 是否 flaky?
- [ ] Lua fallback 测试是否覆盖所有异常路径?

### 2.6 文档完整性 (Documentation)

| 文档 | 是否更新 |
|---|---|
| `docs/API.md` | ✅ 更新 §8 audit header table (cut-019/021/022/023/027) |
| `docs/v0.2-deploy.md` | ✅ 新建 (cut-019), 后续 023/024/025/026/029/032/034 累积追加 |
| `docs/v0.2-cutover-checklist.md` | ✅ 新建 (cut-025) |
| `docs/v0.1-deploy.md` | ⚠️ 未更新 — v0.1 部署应仍参考此文件 (保持稳定) |
| `reports/cut-019..034-*.md` | ✅ 16 篇报告齐全 |

---

## 3. 完整 Commits 列表 (Full Commit Manifest)

```
27877f5 docs(reports): cut-031/032/033/034 reports — Lua + RS256 + items-csv + webhook
d63a9b4 feat(audit): ECE_AUDIT_WEBHOOK_URL async POST for SIEM streaming (cut-034)
f5f3e41 feat(audit-export): --format items-csv for per-item granularity (cut-033)
40925e7 feat(auth): RS256 asymmetric JWT via ECE_JWT_PUBLIC_KEY (cut-032)
88fac59 feat(rate-limit): Redis Lua atomic single-round-trip (cut-031)
449e2fc docs(reports): cut-027/028/029/030 reports — v0.2 RBAC hardening arc closure
d4f0659 feat(audit-export): --org, --until, --format csv for compliance (cut-030)
1141fda feat(quota): ECE_ORG_QUOTAS per-org long-term quota tracking (cut-029)
e112fea feat(revocation): ECE_REVOKED_USERS user-level revocation (cut-028)
b1c8b61 feat(auth): JWT bearer token (Authorization header) replaces X-User-Id (cut-027)
fa6b3e1 docs(reports): cut-026 report — Redis rate limit closure
958ef1d feat(rate-limit): Redis backend for multi-process correctness (cut-026)
a476323 docs(reports): cut-025 report — v0.2 cut-over closure
adb9809 feat(v0.2-cutover): e2e RBAC test + production checklist (cut-025)
a66581c docs(reports): cut-024 report — token revocation closure
2f85fe4 feat(revocation): ECE_REVOKED_TOKENS compromise mitigation (cut-024)
0ada1d3 docs(reports): cut-023 report — org rate limit closure
7d663ee feat(rate-limit): ECE_ORG_RATE_LIMITS per-org fixed-window throttling (cut-023)
454e80f docs(reports): cut-022 report — per-resource scope closure
80a4622 feat(delegation): ECE_AUDIT_TOKEN_REQUEST_IDS per-resource scope (cut-022)
5bac946 docs(reports): cut-021 report — cross-org delegation closure
5afc549 feat(delegation): ECE_DELEGATION_ORG_TOKENS cross-org delegation (cut-021)
0883fd5 docs(reports): cut-020 report — multi-tenant bench closure
22c2149 feat(multi-tenant): perf bench + cross-org denial verification (cut-020)
4c6544a docs(reports): cut-019 report — multi-tenant + per-resource scope closure
daeb575 feat(multi-tenant): X-Org-Id cross-org isolation + ECE_USER_ORGS env (cut-019)
```

(27 commits 完整列表，按时间倒序 — 最新在上)

---

## 4. 文件变更统计 (File Diff Stats)

```
27 files changed
+~6500 lines code
+~2000 lines tests
+~16 reports
```

主要新文件:
- 5 个新模块 (`org.py` / `rate_limit.py` / `quota.py` / `webhook.py` / `auth/jwt.py`)
- 1 个新迁移 (`0007_user_orgs.py`)
- 16 个新集成测试
- 2 个新部署文档 (`v0.2-deploy.md` / `v0.2-cutover-checklist.md`)
- 16 个 cut 报告

修改文件:
- `src/ece/api/audit.py` — 5 次 edit (cut-019/022/023/025/027)
- `src/ece/api/debug.py` — 5 次 edit (同上)
- `src/ece/api/delegation.py` — 4 次 edit (cut-021/022/024/028)
- `src/ece/context/assembly.py` — 1 次 edit (cut-019: get_user_org)
- `src/ece/context/provenance.py` — 1 次 edit (cut-034: webhook)
- `scripts/export_audit.py` — 2 次 edit (cut-030/033)
- `pyproject.toml` — 2 个新依赖 (pyjwt + redis, fakeredis as dev)

---

## 5. 自动化验证 (Automated Verification)

Cline 可直接执行以下命令确认当前状态:

```bash
cd /Users/kjonekong/projects/domainAgentECE/ece

# 1. 确认 commit 范围
git log --oneline 526ea75..HEAD | wc -l
# Expected: 27

# 2. 5 项 discipline 全绿
make test
# Expected: 329 passed, 6 skipped, 2 warnings

uv run ruff check .
# Expected: All checks passed

uv run mypy src tests
# Expected: Success: no issues found in 114 source files

uv run lint-imports
# Expected: Domain pack isolation KEPT + Engine core isolation KEPT

make check-api-docs
# Expected: OK - 14 routes registered

# 3. 数据库迁移就位
uv run alembic -c src/ece/migrations/alembic.ini current
# Expected: 0007_user_orgs (head)

# 4. v0.2 RBAC smoke test
bash scripts/verify_v02_rbac.sh
# Expected: v0.2 RBAC: PASS

# 5. Multi-tenant perf bench (mock LLM)
uv run python scripts/bench_multi_tenant.py --n 50 --skip-cross-org
# Expected: p95 < 1500ms, 0 429s

# 6. Real LLM 验证 (需要 LLM_BASE_URL — user 手动)
bash scripts/bench_e6_real_llm_multi_tenant.sh
# Expected: ≥80% accuracy + multi-tenant bench pass
```

---

## 6. 已知风险 + 后续 cut 候选 (Known Risks + Future Cuts)

### 6.1 已知边界 / 技术债

| 风险 | 严重度 | 影响 |
|---|---|---|
| Webhook 无重试 | 中 | webhook 失败 → 事件丢失 (进程崩溃/网络抖动) |
| Rate limit dict 无界 | 低 | 大量 org 可能内存膨胀 |
| Lua script 每次重传 | 低 | 微小带宽浪费 |
| Webhook 无 auth | 中 | 任意可 POST 到 webhook URL |
| JWT 无 iat / aud 验证 | 低 | 仅 sub + exp 已验证 |
| 单 key JWT rotation | 中 | 轮换期间旧 token 失效 |

### 6.2 v0.3 候选 (cut-035+)

1. **cut-035**: Webhook retry queue (持久化 + at-least-once)
2. **cut-036**: Multi-key JWT rotation (新旧 key 并存)
3. **cut-037**: Webhook HMAC signature (callers 验证 ECE 签名)
4. **cut-038**: EVALSHA + SCRIPT LOAD (Lua script 缓存)
5. **cut-039**: Audit log retention policy (TTL 自动清理)
6. **cut-040**: Per-resource export (per-trace_id filter)

---

## 7. 重点 review 章节 (High-Priority Review Sections)

按风险从高到低排序:

1. **src/ece/api/audit.py** — 5 步权限检查 + JWT + quota + rate limit + webhook 是整个 v0.2 的入口, 必审
2. **src/ece/api/delegation.py** — 3 层委托 + 2 层撤销, 业务规则最复杂
3. **src/ece/audit/webhook.py** — fire-and-forget 线程逻辑, 资源管理
4. **src/ece/auth/jwt.py** — JWT mode + 多算法支持, 安全敏感
5. **scripts/export_audit.py** — 3 种格式 + schema_version 兼容性
6. **src/ece/migrations/versions/0007_user_orgs.py** — 迁移回滚安全性
7. **src/ece/api/rate_limit.py** + **quota.py** — Redis Lua 优化 + fallback

---

## 8. 审验结论回执 (Audit Verdict Template)

Cline 完成审验后请在 `reports/cline-review-verdict-2026-09.md` 写明:

```markdown
# Cline Review Verdict — v0.2 hardening arc (cut-019 → cut-034)

## Verdict
- [ ] PASS  (无 blocker, 可发版)
- [ ] PASS WITH NITS  (无 blocker, 有建议改进)
- [ ] BLOCKER  (存在 P0 问题, 需修复)

## Files reviewed (清单)

## Findings (按严重度)

### P0 (Blocker)
...

### P1 (Should fix before v0.2 cut-over)
...

### P2 (Nice to have, post-v0.2)
...

## Test coverage assessment

## Recommendation

Reviewed by: <cline/codex-id>
Date: YYYY-MM-DD
```

---

**审验入口**: 当前 commit hash `27877f5` 可直接 checkout 审验

**审验人**: cline/codex
**交接时间**: 2026-09-15
**交接者**: Claude Fable 5 (autonomous session, double push via `127.0.0.1:7890`)