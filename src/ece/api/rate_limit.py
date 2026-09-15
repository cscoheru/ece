"""Org-level rate limiting (cut-023 — v0.2 hardening).

Per-org fixed-window rate limit for /audit + /debug endpoints.
Prevents runaway scripts / audit storms from a single org consuming
all read capacity.

Env format:
    ECE_ORG_RATE_LIMITS="org_a:100/m;org_b:500/h;org_c:1000/d"

`N/period` where period is one of s|m|h|d (seconds, minutes, hours, days).

When rate limit exceeded: endpoint returns 429 with Retry-After header.

Algorithm: fixed-window counter. Each org starts with N tokens. Each
request consumes 1 token. After `period` seconds, bucket refills to N.

For multi-process deployments, the in-memory bucket is per-process. Use
Redis or similar for shared state (cut-024+).

Per ECE/CLAUDE.md 私有化 acceptance: rate limit is per-org (X-Org-Id
header), not per-IP. Single-tenant deployments (ECE_USER_ORGS unset)
skip rate limiting entirely.
"""
from __future__ import annotations

import os
import threading
import time

# Per-org bucket state: {org_id: (count, last_refill_monotonic_ts)}
_buckets: dict[str, tuple[float, float]] = {}
_lock = threading.Lock()


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


def check_rate_limit(org_id: str | None) -> tuple[bool, str, float]:
    """Check if request is allowed under org's rate limit.

    Args:
        org_id: org_id from X-Org-Id header (or None for no limit)

    Returns:
        (allowed, error_code, retry_after_seconds)
        - error_code 'no_limit': no rate limit configured (always allow)
        - error_code 'ok': allowed
        - error_code 'rate_limited': 429 (org's bucket exhausted)
    """
    if not org_id:
        return True, "no_limit", 0.0

    limits = parse_org_rate_limits()
    if org_id not in limits:
        return True, "no_limit", 0.0

    n, period_sec = limits[org_id]
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
