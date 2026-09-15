"""S7 — Multi-tenant perf bench + cross-org denial tests (cut-020).

Per ADR-009 SLA + cut-019 multi-tenant: bench_multi_tenant.py must
report p95 < 1.5s and 100% cross-org denial rate. These tests verify
the bench script's pure logic (percentile, cross-org denial) without
running the full perf measurement (which depends on hardware).

For full perf measurement, run `uv run python scripts/bench_multi_tenant.py`
manually (see docs/v0.2-deploy.md §4).
"""
from __future__ import annotations

import os

from ece.api.org import check_org_access, is_multi_tenant_mode
from ece.context.assembly import assemble_context
from ece.db import get_engine
from scripts.bench_multi_tenant import (
    ORG_A,
    ORG_B,
    USER_ORG_A,
    USER_ORG_B,
    _percentile,
    bench_cross_org_denial,
)


def test_percentile_median() -> None:
    """p50 of [1..10] = 5.5 (linear interpolation)."""
    values = sorted([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    assert _percentile(values, 50) == 5.5


def test_percentile_p95() -> None:
    """p95 of 100 values 1..100 should be ~95."""
    values = sorted(float(i) for i in range(1, 101))
    p95 = _percentile(values, 95)
    assert 94.0 <= p95 <= 96.0


def test_percentile_empty() -> None:
    """Empty list returns 0.0 (no error)."""
    assert _percentile([], 50) == 0.0
    assert _percentile([], 95) == 0.0


def test_percentile_single() -> None:
    """Single value returns that value."""
    assert _percentile([42.0], 50) == 42.0
    assert _percentile([42.0], 95) == 42.0


def test_check_org_access_multi_tenant_blocks_cross_org() -> None:
    """check_org_access blocks X-Org-Id mismatches in multi-tenant mode."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ORG_A}:{ORG_A};{USER_ORG_B}:{ORG_B}"
    try:
        # Cross-org: caller sends org_b, trace is org_a
        allowed, code = check_org_access(ORG_B, ORG_A)
        assert allowed is False
        assert code == "org_mismatch"

        # Same org: caller sends org_a, trace is org_a
        allowed, code = check_org_access(ORG_A, ORG_A)
        assert allowed is True
        assert code == "ok"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_check_org_access_requires_header_in_multi_tenant() -> None:
    """Multi-tenant + trace has org_id + no X-Org-Id → org_id_required."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ORG_A}:{ORG_A}"
    try:
        allowed, code = check_org_access(None, ORG_A)
        assert allowed is False
        assert code == "org_id_required"
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_check_org_access_disabled_in_single_tenant() -> None:
    """Single-tenant (env unset) skips org checks entirely."""
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ.pop("ECE_USER_ORGS", None)
    try:
        assert is_multi_tenant_mode() is False
        # Any combination should be allowed
        allowed, code = check_org_access(None, None)
        assert allowed is True
        allowed, code = check_org_access("anything", "trace_org")
        assert allowed is True
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved


def test_bench_cross_org_denial_100_percent() -> None:
    """bench_cross_org_denial reports 100% denial rate for cross-org attempts."""
    metrics, denial_pass = bench_cross_org_denial()
    assert denial_pass is True
    assert metrics["denial_rate"] == 1.0
    assert metrics["cross_org_attempts"] >= 10  # at least 10 cross-org attempts
    assert metrics["blocked"] == metrics["cross_org_attempts"]


def test_assemble_context_distinct_org_ids_per_user() -> None:
    """assemble_context records correct org_id for different users in same DB."""
    engine = get_engine()
    saved = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ORG_A}:{ORG_A};{USER_ORG_B}:{ORG_B}"
    try:
        pkg_a = assemble_context(
            engine=engine,
            user_ref=USER_ORG_A,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR_ORG_TEST_A"}],
        )
        pkg_b = assemble_context(
            engine=engine,
            user_ref=USER_ORG_B,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": "PR_ORG_TEST_B"}],
        )

        from ece.audit.trace import get_context_trace

        trace_a = get_context_trace(engine, pkg_a.request_id)
        trace_b = get_context_trace(engine, pkg_b.request_id)
        assert trace_a is not None and trace_a["org_id"] == ORG_A
        assert trace_b is not None and trace_b["org_id"] == ORG_B
    finally:
        if saved is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved
