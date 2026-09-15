# Cut-029 Report — per-org quota tracking

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-029 |
| Date | 2026-09-15 |
| Sprint | Sprint 15 v0.2 |
| Scope | `ECE_ORG_QUOTAS` long-term usage tracking |
| Author | Claude Fable 5 |
| Commit | `1141fda` |
| Branch | `main` |
| Test delta | 277 → 289 (+12) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `src/ece/api/quota.py` | `parse_org_quotas()` + `check_org_quota()` (Redis + in-memory) |
| `tests/integration/test_s15_quota.py` | 12 tests |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/audit.py` | Calls `check_org_quota()` after rate limit check; 429 with `quota_exceeded` code |
| `src/ece/api/debug.py` | Same quota check as /audit |

### 2.3 Env config

```bash
ECE_ORG_QUOTAS="org_a:10000/d;org_b:50000/w;org_c:200000/m"
```

Format: `org_id:N/period`. Period is `d|w|m` (days/weeks/months).
Short periods (`s|m|h`) NOT supported — use rate limit (cut-023).

### 2.4 Rate limit vs quota

| Aspect | Rate limit (cut-023) | Quota (cut-029) |
|---|---|---|
| Period | s / m / h | d / w / m |
| Purpose | Burst protection | Total usage tracking |
| Error code | `rate_limited` | `quota_exceeded` |
| Retry-After | Seconds (short) | Hours/days (long) |
| HTTP status | 429 | 429 |
| Backend | Redis (cut-026) | Redis (shared) |

Both can be active simultaneously. Rate limit fires first (shorter
period), then quota.

### 2.5 Algorithm

Same Redis pattern as cut-026 rate limit:
- `SET NX EX` initializes key with TTL = period_seconds
- `INCR` returns new count
- If count > N: rate_limited, retry_after = remaining TTL

In-memory fallback uses `now + period_sec` for absolute time-based
reset (vs rate limit's monotonic-based refill).

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 108 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 289 passed, 6 skipped, 2 warnings in 29.75s (was 277; +12 quota tests)
```

## 4. Commit hash

- HEAD: `1141fda feat(quota): ECE_ORG_QUOTAS per-org long-term usage tracking (cut-029)`
- Pushed: `e112fea..1141fda main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Two-tier protection: rate limit (short) + quota (long)

- Rate limit: protects against burst spikes (per-second / per-minute)
- Quota: enforces long-term budget (per-day / per-week / per-month)

Both apply to same `/audit` + `/debug` endpoints. Order of checks:
1. Owner / delegation / per-resource (cut-018b/021/022)
2. X-Org-Id match (cut-019)
3. Rate limit (cut-023)
4. Quota (cut-029)

Quota is checked AFTER rate limit because rate limit is more strict
(shorter period, lower tolerance). Org exceeding daily quota
should hit rate limit first during burst.

### 5.2 Quota TTL is exact period (vs rate limit's fixed window)

Quota key has TTL = period_seconds (86400 / 604800 / 2592000). After
TTL, key expires and counter resets to 0 on next request.

Rate limit uses fixed-window counter that resets via refill logic.

Both achieve the same effect; quota uses Redis TTL for simplicity,
rate limit uses refill logic for finer control over retry_after.

### 5.3 Reuses ECE_REDIS_URL from cut-026

Both rate limit and quota share the same Redis client (when
configured). No need for separate Redis URLs. Operators configure
`ECE_REDIS_URL` once, both features benefit.

### 5.4 In-memory quota uses absolute time

In-memory path uses `time.monotonic()` + `period_end` to detect
period reset. When `now >= period_end`, bucket refills. This is
different from rate limit's monotonic elapsed tracking, but equivalent
in effect.

## 6. Lessons

### 6.1 Same Redis pattern across cut-026 + cut-029

Both use `SET NX EX` + `INCR` for atomic counter. Copy-paste-adapt
worked, but factoring out a helper `_redis_incr_with_ttl()` would
reduce duplication. cut-031+ refactor opportunity.

### 6.2 Period format must be longer than rate limit's

Quota periods (`d|w|m`) intentionally exclude `s|m|h` to prevent
operators from accidentally using quota for short-term bursts (use
rate limit instead). Validation in `_period_to_seconds()` enforces
this.

### 6.3 Distinct error codes for distinct concerns

`rate_limited` vs `quota_exceeded` lets clients (e.g., SDK) handle
each differently:
- `rate_limited` → backoff exponentially
- `quota_exceeded` → wait until next period or upgrade plan

Generic `429` would conflate these.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>