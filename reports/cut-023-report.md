# Cut-023 Report — org-level rate limiting

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-023 |
| Date | 2026-09-15 |
| Sprint | Sprint 10 v0.2 |
| Scope | org-level rate limit via `ECE_ORG_RATE_LIMITS` |
| Author | Claude Fable 5 |
| Commit | `7d663ee` |
| Branch | `main` |
| Test delta | 207 → 219 (+12) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `src/ece/api/rate_limit.py` | `parse_org_rate_limits()` / `check_rate_limit()` / `reset_buckets()` |
| `tests/integration/test_s10_rate_limit.py` | 12 tests for org-level rate limiting |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/audit.py` | Calls `check_rate_limit(x_org_id)`; raises 429 + Retry-After when bucket exhausted |
| `src/ece/api/debug.py` | Same rate limit check as /audit |
| `docs/API.md` | §8 audit header table adds rate limit row |
| `docs/v0.2-deploy.md` | §4 multi-tenant adds `ECE_ORG_RATE_LIMITS` section + use cases |

### 2.3 Env config

```bash
ECE_ORG_RATE_LIMITS="org_a:100/m;org_b:500/h;org_c:1000/d"
```

Format: `org_id:N/period`. Period is `s|m|h|d` (seconds/minutes/hours/days).
Fixed-window counter: bucket starts at N, refills to N after period elapses.

### 2.4 HTTP behavior

- `429 Too Many Requests` when org's bucket exhausted
- `Retry-After` header in seconds (rounded up +1)
- `detail.retry_after_seconds` in JSON body

### 2.5 Use cases

- **Loud neighbor prevention**: `ECE_ORG_RATE_LIMITS="org_a:100/m"` caps one
  org's read traffic at 100/min
- **Free tier cap**: `ECE_ORG_RATE_LIMITS="free_org:10/h"` for trial users
- **Burst protection**: `ECE_ORG_RATE_LIMITS="org_a:5/s"` for very strict limits

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 100 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 219 passed, 6 skipped, 1 warning in 24.10s (was 207; +12 rate limit tests)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-023 adds 12):
- 1 unit test for `_period_to_seconds` (s/m/h/d + invalid)
- 3 unit tests for `parse_org_rate_limits` (basic / empty / invalid period)
- 4 unit tests for `check_rate_limit` (no-org / unconfigured / first / exhaustion)
- 4 integration tests for /audit + /debug (429 / per-org isolation / unconfigured / debug 429)

## 4. Commit hash

- HEAD: `7d663ee feat(rate-limit): ECE_ORG_RATE_LIMITS per-org fixed-window throttling (cut-023)`
- Pushed: `454e80f..7d663ee main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Fixed-window counter is simple but bursty

The fixed-window algorithm allows burst at window boundaries: an org with
`100/m` can do 100 requests in the last second of one minute AND the
first second of the next — effectively 200 in 2 seconds.

For smoother throttling, consider switching to token bucket or sliding
window in cut-024+. v0.2 cut-023 keeps it simple: predictable, easy to
reason about, no floating-point drift over long periods.

### 5.2 In-memory state is per-process

`_buckets` is a module-level dict, so each uvicorn worker process has
its own bucket. With N workers, an org effectively gets N× the limit.

For multi-process deployments, use Redis (or similar shared store) with
atomic INCR + EXPIRE. cut-024+ when production traffic warrants.

### 5.3 Rate limit check is per-endpoint-pair (org, request)

Each call to `/audit` or `/debug` consumes 1 token from the org's
bucket. Cross-endpoint (audit + debug) share the same bucket per org.

If separate budgets per endpoint are needed (e.g., "audit at 100/m
AND debug at 50/m"), split into two env vars (cut-024+).

### 5.4 Unconfigured orgs are unrestricted

Org not in `ECE_ORG_RATE_LIMITS` → no rate limit, all requests pass.
This is intentional for forward compatibility: existing orgs that
haven't been added to the limit config don't suddenly hit 429.

Production deployment checklist should add all active orgs to the limit.

## 6. Lessons

### 6.1 Threading.Lock is required for multi-threaded ASGI

uvicorn runs handlers in a thread pool (or async). Concurrent requests
to /audit mutate `_buckets` dict concurrently. Without `_lock`, race
conditions could double-spend tokens or corrupt bucket state.

**Pattern**: module-level `_lock = threading.Lock()`; acquire inside
`check_rate_limit` to make bucket ops atomic.

### 6.2 Retry-After header semantics

Per RFC 7231, `Retry-After` can be HTTP-date OR seconds (integer).
We use seconds (more common for 429). Format: integer seconds, with
`+1` rounding to avoid "retry immediately" when retry_after < 1s.

Test verifies the header is present (`"Retry-After" in r.headers`).

### 6.3 Reset fixture (`autouse=True`) prevents test pollution

Rate limit state persists across tests by default. The `_reset_buckets`
fixture with `autouse=True` runs before every test in the file,
clearing bucket state. Without this, test order could affect outcomes
(e.g., test_audit_rate_limit_429 consuming 2 tokens, leaving test_audit_rate_limit_per_org_isolation to start with depleted org_a).

**Pattern**: when module state affects tests, use `autouse=True` fixture
to reset state per test.

### 6.4 W292 (no trailing newline) recurs across cuts

Every cut produces files that need a trailing newline. ruff auto-fix
handles it, but tests must be re-run after auto-fix (auto-fix doesn't
trigger test re-run automatically).

Pattern observed: 3 W292 errors per cut on average. ruff --fix clears
them; subsequent `make test` verifies no regression.

## 7. Cut-024+ preview

Possible next cuts (in priority order):

1. **cut-024**: v0.2 cut-over — full RBAC doc + production rollout
   checklist (multi-tenant + cross-org delegation + per-resource +
   rate limit + audit token rotation).

2. **cut-025**: Redis-backed rate limit — replace in-memory `_buckets`
   with Redis INCR for multi-process correctness.

3. **cut-026**: token revocation list (`ECE_REVOKED_TOKENS`) — quick
   way to invalidate compromised tokens without env restart.

4. **cut-027**: JWT migration — replace `X-User-Id` with decoded JWT
   claim. SSO-friendly; eliminates user_ref spoofing.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>