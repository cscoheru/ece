"""Sprint 12.5 v0.2 — Redis-backed rate limit tests (cut-026).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: rate limit
backend switches from in-memory (per-process) to Redis (multi-process
correct) when ECE_REDIS_URL env is set.

Uses fakeredis to mock Redis in tests without requiring a real Redis
instance. Verifies:
- Redis path: counter increments per request, TTL on key, expires after period
- Fallback: when ECE_REDIS_URL unset, in-memory path is used
- Same public API: check_rate_limit returns (allowed, code, retry_after)
"""
from unittest.mock import patch

import fakeredis
import pytest

from ece.api.rate_limit import (
    _check_rate_limit_redis,
    _get_redis_client,
    check_rate_limit,
    reset_buckets,
    reset_redis_client,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset both in-memory buckets and Redis client between tests."""
    reset_buckets()
    reset_redis_client()
    monkeypatch.delenv("ECE_REDIS_URL", raising=False)
    monkeypatch.delenv("ECE_ORG_RATE_LIMITS", raising=False)


def test_get_redis_client_no_url() -> None:
    """_get_redis_client returns None when ECE_REDIS_URL unset."""
    import os

    os.environ.pop("ECE_REDIS_URL", None)
    reset_redis_client()
    assert _get_redis_client() is None


def test_get_redis_client_with_url() -> None:
    """_get_redis_client connects when ECE_REDIS_URL is set (mocked)."""
    import os

    fake = fakeredis.FakeRedis(decode_responses=True)
    # Make fake.ping() return True (fakeredis supports ping natively)
    os.environ["ECE_REDIS_URL"] = "redis://fake:6379/0"
    reset_redis_client()
    with patch("ece.api.rate_limit._redis_lib") as mock_lib:
        mock_lib.Redis.from_url.return_value = fake
        client = _get_redis_client()
        assert client is fake
        # Second call returns cached client (no re-init)
        client2 = _get_redis_client()
        assert client2 is fake
    reset_redis_client()


def test_redis_first_request_initializes_key_with_ttl() -> None:
    """First request sets key with TTL; second request increments count."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # 5/min limit, 60s period
    allowed, code, retry = _check_rate_limit_redis(fake, "org_test", 5, 60.0)
    assert allowed is True
    assert code == "ok"
    # Key should exist with TTL
    assert fake.ttl("ece:rl:org_test") > 0
    val = fake.get("ece:rl:org_test")
    assert val is not None
    assert int(val) == 1


def test_redis_exhaustion_returns_429() -> None:
    """After N requests, Redis returns rate_limited."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # 3/min limit
    for i in range(3):
        allowed, code, _ = _check_rate_limit_redis(fake, "org_test", 3, 60.0)
        assert allowed is True, f"Request {i+1} should succeed"
    # 4th request fails
    allowed, code, retry = _check_rate_limit_redis(fake, "org_test", 3, 60.0)
    assert allowed is False
    assert code == "rate_limited"
    assert retry > 0.0  # TTL is still active


def test_redis_key_expires_resets_counter() -> None:
    """After TTL expires, counter resets (next request allowed)."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # 2/s limit with 1s period
    _check_rate_limit_redis(fake, "org_test", 2, 1.0)
    _check_rate_limit_redis(fake, "org_test", 2, 1.0)
    # 3rd request fails
    allowed, _, _ = _check_rate_limit_redis(fake, "org_test", 2, 1.0)
    assert allowed is False
    # Force expiry
    fake.delete("ece:rl:org_test")
    # Next request succeeds (key re-initialized)
    allowed, code, _ = _check_rate_limit_redis(fake, "org_test", 2, 1.0)
    assert allowed is True
    assert code == "ok"


def test_check_rate_limit_uses_redis_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """check_rate_limit dispatches to Redis backend when ECE_REDIS_URL is set."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", "org_redis:5/m")
    monkeypatch.setenv("ECE_REDIS_URL", "redis://fake:6379/0")
    reset_redis_client()

    with patch("ece.api.rate_limit._redis_lib") as mock_lib:
        mock_lib.Redis.from_url.return_value = fake

        # First request → Redis backend
        allowed, code, _ = check_rate_limit("org_redis")
        assert allowed is True
        assert code == "ok"
        # Verify Redis key was created
        assert fake.exists("ece:rl:org_redis")


def test_check_rate_limit_falls_back_to_inmemory_when_no_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ECE_REDIS_URL, in-memory backend is used."""
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", "org_inmem:3/m")
    monkeypatch.delenv("ECE_REDIS_URL", raising=False)
    reset_redis_client()

    # First 3 requests succeed
    for _ in range(3):
        allowed, code, _ = check_rate_limit("org_inmem")
        assert allowed is True
    # 4th request fails (in-memory bucket exhausted)
    allowed, code, retry = check_rate_limit("org_inmem")
    assert allowed is False
    assert code == "rate_limited"
    assert retry > 0.0


def test_check_rate_limit_unconfigured_org_allows_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Org not in ECE_ORG_RATE_LIMITS → no limit (regardless of backend)."""
    monkeypatch.setenv("ECE_ORG_RATE_LIMITS", "org_a:1/m")
    monkeypatch.delenv("ECE_REDIS_URL", raising=False)

    # 5 requests to org_b (not in config) → all succeed
    for _ in range(5):
        allowed, code, _ = check_rate_limit("org_b")
        assert allowed is True
        assert code == "no_limit"


def test_check_rate_limit_no_org_id_allows_all() -> None:
    """No org_id → no limit."""
    allowed, code, _ = check_rate_limit(None)
    assert allowed is True
    assert code == "no_limit"


def test_redis_per_org_isolation() -> None:
    """Different orgs have independent Redis counters."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # org_a: 2/s limit
    _check_rate_limit_redis(fake, "org_a", 2, 60.0)
    _check_rate_limit_redis(fake, "org_a", 2, 60.0)
    allowed_a, _, _ = _check_rate_limit_redis(fake, "org_a", 2, 60.0)
    assert allowed_a is False  # org_a exhausted

    # org_b: 5/s limit (independent)
    allowed_b, code, _ = _check_rate_limit_redis(fake, "org_b", 5, 60.0)
    assert allowed_b is True
    assert code == "ok"
