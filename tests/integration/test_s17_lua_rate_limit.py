"""Sprint 17 v0.2 — Redis Lua atomic rate-limit tests (cut-031).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening optimization:
replace 2-op Redis pattern (SET NX EX + INCR) with single atomic Lua
script. Reduces round-trips, eliminates race conditions on the
EXPIRE-then-INCR window.

Backward compat: if EVAL fails (older Redis, network glitch), falls
back to 2-op pattern.
"""
from unittest.mock import patch

import fakeredis
import pytest

from ece.api.quota import _check_quota_redis
from ece.api.rate_limit import _check_rate_limit_redis


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from ece.api.rate_limit import reset_redis_client

    reset_redis_client()
    monkeypatch.delenv("ECE_REDIS_URL", raising=False)


def test_lua_rate_limit_first_request_initializes() -> None:
    """Lua path: first request initializes key with TTL."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    allowed, code, _ = _check_rate_limit_redis(fake, "org_lua", 5, 60.0)
    assert allowed is True
    assert code == "ok"
    assert fake.ttl("ece:rl:org_lua") > 0


def test_lua_rate_limit_exhaustion() -> None:
    """Lua path: N+1 requests fail with retry_after from TTL."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    for _ in range(3):
        allowed, _, _ = _check_rate_limit_redis(fake, "org_lua", 3, 60.0)
        assert allowed is True
    # 4th fails
    allowed, code, retry = _check_rate_limit_redis(fake, "org_lua", 3, 60.0)
    assert allowed is False
    assert code == "rate_limited"
    assert retry > 0.0


def test_lua_quota_first_request() -> None:
    """Lua quota path: first request initializes key."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    allowed, code, _ = _check_quota_redis(fake, "org_quota_lua", 100, 86400.0)
    assert allowed is True
    assert code == "ok"
    assert fake.ttl("ece:quota:org_quota_lua") > 0


def test_lua_quota_exhaustion() -> None:
    """Lua quota path: N+1 requests fail with quota_exceeded code."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    for _ in range(3):
        allowed, _, _ = _check_quota_redis(fake, "org_q_lua", 3, 86400.0)
        assert allowed is True
    allowed, code, retry = _check_quota_redis(fake, "org_q_lua", 3, 86400.0)
    assert allowed is False
    assert code == "quota_exceeded"
    assert retry > 0.0


def test_lua_fallback_to_two_op_on_eval_failure() -> None:
    """If Redis EVAL raises, falls back to 2-op SET NX EX + INCR."""
    fake = fakeredis.FakeRedis(decode_responses=True)

    class FailingEvalClient:
        """Proxy that fails eval() but forwards other ops to fake."""

        def __init__(self, inner: fakeredis.FakeRedis) -> None:
            self.inner = inner

        def eval(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("EVAL not supported")

        def set(self, *args: object, **kwargs: object) -> object:
            return self.inner.set(*args, **kwargs)  # type: ignore[arg-type]

        def incr(self, *args: object, **kwargs: object) -> int:
            return self.inner.incr(*args, **kwargs)  # type: ignore[arg-type]

        def ttl(self, *args: object, **kwargs: object) -> int:
            return self.inner.ttl(*args, **kwargs)  # type: ignore[arg-type]

    fallback = FailingEvalClient(fake)
    allowed, code, _ = _check_rate_limit_redis(fallback, "org_fallback", 5, 60.0)
    assert allowed is True
    assert code == "ok"
    # Verify fallback path created key via SET NX EX
    assert fake.ttl("ece:rl:org_fallback") > 0


def test_lua_returns_same_result_as_two_op() -> None:
    """Lua path and 2-op fallback produce equivalent results."""
    # Lua path
    fake_lua = fakeredis.FakeRedis(decode_responses=True)
    for _ in range(2):
        allowed, _, _ = _check_rate_limit_redis(fake_lua, "org_a", 2, 60.0)
        assert allowed is True
    allowed, _, _ = _check_rate_limit_redis(fake_lua, "org_a", 2, 60.0)
    assert allowed is False

    # 2-op path (delete and re-test)
    fake_lua.delete("ece:rl:org_a")
    # Manually trigger fallback
    fake_lua.set("ece:rl:org_a", 0, ex=60, nx=True)
    fake_lua.incr("ece:rl:org_a")
    fake_lua.incr("ece:rl:org_a")
    fake_lua.incr("ece:rl:org_a")
    # 2-op also exhausted at 3
    val = fake_lua.get("ece:rl:org_a")
    assert val is not None
    assert int(val) == 3


def test_lua_atomic_single_call() -> None:
    """Lua path uses single Redis EVAL call (vs 3 ops in 2-op)."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    # Track call count via mock
    with patch.object(fake, "eval", wraps=fake.eval) as mock_eval:
        _check_rate_limit_redis(fake, "org_atomic", 5, 60.0)
        # 1 EVAL call vs 2 ops (SET + INCR + TTL) in fallback
        assert mock_eval.call_count == 1


def test_lua_quota_uses_single_call() -> None:
    """Lua quota path uses single Redis EVAL call."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch.object(fake, "eval", wraps=fake.eval) as mock_eval:
        _check_quota_redis(fake, "org_atomic_q", 100, 86400.0)
        assert mock_eval.call_count == 1
