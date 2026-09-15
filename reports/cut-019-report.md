# Cut-019 Report — multi-tenant + per-resource scope

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-019 |
| Date | 2026-09-15 |
| Sprint | Sprint 7 v0.2 |
| Scope | multi-tenant (cross-org) + per-resource scope |
| Author | Claude Fable 5 |
| Commit | `daeb575` |
| Branch | `main` |
| Test delta | 159 → 175 (+16) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `src/ece/api/org.py` | `parse_user_orgs()` / `get_user_org()` / `is_multi_tenant_mode()` / `check_org_access()` helpers |
| `src/ece/migrations/versions/0007_user_orgs.py` | Adds nullable `org_id` column + index to `context_requests` |
| `tests/integration/test_s7_orgs.py` | 16 multi-tenant tests (unit + integration) |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/context/provenance.py` | `record_package` accepts `user_org: str \| None = None`; INSERT writes `org_id` column |
| `src/ece/context/assembly.py` | imports `get_user_org` from `ece.api.org`; passes `user_org=get_user_org(user_dict["id"])` |
| `src/ece/audit/trace.py` | `get_context_trace` SELECT includes `org_id`; returns `org_id` field |
| `src/ece/api/audit.py` | Adds `X-Org-Id` header param; calls `check_org_access`; 400 if missing in multi-tenant mode, 403 if cross-org; response model adds `org_id` |
| `src/ece/api/debug.py` | Same `X-Org-Id` enforcement as `/audit` |
| `docs/API.md` | §8 audit/debug sections document `X-Org-Id` header + multi-tenant rules |

### 2.3 Env config

```bash
ECE_USER_ORGS="alice:org_a;bob:org_b;carol:org_a"
```

Format: `user_ref:org_id;...` — semicolon-separated entries, each mapping
a user to one org. Empty env = single-tenant mode (v0.1 back-compat).

### 2.4 Header contract

| Header | Required | Behavior |
|---|---|---|
| `X-User-Id` | one of these | self access (ADR-004 owner check) |
| `X-Delegation-Token` | one of these | cross-user access (cut-018b manager) |
| `X-Org-Id` | only if `ECE_USER_ORGS` set | cross-org isolation (cut-019) |

Errors (multi-tenant mode):
- `400` if `X-Org-Id` missing on `/audit` or `/debug`
- `403` if `X-Org-Id != trace.org_id` (cross-org blocked)
- legacy rows (`org_id IS NULL`) bypass enforcement for v0.1 back-compat

## 3. Verification (5 项 discipline)

```
uv run ruff check .            → All checks passed
uv run mypy src tests           → Success: no issues found in 95 source files
uv run lint-imports             → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                       → 175 passed, 6 skipped, 1 warning in 22.67s (was 159; +16 org tests)
make check-api-docs             → OK - 14 routes registered
```

Test breakdown (cut-019 adds 16):
- 5 unit tests for `parse_user_orgs` / `get_user_org` / `is_multi_tenant_mode`
- 5 unit tests for `check_org_access` (disabled / legacy / match / required / mismatch)
- 4 integration tests for `/audit` (matching / missing / cross-org / single-tenant)
- 2 integration tests for `/debug` (matching / cross-org)
- 1 integration test verifying `assemble_context` records `org_id`

## 4. Commit hash

- HEAD: `daeb575 feat(multi-tenant): X-Org-Id cross-org isolation + ECE_USER_ORGS env (cut-019)`
- Pushed: `75938ca..daeb575 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Legacy-row back-compat

When `ECE_USER_ORGS` is set BUT a `context_request` was recorded before
this migration (i.e., `org_id IS NULL`), the trace is still readable
without `X-Org-Id`. This prevents historical v0.1 traces from becoming
inaccessible after cut-019.

Rationale: cut-019 deployment happens against a database that may have
accumulated v0.1 traces over weeks/months. Forcing X-Org-Id for those
would break existing audit flows. Once all pre-cut-019 traces age out
or get backfilled, this back-compat can be tightened (cut-021+).

### 5.2 Cross-org delegation not yet wired

`X-Delegation-Token` currently grants cross-USER access (manager views
team's traces). It does NOT yet grant cross-ORG access (manager views
other org's traces). For v0.2 cut-019 scope, cross-org requires the
caller's own `X-Org-Id` to match.

Per-resource scope (manager views specific trace by ID only) is deferred
to cut-021+ — would extend delegation to include `request_id` patterns
or per-trace ACLs.

### 5.3 Single-tenant bypass is silent

When `ECE_USER_ORGS` is unset, `/audit` and `/debug` accept requests
without `X-Org-Id` and silently ignore any `X-Org-Id` provided. No
warning. This matches v0.1 behavior and avoids breaking deployments
that haven't migrated to multi-tenant.

For cut-021+ (full v0.2 cut-over), consider adding a startup log line
when multi-tenant is disabled but `X-Org-Id` headers are seen in traffic.

## 6. Lessons

### 6.1 Migration must be applied BEFORE tests can pass

Migrations are NOT auto-applied by `make test`. New column `org_id`
exists in schema but tests fail with `UndefinedColumn` until
`uv run alembic -c src/ece/migrations/alembic.ini upgrade head` runs.

**Apply this in CI/deploy**: either run migration before tests OR
make tests apply pending migrations on setup.

### 6.2 Header ordering: ADR-004 → multi-user → multi-tenant

Permission checks should be applied in this order in audit/debug handlers:
1. ADR-004 owner check (X-User-Id match)
2. multi-user delegation (X-Delegation-Token expansion)
3. multi-tenant org check (X-Org-Id match)

If org check runs before owner check, an attacker can probe org
membership of arbitrary users via 400/403 error messages. The current
order leaks only "trace exists" or "owner mismatch", which is correct.

### 6.3 Nullable `org_id` enables zero-downtime migration

By keeping `org_id` nullable (rather than `NOT NULL DEFAULT ''`),
existing rows keep their original NULL state and `check_org_access`
treats them as legacy (bypass enforcement). This is safer than
backfilling all rows with a default value at migration time.

### 6.4 Env config inherits delegation token pattern

`ECE_USER_ORGS` follows the same `;`-then-`:` syntax as
`ECE_DELEGATION_TOKENS`. Operators familiar with one immediately
understand the other. Consider documenting both side-by-side in
v0.2-deploy.md (cut-021 follow-up).

### 6.5 Test fixture env-mutation hygiene

Test fixtures that mutate `os.environ` must save+restore via `saved = os.environ.get(KEY)` pattern, NOT pop+restore blindly. The pop pattern can leak between tests if a test panics before its finally block. Several existing tests in test_s7_orgs.py already follow the save+restore idiom; continue this convention for new tests.

## 7. Cut-020 preview

cut-020 scope = real perf bench on production data scale + multi-tenant verification:

- Real LLM (`ECE_LLM_BASE_URL=qwen2.5:14b` local Ollama) E6 runner with
  multi-tenant trace mix
- P95 latency measurement on 200-question batch with 50/50 org_a/org_b
  split (simulating two tenants sharing one ECE instance)
- Cross-org audit denial coverage (50% of /audit calls should 403)
- Benchmark script: `scripts/bench_e6_real_llm_multi_tenant.sh`

Acceptance: P95 ≤ 1.5s on 200q batch + cross-org denial rate 100% (no
false positives in the 403 path) + ≥80% accuracy on E6.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>