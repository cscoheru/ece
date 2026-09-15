# Cut-026 Report — Redis-backed rate limit

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-026 |
| Date | 2026-09-15 |
| Sprint | Sprint 12.5 v0.2 (post-cutover hardening) |
| Scope | Redis backend for rate limit (multi-process correctness) |
| Author | Claude Fable 5 |
| Commit | `958ef1d` |
| Branch | `main` |
| Test delta | 241 → 251 (+10) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s12_redis_rate_limit.py` | 10 tests using fakeredis |

### 2.2 Files modified

| File | Change |
|---|---|
| `pyproject.toml` | Added `redis>=5.0` to deps + `fakeredis>=2.0` to dev deps |
| `src/ece/api/rate_limit.py` | Added Redis backend with `SET NX EX` + `INCR` atomic pattern |
| `docs/v0.2-deploy.md` | §4 multi-tenant adds Redis-backed rate limit section |
| `docs/v0.2-cutover-checklist.md` | §3 env vars adds optional `ECE_REDIS_URL` |

### 2.3 Env config

```bash
# Optional: enable Redis backend (multi-process correct)
export ECE_REDIS_URL="redis://localhost:6379/0"

# Required (cut-023): rate limits
export ECE_ORG_RATE_LIMITS="org_a:100/m;org_b:500/h"
```

If `ECE_REDIS_URL` is unset: in-memory backend (per-process, fine for
single-worker deployments). If set: Redis backend (atomic shared counter).

### 2.4 Algorithm

```python
# On each request:
client.set(f"ece:rl:{org_id}", 0, ex=period_sec, nx=True)  # init if not exists
count = client.incr(f"ece:rl:{org_id}")                     # atomic increment
if count > N:
    ttl = client.ttl(f"ece:rl:{org_id}")                    # for Retry-After
    return False, "rate_limited", ttl
return True, "ok", 0
```

Two ops (SET NX EX + INCR) per request. SET NX EX only sets TTL on
first request (key creation), subsequent requests just INCR. Atomic
counter shared across all workers via Redis.

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 103 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 251 passed, 6 skipped, 1 warning in 24.76s (was 241; +10 redis tests)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-026 adds 10):
- 2 unit tests for `_get_redis_client` (no-URL / with-URL mock)
- 3 unit tests for `_check_rate_limit_redis` (init / exhaustion / expire)
- 2 unit tests for `check_rate_limit` dispatch (Redis / in-memory)
- 2 unit tests for `check_rate_limit` (no-org / unconfigured)
- 1 unit test for per-org isolation in Redis backend

## 4. Commit hash

- HEAD: `958ef1d feat(rate-limit): Redis backend for multi-process correctness (cut-026)`
- Pushed: `a476323..958ef1d main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 SET NX EX + INCR vs Lua script

Two atomic ops (SET NX EX + INCR) are sufficient for fixed-window
counter. A Lua script would be more atomic (single round-trip), but
Redis pipelines with separate ops are simpler to reason about.

Trade-off: 2 ops × ~0.1ms = 0.2ms per request vs Lua script ~0.1ms.
For v0.2 throughput, the difference is negligible. cut-027+ could
optimize to Lua if needed.

### 5.2 Connection probe in lazy init

`_get_redis_client()` calls `_redis_client.ping()` to verify connection
on first use. This adds ~1ms latency on the first request after
startup, but catches connection errors early.

If Redis is unreachable, the function returns None and falls back to
in-memory (warning logged). Operator sees 429s instead of 500s — better
UX during Redis outages.

### 5.3 Optional dependency

`redis>=5.0` is in main deps (not optional), but `_redis_lib = None`
when import fails. This means:
- Production with `ECE_REDIS_URL` set: requires `pip install redis`
- Production without `ECE_REDIS_URL`: redis import not strictly required
  (try/except handles ImportError)

For v0.2 simplicity, redis is a hard dep. If minimizing dependencies,
move to optional `extras_require`.

### 5.4 fakeredis for testing without real Redis

Tests use `fakeredis.FakeRedis(decode_responses=True)` — an in-process
Redis emulator. No external Redis required for CI.

Trade-off: fakeredis has minor API gaps vs real Redis (e.g., pub/sub
quirks). For our use case (INCR + TTL + SET NX EX), it's fully
compatible.

## 6. Lessons

### 6.1 Multi-process correctness requires shared state

The cut-023 in-memory bucket was per-process. With N workers, an org
with limit `100/m` could effectively consume `100*N/m`. Cut-026 fixes
this by storing counter in Redis (shared across processes).

**Lesson**: any state that's "global" (rate limits, quotas, locks)
must be in shared storage (Redis) for multi-process deployments.
In-memory state is OK only for single-process.

### 6.2 Mock chain syntax for Redis client

Initial test had `mock_lib.Redis.from_url.return_value.ping.return_value = True`
— fails because `from_url.return_value` is a method, not an attribute.

Correct pattern: assign the FakeRedis instance directly to `from_url.return_value`.
fakeredis's `ping()` is a real method returning True (no need to mock).

**Lesson**: fakeredis provides a complete Redis API; only mock the
client constructor (Redis.from_url), not individual methods.

### 6.3 Type narrowing for Optional[bytes | str | None]

`fake.get("key")` returns `bytes | str | None` when `decode_responses=True`.
mypy requires narrowing None before `int()`.

**Pattern**: `val = fake.get("key"); assert val is not None; int(val)`.

### 6.4 Optional import pattern in v0.2 era

`try: import redis as _redis_lib except ImportError: _redis_lib = None`
allows code to work even without redis installed. mypy infers type as
Module | None, requiring explicit type ignore.

Alternative: require redis in deps (current choice). Simpler, but
forces install even if not used.

For cut-026, we chose hard dep + optional runtime fallback (graceful
degradation when ECE_REDIS_URL unset).

## 7. Cut-027+ preview

| Cut | Feature | Status |
|---|---|---|
| cut-027 | JWT migration (replace X-User-Id) | P1 |
| cut-028 | User-level revocation (ECE_REVOKED_USERS) | P2 |
| cut-029 | Per-org quota tracking | P3 |
| cut-030 | Audit log export (compliance) | P3 |

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>