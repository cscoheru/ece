"""Sprint 15 v0.2 — per-org quota tracking tests (cut-029).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: long-term quota
tracking (per-day / per-week / per-month) separate from short-term
rate limit (cut-023).

Env format:
    ECE_ORG_QUOTAS="org_a:10000/d;org_b:50000/w;org_c:200000/m"

Different from rate limit:
- Rate limit: burst protection (N requests per second/minute)
- Quota: total usage tracking (N requests per day/week/month)
- Quota returns 'quota_exceeded' error_code; rate limit returns 'rate_limited'
"""
from unittest.mock import patch

import fakeredis
import pytest

from ece.api.quota import (
    _check_quota_redis,
    _period_to_seconds,
    check_org_quota,
    parse_org_quotas,
    reset_quotas,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset quota state and Redis client between tests."""
    reset_quotas()
    from ece.api.rate_limit import reset_redis_client

    reset_redis_client()
    monkeypatch.delenv("ECE_ORG_QUOTAS", raising=False)
    monkeypatch.delenv("ECE_REDIS_URL", raising=False)


def test_period_to_seconds() -> None:
    """Period string → seconds conversion (longer periods than rate limit)."""
    assert _period_to_seconds("d") == 86400.0
    assert _period_to_seconds("w") == 604800.0
    assert _period_to_seconds("m") == 2592000.0
    assert _period_to_seconds("invalid") is None
    # Short periods (s/m/h) NOT supported for quota (use rate limit instead)
    assert _period_to_seconds("s") is None
    assert _period_to_seconds("h") is None


def test_parse_org_quotas_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_org_quotas parses 'org:N/period' format."""
    monkeypatch.setenv("ECE_ORG_QUOTAS", "org_a:10000/d;org_b:50000/w;org_c:200000/m")
    result = parse_org_quotas()
    assert result["org_a"] == (10000, 86400.0)
    assert result["org_b"] == (50000, 604800.0)
    assert result["org_c"] == (200000, 2592000.0)


def test_parse_org_quotas_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """parse_org_quotas returns empty dict when env unset."""
    monkeypatch.delenv("ECE_ORG_QUOTAS", raising=False)
    assert parse_org_quotas() == {}


def test_parse_org_quotas_short_period_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Short periods (s/m/h) are not valid for quota (use rate limit)."""
    monkeypatch.setenv("ECE_ORG_QUOTAS", "org_a:100/s;org_b:200/d")
    result = parse_org_quotas()
    # org_a: short period rejected
    assert "org_a" not in result
    # org_b: daily quota accepted
    assert result["org_b"] == (200, 86400.0)


def test_check_org_quota_no_org() -> None:
    """No org_id → always allow."""
    allowed, code, _ = check_org_quota(None)
    assert allowed is True
    assert code == "no_quota"


def test_check_org_quota_unconfigured_org(monkeypatch: pytest.MonkeyPatch) -> None:
    """Org not in ECE_ORG_QUOTAS → no quota (always allow)."""
    monkeypatch.delenv("ECE_ORG_QUOTAS", raising=False)
    allowed, code, _ = check_org_quota("org_unknown")
    assert allowed is True
    assert code == "no_quota"


def test_check_org_quota_first_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """First request to configured org → allow."""
    monkeypatch.setenv("ECE_ORG_QUOTAS", "org_test:5/d")
    allowed, code, retry = check_org_quota("org_test")
    assert allowed is True
    assert code == "ok"
    assert retry == 0.0


def test_check_org_quota_exhaustion_returns_quota_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After N requests, quota empty → 429 with 'quota_exceeded' code."""
    monkeypatch.setenv("ECE_ORG_QUOTAS", "org_test:3/d")
    # 3 requests succeed
    for i in range(3):
        allowed, code, _ = check_org_quota("org_test")
        assert allowed is True, f"Request {i+1} should succeed"
    # 4th request fails with quota_exceeded
    allowed, code, retry = check_org_quota("org_test")
    assert allowed is False
    assert code == "quota_exceeded"
    assert retry > 0.0  # has retry-after (until next day)


def test_redis_quota_first_request_initializes() -> None:
    """Redis backend initializes key with period TTL on first request."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    allowed, code, _ = _check_quota_redis(fake, "org_redis", 100, 86400.0)
    assert allowed is True
    assert code == "ok"
    assert fake.ttl("ece:quota:org_redis") > 0


def test_redis_quota_exhaustion() -> None:
    """Redis backend: N+1 requests fail with quota_exceeded."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # 3/d quota
    for _ in range(3):
        allowed, _, _ = _check_quota_redis(fake, "org_redis", 3, 86400.0)
        assert allowed is True
    # 4th fails
    allowed, code, retry = _check_quota_redis(fake, "org_redis", 3, 86400.0)
    assert allowed is False
    assert code == "quota_exceeded"
    assert retry > 0.0


def test_redis_quota_per_org_isolation() -> None:
    """Different orgs have independent Redis quota counters."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # org_a: 2/d
    _check_quota_redis(fake, "org_a", 2, 86400.0)
    _check_quota_redis(fake, "org_a", 2, 86400.0)
    allowed_a, _, _ = _check_quota_redis(fake, "org_a", 2, 86400.0)
    assert allowed_a is False  # org_a exhausted
    # org_b: 5/d independent
    allowed_b, _, _ = _check_quota_redis(fake, "org_b", 5, 86400.0)
    assert allowed_b is True


def test_quota_uses_redis_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_org_quota dispatches to Redis backend when ECE_REDIS_URL is set."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("ECE_ORG_QUOTAS", "org_q:5/d")
    monkeypatch.setenv("ECE_REDIS_URL", "redis://fake:6379/0")
    from ece.api.rate_limit import reset_redis_client

    reset_redis_client()

    with patch("ece.api.rate_limit._redis_lib") as mock_lib:
        mock_lib.Redis.from_url.return_value = fake
        allowed, _, _ = check_org_quota("org_q")
        assert allowed is True
        # Verify Redis key was created
        assert fake.exists("ece:quota:org_q")
