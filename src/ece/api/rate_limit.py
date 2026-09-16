"""Org-level rate limiting (cut-023 + cut-026 — v0.2 hardening).

Per-org fixed-window rate limit for /audit + /debug endpoints.
Prevents runaway scripts / audit storms from a single org consuming
all read capacity.

Env format:
    ECE_ORG_RATE_LIMITS="org_a:100/m;org_b:500/h;org_c:1000/d"

`N/period` where period is one of s|m|h|d (seconds, minutes, hours, days).

When rate limit exceeded: endpoint returns 429 with Retry-After header.

Backend (cut-026):
- If ECE_REDIS_URL is set: Redis-backed counter (multi-process correct)
- Else: in-memory dict (single-process only)

Algorithm: fixed-window counter with TTL. Each org starts with N tokens.
Each request consumes 1 token. After `period` seconds, key expires
(bucket refills to N).

For multi-process deployments, Redis is required (in-memory bucket is
per-process, so N workers effectively gives N× the limit).
"""
from __future__ import annotations

import os
import threading
import time

# Optional Redis dependency (cut-026). Import at module level so tests
# can monkeypatch ece.api.rate_limit._redis_lib if needed.
_redis_lib = None
try:
    import redis as _redis_lib  # type: ignore[assignment]
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


# Per-org in-memory bucket state: {org_id: (count, last_refill_monotonic_ts)}
_buckets: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()

# Lazily-initialized Redis client (cut-026)
_redis_client = None


def parse_org_rate_limits() -> dict[str, tuple[int, float]]:
    """Parse ECE_ORG_RATE_LIMITS env into {org_id: (N, period_seconds)}.

    Format: "org_a:100/m;org_b:500/h;org_c:1000/d"
    Whitespace tolerant. Skips malformed entries.
    """
    raw = os.environ.get("ECE_ORG_RATE_LIMITS", "")
    result: dict[str, tuple[int, float]] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        org_id, limit_str = entry.split(":", 1)
        org_id = org_id.strip()
        if not org_id:
            continue
        if "/" not in limit_str:
            continue
        n_str, period = limit_str.split("/", 1)
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
    if period == "s":
        return 1.0
    if period == "m":
        return 60.0
    if period == "h":
        return 3600.0
    if period == "d":
        return 86400.0
    return None


def _get_redis_client():
    """Lazy-init Redis client from ECE_REDIS_URL env (cut-026).

    Returns None if ECE_REDIS_URL not set, redis lib unavailable, or
    client cannot be created. Callers fall back to in-memory.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not _REDIS_AVAILABLE:
        return None
    url = os.environ.get("ECE_REDIS_URL")
    if not url:
        return None
    try:
        _redis_client = _redis_lib.Redis.from_url(url, decode_responses=True)
        # Probe to verify connection (lazy)
        _redis_client.ping()
    except Exception:  # connection error, bad URL, etc.
        _redis_client = None
    return _redis_client


def reset_redis_client() -> None:
    """Reset Redis client (for testing)."""
    global _redis_client
    _redis_client = None


def _resolve_bucket_org_id(user_ref: str | None, x_org_id: str | None) -> str | None:
    """cut-037 R37.2: Derive rate-limit bucket key from authenticated identity.

    X-Org-Id header is NOT used to determine the bucket — per directive
    "不再信裸 X-Org-Id". Bucket key resolution:

    1. ECE_USER_ORGS mapping for user_ref (most authoritative — survives
       any X-Org-Id header value)
    2. "default" (catches all unmapped callers; cumulative bucket so
       rotation-by-omission doesn't bypass rate limits)

    Returns bucket key string. Never None.
    """
    from ece.api.org import get_user_org

    mapped = get_user_org(user_ref)
    if mapped:
        return mapped
    return "default"


def check_rate_limit(
    user_ref: str | None,
    x_org_id: str | None,
) -> tuple[bool, str, float]:
    """Check if request is allowed under caller's rate-limit bucket.

    cut-037 R37.2: bucket key is bound to the AUTHENTICATED user_ref's
    mapped org (via ECE_USER_ORGS). The X-Org-Id header NO LONGER
    determines the bucket. Closes P4 (probe: caller rotated X-Org-Id
    from org_a to org_b after exhausting org_a bucket — was returning
    200; should stay 429).

    Args:
        user_ref: authenticated user identity (from X-User-Id or JWT sub).
        x_org_id: legacy X-Org-Id header — IGNORED by this function for
                  bucket selection (still used by check_org_access for
                  multi-tenant cross-org isolation).

    Returns:
        (allowed, error_code, retry_after_seconds)
        - error_code 'no_limit': no rate limit configured for the bucket
        - error_code 'ok': allowed
        - error_code 'rate_limited': 429 (bucket exhausted)
    """
    bucket_org_id = _resolve_bucket_org_id(user_ref, x_org_id)

    limits = parse_org_rate_limits()
    if bucket_org_id not in limits:
        return True, "no_limit", 0.0

    n, period_sec = limits[bucket_org_id]

    redis_client = _get_redis_client()
    if redis_client is not None:
        return _check_rate_limit_redis(redis_client, bucket_org_id, n, period_sec)
    return _check_rate_limit_inmemory(bucket_org_id, n, period_sec)


def _check_rate_limit_redis(
    client, org_id: str, n: int, period_sec: float
) -> tuple[bool, str, float]:
    """Redis-backed rate limit check (cut-026).

    Uses Lua script (cut-031) for atomic single-round-trip counter
    increment with TTL init. Falls back to 2-op pattern if EVAL fails
    (e.g., Redis < 2.6 without Lua support).
    """
    bucket_key = f"ece:rl:{org_id}"
    try:
        # Lua script: atomic INCR + EXPIRE-on-first + check
        result = client.eval(
            _RATE_LIMIT_LUA_SCRIPT,
            1,
            bucket_key,
            int(period_sec),
            n,
        )
        allowed, retry_after = int(result[0]), float(result[1])
        if allowed == 1:
            return True, "ok", 0.0
        return False, "rate_limited", retry_after
    except Exception:
        # Fallback to 2-op pattern (cut-026 original)
        client.set(bucket_key, 0, ex=int(period_sec), nx=True)
        count = client.incr(bucket_key)
        if count > n:
            ttl = client.ttl(bucket_key)
            retry_after = float(ttl) if ttl > 0 else period_sec
            return False, "rate_limited", retry_after
        return True, "ok", 0.0


# Lua script for atomic rate-limit check (cut-031):
#   KEYS[1] = bucket key (e.g. ece:rl:org_a)
#   ARGV[1] = period_sec (TTL on first request)
#   ARGV[2] = max N (limit threshold)
# Returns: {allowed (1/0), retry_after_seconds}
_RATE_LIMIT_LUA_SCRIPT = """
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


def _check_rate_limit_inmemory(
    org_id: str, n: int, period_sec: float
) -> tuple[bool, str, float]:
    """In-memory rate limit check (single-process)."""
    now = time.monotonic()
    with _lock:
        if org_id not in _buckets:
            # First request: initialize to full bucket, consume 1
            _buckets[org_id] = (float(n - 1), now)
            return True, "ok", 0.0

        count, last_refill = _buckets[org_id]
        elapsed = now - last_refill

        if elapsed >= period_sec:
            # Refill: bucket resets to N
            count = float(n)
            last_refill = now
        else:
            retry_after = period_sec - elapsed

        if count <= 0:
            retry_after = period_sec - elapsed if elapsed < period_sec else 0.0
            _buckets[org_id] = (count, last_refill)
            return False, "rate_limited", retry_after

        count -= 1
        _buckets[org_id] = (count, last_refill)
        return True, "ok", 0.0


def reset_buckets() -> None:
    """Reset all in-memory buckets. For testing only."""
    with _lock:
        _buckets.clear()
