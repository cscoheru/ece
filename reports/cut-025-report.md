# Cut-025 Report — v0.2 cut-over consolidation

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-025 |
| Date | 2026-09-15 |
| Sprint | Sprint 12 v0.2 (closure) |
| Scope | end-to-end RBAC test + production rollout checklist |
| Author | Claude Fable 5 |
| Commit | `adb9809` |
| Branch | `main` |
| Test delta | 230 → 241 (+11) |

## 2. v0.2 hardening arc summary

After cut-025, the v0.2 hardening arc (cut-018b → cut-025) is complete:

| Cut | Feature | Tests | Cumulative |
|---|---|---|---|
| cut-018b | multi-user delegation (per-USER) | +10 | 169 |
| cut-019 | multi-tenant (X-Org-Id) | +16 | 175 |
| cut-020 | multi-tenant perf bench | +9 | 184 |
| cut-021 | cross-org delegation (per-ORG) | +12 | 196 |
| cut-022 | per-resource scope (per-RESOURCE) | +11 | 207 |
| cut-023 | org-level rate limit | +12 | 219 |
| cut-024 | token revocation | +11 | 230 |
| **cut-025** | **e2e RBAC + production checklist** | **+11** | **241** |

**Total v0.2 delta**: 159 → 241 tests (+82 tests, +52%).

## 3. Changes

### 3.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s12_v02_e2e.py` | 11 end-to-end RBAC scenarios exercising all 6 delegation channels |
| `docs/v0.2-cutover-checklist.md` | Production rollout runbook (pre-cutover, migration, env, headers, deployment, rollback, monitoring) |
| `scripts/verify_v02_rbac.sh` | One-shot RBAC smoke test entry point (runs alembic upgrade + pytest e2e) |

### 3.2 RBAC scenarios tested

| Scenario | Channel | Cut | Expected |
|---|---|---|---|
| 1. Owner reads own trace | owner | cut-001 ADR-004 | 200 |
| 2. Per-USER delegation | X-Delegation-Token (per-user) | cut-018b | 200 |
| 3. Cross-org blocked | X-Org-Id mismatch | cut-019 | 403 |
| 4. Per-ORG delegation | X-Delegation-Token (per-org) | cut-021 | 200 (cross-org via token) |
| 5. Per-RESOURCE delegation | X-Delegation-Token (per-rq) | cut-022 | 200 (specific rq) |
| 5b. Per-RESOURCE denies other | X-Delegation-Token (per-rq) | cut-022 | 403 (different rq) |
| 6. Rate limit per-org | X-Org-Id bucket | cut-023 | 429 after N |
| 7. Revoked token blocks | ECE_REVOKED_TOKENS | cut-024 | 403 |
| 7b. Owner unaffected by revocation | X-User-Id == trace.user_ref | cut-024 | 200 |
| 8. Combined owner + token | redundant | — | 200 |
| 9. Full v0.2 RBAC matrix | all combined | — | mixed 200/403 |

## 4. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 102 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 241 passed, 6 skipped, 1 warning in 23.03s (was 230; +11 e2e tests)
make check-api-docs            → OK - 14 routes registered
```

## 5. Commit hash

- HEAD: `adb9809 feat(v0.2-cutover): e2e RBAC test + production checklist (cut-025)`
- Pushed: `a66581c..adb9809 main -> main` (via Clash proxy)

## 6. Non-typical items

### 6.1 v0.2-cutover-checklist.md complements (not replaces) v0.2-deploy.md

`v0.2-deploy.md` is the **reference doc** (env vars, header contract,
use cases, troubleshooting). `v0.2-cutover-checklist.md` is the
**operational runbook** (deployment order, rollback plan, monitoring).

Operators read both: reference for understanding, runbook for executing.

### 6.2 verify_v02_rbac.sh is a smoke test, not full e2e

The script runs `pytest tests/integration/test_s12_v02_e2e.py -v` —
this is fast (under 30s with seed data) and exercises all RBAC channels.
For deeper verification, use the perf bench (cut-020) with real LLM.

### 6.3 e2e test uses monkeypatch for env isolation

`_setup_env` fixture uses `pytest.MonkeyPatch.setenv` which auto-restores
env after each test. This prevents test pollution across the e2e
scenarios (no need for explicit save/restore finally blocks).

**Pattern**: prefer `monkeypatch` over `os.environ` mutation when
available — it's safer.

### 6.4 RBAC matrix is now production-ready

All 6 delegation channels (owner + 5 delegation types + rate limit +
revocation) have been:
- Implemented
- Unit tested
- Integration tested
- Documented in API.md + v0.2-deploy.md + v0.2-cutover-checklist.md
- Verified end-to-end via cut-025

**Status**: ready for production cut-over. Operator must run
`bash scripts/verify_v02_rbac.sh` AND `bash scripts/bench_e6_real_llm_multi_tenant.sh`
(real LLM) before flipping traffic.

## 7. Lessons

### 7.1 E2E tests catch cross-cutting regressions

`test_full_v02_flow` runs all RBAC scenarios in sequence. A regression
in any single channel (e.g., revocation check broken) breaks the
e2e test, even if the channel-specific unit tests still pass.

**Lesson**: e2e tests complement unit tests by catching interactions
between channels. Keep both layers.

### 7.2 autouse fixture simplifies multi-env tests

The `_setup_env` fixture with `monkeypatch.setenv` runs for every test
in the file. This eliminates the save/restore boilerplate that
dominated earlier test files (cut-018b/019/021/022/023/024).

**Pattern shift**: from `try/finally` env mutation to `monkeypatch`.
Use `monkeypatch` for new tests; legacy `try/finally` patterns can stay.

### 7.3 Cut-over checklist must include rollback

`v0.2-cutover-checklist.md §6` documents rollback: unset `ECE_USER_ORGS`
(disables multi-tenant), `ECE_REVOKED_TOKENS` (without redeploy),
`alembic downgrade -1` (drops column).

**Lesson**: every cut-over needs an explicit rollback plan. Operators
should NEVER deploy without one.

### 7.4 Documentation split: reference vs runbook

Splitting docs into reference (v0.2-deploy.md) and runbook
(v0.2-cutover-checklist.md) keeps each focused. Reference = what is
this feature. Runbook = how do I deploy it.

For future cuts, maintain this split:
- New feature → update API.md + v0.2-deploy.md (reference)
- New ops procedure → update v0.2-cutover-checklist.md (runbook)

## 8. v0.2 closure: production-ready?

After cut-025, v0.2 is **production-ready** subject to:

✅ All 6 RBAC channels implemented + tested
✅ Migration script (alembic upgrade head) verified
✅ Production runbook documented
✅ Smoke test (`verify_v02_rbac.sh`) passing
✅ E6 ≥80% gate helper documented (cut-018c, cut-020)
✅ Real LLM cut-over gate documented (cut-020)

⚠️ Operator must verify before deployment:
- `bash scripts/verify_v02_rbac.sh` returns 0
- `bash scripts/bench_e6_real_llm_multi_tenant.sh` returns 0 (real LLM)
- 5/5 discipline green in target deployment
- Migration applied to production DB
- All X-Org-Id headers added to /audit + /debug callers
- Monitoring metrics enabled

Once these are confirmed, ECE v0.2 can be cut-over to production.

## 9. Cut-026+ preview (post v0.2)

| Cut | Feature | Status |
|---|---|---|
| cut-026 | Redis-backed rate limit (multi-process) | P1 (extends cut-023) |
| cut-027 | JWT migration (replace X-User-Id) | P2 (SSO + spoofing fix) |
| cut-028 | user-level revocation (ECE_REVOKED_USERS) | P2 (extend cut-024) |
| cut-029 | per-org quota tracking | P3 (extends rate limit) |
| cut-030 | audit log export (compliance) | P3 (extend export_audit.py) |

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>