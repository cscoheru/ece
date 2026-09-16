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


def _resolve_bucket_org_id(user_ref: str | None, x_org_id: str | None) -> str | None:
    """cut-037 R37.2: Mirror of rate_limit._resolve_bucket_org_id.

    Bucket key = ECE_USER_ORGS-mapped org (if mapped) else "default".
    X-Org-Id header is NOT used (per "不再信裸 X-Org-Id" directive).
    """
    from ece.api.org import get_user_org

    mapped = get_user_org(user_ref)
    if mapped:
        return mapped
    return "default"


def check_org_quota(
    user_ref: str | None,
    x_org_id: str | None,
) -> tuple[bool, str, float]:
    """Check if request is allowed under caller's quota.

    cut-037 R37.2: bucket key bound to authenticated user_ref's mapped org
    (via ECE_USER_ORGS), not raw X-Org-Id header. X-Org-Id is NOT trusted
    as bucket selector (still used by check_org_access for multi-tenant
    isolation).

    Args:
        user_ref: authenticated user identity.
        x_org_id: legacy X-Org-Id header — IGNORED for bucket selection.

    Returns:
        (allowed, error_code, retry_after_seconds)
        - error_code 'no_quota': no quota configured for the bucket
        - error_code 'ok': allowed
        - error_code 'quota_exceeded': 429 (quota exhausted)
    """
    bucket_org_id = _resolve_bucket_org_id(user_ref, x_org_id)

    quotas = parse_org_quotas()
    if bucket_org_id not in quotas:
        return True, "no_quota", 0.0

    n, period_sec = quotas[bucket_org_id]

    redis_client: Any = _get_redis_client()
    if redis_client is not None:
        return _check_quota_redis(redis_client, bucket_org_id, n, period_sec)
    return _check_quota_inmemory(bucket_org_id, n, period_sec)


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
