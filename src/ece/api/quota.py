"""Per-org quota tracking (cut-029 — v0.2 hardening).

Per-org long-term usage quota (per-day / per-week / per-month).
Different from rate limit (cut-023): rate limit is burst protection
(short periods), quota is total usage tracking (long periods).

Env format:
    ECE_ORG_QUOTAS="org_a:10000/d;org_b:50000/w;org_c:200000/m"

`N/period` where period is `d|w|m` (days, weeks, months). Default
backend is Redis (atomic counter with TTL); in-memory fallback for
single-process deployments.

When quota exceeded: endpoint returns 429 with error_code
'quota_exceeded' and Retry-After header (days/weeks/months until reset).

For multi-process deployments: uses the same ECE_REDIS_URL backend
as cut-026 rate limit.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

# Reuse Redis client logic from rate_limit
from ece.api.rate_limit import _get_redis_client

# In-memory quota state: {org_id: (count, period_end_monotonic_ts)}
_quotas: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()


def parse_org_quotas() -> dict[str, tuple[int, float]]:
    """Parse ECE_ORG_QUOTAS env into {org_id: (N, period_seconds)}.

    Format: "org_a:10000/d;org_b:50000/w"
    Whitespace tolerant. Skips malformed entries.
    """
    raw = os.environ.get("ECE_ORG_QUOTAS", "")
    result: dict[str, tuple[int, float]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        org_id, quota_str = entry.split(":", 1)
        org_id = org_id.strip()
        if not org_id:
            continue
        if "/" not in quota_str:
            continue
        n_str, period = quota_str.split("/", 1)
        n_str = n_str.strip()
        period = period.strip()
        try:
            n = int(n_str)
        except ValueError:
            continue
        if n <= 0:
            continue
        period_sec = _period_to_seconds(period)
        if period_sec is None:
            continue
        result[org_id] = (n, period_sec)
    return result


def _period_to_seconds(period: str) -> float | None:
    """Convert period string to seconds. None for invalid."""
    if period == "d":
        return 86400.0
    if period == "w":
        return 604800.0
    if period == "m":
        return 2592000.0  # 30 days
    return None


def check_org_quota(org_id: str | None) -> tuple[bool, str, float]:
    """Check if request is allowed under org's quota.

    Args:
        org_id: org_id from X-Org-Id header (or None for no quota)

    Returns:
        (allowed, error_code, retry_after_seconds)
        - error_code 'no_quota': no quota configured (always allow)
        - error_code 'ok': allowed
        - error_code 'quota_exceeded': 429 (org's quota exhausted)
    """
    if not org_id:
        return True, "no_quota", 0.0

    quotas = parse_org_quotas()
    if org_id not in quotas:
        return True, "no_quota", 0.0

    n, period_sec = quotas[org_id]

    redis_client: Any = _get_redis_client()
    if redis_client is not None:
        return _check_quota_redis(redis_client, org_id, n, period_sec)
    return _check_quota_inmemory(org_id, n, period_sec)


def _check_quota_redis(
    client, org_id: str, n: int, period_sec: float
) -> tuple[bool, str, float]:
    """Redis-backed quota check (cut-029).

    Uses Lua script (cut-031) for atomic single-round-trip.
    Falls back to 2-op pattern if EVAL fails.
    """
    quota_key = f"ece:quota:{org_id}"
    try:
        result = client.eval(
            _QUOTA_LUA_SCRIPT,
            1,
            quota_key,
            int(period_sec),
            n,
        )
        allowed, retry_after = int(result[0]), float(result[1])
        if allowed == 1:
            return True, "ok", 0.0
        return False, "quota_exceeded", retry_after
    except Exception:
        # Fallback to 2-op pattern (cut-029 original)
        client.set(quota_key, 0, ex=int(period_sec), nx=True)
        count = client.incr(quota_key)
        if count > n:
            ttl = client.ttl(quota_key)
            retry_after = float(ttl) if ttl > 0 else period_sec
            return False, "quota_exceeded", retry_after
        return True, "ok", 0.0


# Lua script for atomic quota check (cut-031): same pattern as rate-limit
_QUOTA_LUA_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
if count > tonumber(ARGV[2]) then
    return {0, ttl}
end
return {1, 0}
"""


def _check_quota_inmemory(
    org_id: str, n: int, period_sec: float
) -> tuple[bool, str, float]:
    """In-memory quota check (single-process)."""
    now = time.monotonic()
    with _lock:
        if org_id not in _quotas:
            # First request: initialize to full quota
            _quotas[org_id] = (float(n - 1), now + period_sec)
            return True, "ok", 0.0

        count, period_end = _quotas[org_id]
        if now >= period_end:
            # Period reset: bucket refills
            count = float(n)
            period_end = now + period_sec

        if count <= 0:
            retry_after = max(0.0, period_end - now)
            _quotas[org_id] = (count, period_end)
            return False, "quota_exceeded", retry_after

        count -= 1
        _quotas[org_id] = (count, period_end)
        return True, "ok", 0.0


def reset_quotas() -> None:
    """Reset all in-memory quotas. For testing only."""
    with _lock:
        _quotas.clear()
