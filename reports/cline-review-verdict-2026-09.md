# Cline Review Verdict — v0.2 hardening arc (cut-019 → cut-034)

## Verdict

- [ ] PASS  (无 blocker, 可发版)
- [ ] PASS WITH NITS  (无 blocker, 有建议改进)
- [x] **BLOCKER  (存在 P0 问题, 需修复)**

审验范围：`526ea75..27877f5`（27 commits，handoff commit `754419b` 为文档本身）。
方法：不采信声明——§5 自动化命令全部亲跑 + 权限链代码逐行 + 4 组对抗探针活体打真服务。

---

## Files reviewed (清单)

- `src/ece/api/audit.py`、`src/ece/api/debug.py` — 5 步权限链 + rate/quota + JWT caller 解析（grep 同构确认 debug 复用同模式）
- `src/ece/auth/jwt.py` — `resolve_caller_user_ref` 回落逻辑
- `src/ece/api/delegation.py` — 3 层委托 + 2 层撤销 + per-resource 通道
- `src/ece/api/org.py` — 多租户 org 检查 + token 撤销
- `src/ece/api/rate_limit.py` — in-memory/Redis/Lua 三后端
- `src/ece/api/quota.py` — 键位模式（与 rate_limit 同构）
- `src/ece/audit/webhook.py` — daemon thread fire-and-forget
- `src/ece/migrations/versions/0001/0005/0006/0007` — 迁移链
- `scripts/verify_v02_rbac.sh`、`scripts/bench_multi_tenant.py` — 验收脚本（亲跑）
- `reports/handoff-for-cline-review.md`、`reports/cut-027-report.md` — 交接与设计声明
- `.github/workflows/ci.yml`、`pyproject.toml`、`uv.lock`（已提交 vs 工作树）

## Findings (按严重度)

### P0 (Blocker)

**P0-1 认证旁路：JWT 模式下 X-User-Id 未认证回落（活体实证 ×2）**

`jwt.py:resolve_caller_user_ref()`：`ECE_JWT_SECRET` 配置后，Authorization 缺失或**验签失败**均静默回落到裸 `X-User-Id` header。探针（真库 + TestClient）：

```
P1 jwt-mode x-user-id impersonation: 200  <-- AUTH BYPASS   # 无 Authorization，自称 alice → 全量 trace
P2 invalid-jwt silent downgrade:    200  <-- AUTH BYPASS    # 垃圾 Bearer + X-User-Id → 同样 200
```

影响面：`/audit/context/*` 与 `/debug/context/*` 全部读路径。cut-027 报告 §5.1 将此写为有意设计（"graceful degradation"）——**披露过，但设计不成立**：hardening arc 的 JWT 一旦可被"去掉 Authorization 头"绕过即为装饰品，冒充任意用户零成本。修复：JWT 模式开启时无效/缺失 Authorization 返回 401；header 认证若需保留必须显式 opt-in（如 `ECE_ALLOW_HEADER_AUTH=1`）且文档标注降级风险。

**P0-2 迁移链不可重放：fresh 库部署必炸 + CI 红 ×3 未披露**

`0001_initial` 被回炉塞入 `0005` 全载荷（`context_requests`/`context_items`/`doc_chunks`/idx），且**回炉版缺 DEFAULT**（`root_entities`/`counts`/`status` 均无默认值，与 0005 版漂移——探针插入时实证 NotNullViolation）。后果：

- 干净库 `alembic upgrade head` 死于 `0004→0005` `DuplicateTable: context_requests already exists`（本地 `down -v` + 删 pgdata 亲测复现，FRESH_MIG=1）；
- 单事务回滚 → 库被清空成零表；
- **CI 最近 3 run 全 failure（含 handoff commit `754419b` 本身）**，交接文档只字未提，且 §0 声称 "Working tree: clean (all pushed)" 与事实不符（见 P1-3）。
- CI workflow step 名仍叫 "Migrate (alembic 0001+0002)"——cut-5 时代残留，侧面印证 0003–0007 期间无人看 CI。

本地一切绿（329 passed、smoke PASS、bench PASS）只因长寿命 volume 当年增量迁上来——**被验收状态 ≠ 可部署状态**。修复：恢复 0001 原 schema 或以新 squash 基线重整链；CI 转绿并纳入"fresh replay"步骤。

### P1 (Should fix before v0.2 cut-over)

**P1-1 cut-028 不变量被 per-resource 通道击穿（活体实证）**

`request_id_can_access()` 查 token 撤销 ✓ 但**不查 user 撤销**；audit.py:102 per-resource 命中后跳过 `user_can_access()`（撤销检查只在那里）。

```
P3b revoked-user + x-user-id + tok: 200  <-- cut-028 invariant violated
```

`ECE_REVOKED_USERS=alice` 时 alice 持有效 audit token 仍可读 trace——delegation.py 文档自称 "revoked users are denied ALL access"。修复：per-resource 分支加 `is_user_revoked` 前置。

**P1-2 rate/quota 桶键＝未验证的裸 header（活体实证）**

`check_rate_limit(x_org_id)`/`check_org_quota(x_org_id)` 直接用 X-Org-Id header 做桶键，不与 caller 身份（`ECE_USER_ORGS` 映射）绑定：

```
P4 rate-limit org_a x3: [200, 200, 429]
P4 rotate header -> org_b:            200  <-- bucket rotation evasion
```

单租户模式下换 org 名即换新桶（quota 同构）。多租户模式下 x_org_id 被强制等于 trace.org_id，问题减弱。修复：桶键改用已认证 caller 的映射 org；未映射 caller 归入统一 default 桶。

**P1-3 推送状态依赖不完整：uv.lock 落后于 pyproject**

已提交 uv.lock 的根项目依赖边缺 `pyjwt`/`redis`（包条目在、根 edges 无）；正确版本只存在于**未提交的工作树 diff（+37 行）**。干净检出 `uv sync --frozen` 会失败。连同 P0-2 的 CI 未披露，构成第 5 次完整性事故模式：**报告/交接的"好状态"部分依赖本地未推送状态**。修复：重跑 `uv lock` 并提交；交接清单增加 "CI 绿 + tree clean + push 后状态可复现" 三查。

### P2 (Nice to have, post-v0.2)

- Webhook 无 HMAC 签名、无重试队列（已在 §6.1 披露，列入 cut-035/037 计划 ✓）
- JWT 未验 `iat`/`aud`（已披露）
- 单 key JWT 轮换窗口（已披露，cut-036 计划 ✓）
- org_id=NULL 历史行跳过 org 检查（已披露 back-compat，建议加日落条款）
- Lua 每次重传、in-memory dict 无界（已披露，量级低）

## Test coverage assessment

- **量**：159→329（+170）为实（本地亲跑 `make test` 329 passed, 6 skipped）；delegation 全通道正/反用例、Lua/fallback、RS256、webhook 均有覆盖——面上是本 arc 最强的部分。
- **盲区**（与 P0/P1 一一对应）：① fallback 被当**特性**断言（测的是"回落可用"而非"回落该不该开"）；② 无 fresh-db 迁移重放测试（有则 CI 红早爆）；③ 无 revoked-user × per-resource 组合用例；④ 无桶键与身份绑定的对抗用例。共性：测试全沿"设计意图"写，缺攻击者视角——正是红队探针四发四中的原因。
- RBAC smoke（`verify_v02_rbac.sh` → 33 用例 PASS）与 bench（p95 21.5ms、0×429、SLA PASS）亲跑确认。

## Recommendation

**BLOCKER，v0.2 不得 cutover。** 建议将修复打包为 cut-035（顺序即优先级）：

1. JWT 执行闸门（P0-1）：无效/缺失 Authorization → 401；header 认证显式 opt-in。
2. 迁移链重整（P0-2）：消除 0001/0005 双建 + DEFAULT 漂移，fresh replay 进 CI，CI 转绿；step 改名。
3. `uv lock` 提交 + 交接三查立规（P1-3，CI 绿 / tree clean / push 状态可复现）。
4. per-resource 分支加 user-revocation 检查（P1-1）+ 回归用例。
5. rate/quota 桶键绑定认证身份（P1-2）+ 对抗用例（含本次 4 探针入测试）。

修复后重新 handoff；本次探针脚本可直接转为 cut-035 验收用例（`/tmp/cline_probe_v02.py` 已留档）。

---

Reviewed by: Cline (red-team track, adversarial re-run methodology)
Date: 2026-09-15
