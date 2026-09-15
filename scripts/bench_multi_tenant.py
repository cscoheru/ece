"""S7 — Multi-tenant perf bench + cross-org denial verification (cut-020).

Per ADR-009 SLA: /context assembly p95 < 1.5s on local Docker.

cut-020 extends to multi-tenant: 200 queries split across 2 orgs
(100 each), measuring:
1. Per-org p95 latency (≤ 1.5s SLA per ADR-009)
2. Cross-org /audit denial rate (must be 100% — no false positives)

Usage:
    uv run python scripts/bench_multi_tenant.py [--n 200] [--base-url URL]
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time

from sqlalchemy import text

from ece.api.org import check_org_access, is_multi_tenant_mode
from ece.audit.trace import get_context_trace
from ece.context.assembly import assemble_context
from ece.db import get_engine

SLA_P95_MS = 1500.0
DEFAULT_N = 200
ORG_A = "org_a"
ORG_B = "org_b"
USER_ORG_A = "demo-user-org-a"
USER_ORG_B = "demo-user-org-b"


def _measure_assembly_latency(
    engine, user_ref: str, pr_ids: list[str]
) -> list[float]:
    """Measure assemble_context latency_ms for N queries.

    Returns sorted list of latency_ms values (ms).
    """
    # Warm up (5 queries) — exclude from measurement
    for pr_id in pr_ids[:5]:
        assemble_context(
            engine=engine,
            user_ref=user_ref,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": pr_id}],
        )

    latencies_ms: list[float] = []
    for pr_id in pr_ids:
        t0 = time.monotonic()
        assemble_context(
            engine=engine,
            user_ref=user_ref,
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": pr_id}],
        )
        latencies_ms.append((time.monotonic() - t0) * 1000.0)
    return latencies_ms


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile using linear interpolation."""
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def bench_assembly(n: int = DEFAULT_N) -> tuple[dict, bool]:
    """Run perf bench across 2 orgs (n/2 each).

    Returns (metrics_dict, perf_pass_bool).
    """
    engine = get_engine()
    n_per_org = n // 2

    # Fetch PRs deterministically (first N by display_id)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'purchase_request'
                ORDER BY display_id
                LIMIT :limit
            """),
            {"limit": n},
        ).fetchall()
    pr_ids = [r[0] for r in rows]
    if len(pr_ids) < max(10, n // 4):
        print(
            f"ERROR: need ≥{max(10, n // 4)} PRs for bench N={n}, got {len(pr_ids)}; "
            f"run make seed first",
            file=sys.stderr,
        )
        return {}, False

    pr_org_a = pr_ids[:n_per_org]
    pr_org_b = pr_ids[n_per_org : 2 * n_per_org]

    print(f"S7 Multi-tenant Perf Bench — N={n} (n_per_org={n_per_org})")
    print(f"  Org A: {USER_ORG_A} ({len(pr_org_a)} PRs)")
    print(f"  Org B: {USER_ORG_B} ({len(pr_org_b)} PRs)")
    print()

    latencies_a = _measure_assembly_latency(engine, USER_ORG_A, pr_org_a)
    latencies_a_sorted = sorted(latencies_a)
    latencies_b = _measure_assembly_latency(engine, USER_ORG_B, pr_org_b)
    latencies_b_sorted = sorted(latencies_b)

    p50_a = _percentile(latencies_a_sorted, 50)
    p95_a = _percentile(latencies_a_sorted, 95)
    p99_a = _percentile(latencies_a_sorted, 99)
    mean_a = statistics.mean(latencies_a_sorted)
    p50_b = _percentile(latencies_b_sorted, 50)
    p95_b = _percentile(latencies_b_sorted, 95)
    p99_b = _percentile(latencies_b_sorted, 99)
    mean_b = statistics.mean(latencies_b_sorted)

    perf_pass_a = p95_a < SLA_P95_MS
    perf_pass_b = p95_b < SLA_P95_MS
    perf_pass = perf_pass_a and perf_pass_b

    print("=== Org A ===")
    print(f"  mean: {mean_a:.1f}ms")
    print(f"  p50:  {p50_a:.1f}ms")
    print(f"  p95:  {p95_a:.1f}ms")
    print(f"  p99:  {p99_a:.1f}ms")
    print(f"  SLA:  p95 < {SLA_P95_MS}ms — {'PASS' if perf_pass_a else 'FAIL'}")
    print()
    print("=== Org B ===")
    print(f"  mean: {mean_b:.1f}ms")
    print(f"  p50:  {p50_b:.1f}ms")
    print(f"  p95:  {p95_b:.1f}ms")
    print(f"  p99:  {p99_b:.1f}ms")
    print(f"  SLA:  p95 < {SLA_P95_MS}ms — {'PASS' if perf_pass_b else 'FAIL'}")
    print()
    print(f"=== Combined SLA: {'PASS' if perf_pass else 'FAIL'} ===")

    return {
        "org_a": {
            "mean_ms": mean_a,
            "p50_ms": p50_a,
            "p95_ms": p95_a,
            "p99_ms": p99_a,
            "n": len(latencies_a_sorted),
            "sla_pass": perf_pass_a,
        },
        "org_b": {
            "mean_ms": mean_b,
            "p50_ms": p50_b,
            "p95_ms": p95_b,
            "p99_ms": p99_b,
            "n": len(latencies_b_sorted),
            "sla_pass": perf_pass_b,
        },
        "sla_pass": perf_pass,
    }, perf_pass


def bench_cross_org_denial() -> tuple[dict, bool]:
    """Verify cross-org /audit denial rate is 100%.

    Sets ECE_USER_ORGS multi-tenant config, assembles traces for users
    in org_a and org_b, then checks: for each (caller, trace) pair where
    caller.org != trace.org, check_org_access() must return False.

    Returns (metrics_dict, denial_pass_bool).
    """
    engine = get_engine()

    # Save existing ECE_USER_ORGS, set multi-tenant config
    import os

    saved_orgs = os.environ.get("ECE_USER_ORGS")
    os.environ["ECE_USER_ORGS"] = f"{USER_ORG_A}:{ORG_A};{USER_ORG_B}:{ORG_B}"
    try:
        if not is_multi_tenant_mode():
            print("ERROR: ECE_USER_ORGS not set; cannot test multi-tenant", file=sys.stderr)
            return {"denial_rate": 0.0, "denial_pass": False}, False

        # Assemble 5 traces for org_a, 5 for org_b
        traces_a: list[str] = []
        traces_b: list[str] = []

        for i in range(5):
            pkg_a = assemble_context(
                engine=engine,
                user_ref=USER_ORG_A,
                intent="evaluate_purchase_request",
                entities=[{"type": "purchase_request", "id": f"PR_DEN_{i}"}],
            )
            traces_a.append(pkg_a.request_id)

            pkg_b = assemble_context(
                engine=engine,
                user_ref=USER_ORG_B,
                intent="evaluate_purchase_request",
                entities=[{"type": "purchase_request", "id": f"PR_DEN_B_{i}"}],
            )
            traces_b.append(pkg_b.request_id)

        # Verify traces recorded correct org_id
        for tid in traces_a:
            trace = get_context_trace(engine, tid)
            assert trace is not None and trace["org_id"] == ORG_A, (
                f"Trace {tid} should have org_id={ORG_A}, got {trace}"
            )
        for tid in traces_b:
            trace = get_context_trace(engine, tid)
            assert trace is not None and trace["org_id"] == ORG_B, (
                f"Trace {tid} should have org_id={ORG_B}, got {trace}"
            )

        # Cross-org access attempts (org_a user → org_b trace, etc.)
        cross_attempts = 0
        cross_blocked = 0
        for _tid in traces_a:
            # org_a caller, no X-Org-Id (should be blocked: org_id_required)
            allowed, code = check_org_access(None, ORG_A)
            cross_attempts += 1
            if not allowed:
                cross_blocked += 1

            # org_a caller, X-Org-Id=org_b (mismatch)
            allowed, code = check_org_access(ORG_B, ORG_A)
            cross_attempts += 1
            if not allowed and code == "org_mismatch":
                cross_blocked += 1

            # org_a caller, X-Org-Id=org_a (match — control)
            allowed, _ = check_org_access(ORG_A, ORG_A)
            cross_attempts += 1
            # control case should be allowed; not counted as cross-org block

        for _tid in traces_b:
            allowed, code = check_org_access(None, ORG_B)
            cross_attempts += 1
            if not allowed:
                cross_blocked += 1

            allowed, code = check_org_access(ORG_A, ORG_B)
            cross_attempts += 1
            if not allowed and code == "org_mismatch":
                cross_blocked += 1

            allowed, _ = check_org_access(ORG_B, ORG_B)
            cross_attempts += 1  # control case

        # Compute denial rate for actual cross-org attempts (excluding controls)
        cross_attempts_real = cross_attempts - 10  # subtract 10 control attempts
        denial_rate = cross_blocked / cross_attempts_real if cross_attempts_real else 0.0

        print()
        print("=== Cross-org denial verification ===")
        print(f"  Total attempts:    {cross_attempts}")
        print(f"  Cross-org:        {cross_attempts_real}")
        print(f"  Blocked (403):    {cross_blocked}")
        print(f"  Denial rate:      {denial_rate * 100:.1f}%")
        print(
            f"  Target:           100% — "
            f"{'PASS' if denial_rate == 1.0 else 'FAIL'}"
        )

        return {
            "total_attempts": cross_attempts,
            "cross_org_attempts": cross_attempts_real,
            "blocked": cross_blocked,
            "denial_rate": denial_rate,
            "denial_pass": denial_rate == 1.0,
        }, denial_rate == 1.0
    finally:
        if saved_orgs is None:
            os.environ.pop("ECE_USER_ORGS", None)
        else:
            os.environ["ECE_USER_ORGS"] = saved_orgs


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-tenant perf bench")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="Total PR lookups (split across 2 orgs)")
    parser.add_argument(
        "--base-url", default=None, help="Override ECE_LLM_BASE_URL (None = Mock)"
    )
    parser.add_argument(
        "--skip-cross-org", action="store_true", help="Skip cross-org denial verification"
    )
    args = parser.parse_args()

    if args.base_url:
        import os

        os.environ["ECE_LLM_BASE_URL"] = args.base_url

    print("=============================================")
    print("S7 Multi-tenant Perf Bench + Cross-org Verify")
    print("=============================================")
    print()

    perf_metrics, perf_pass = bench_assembly(n=args.n)

    denial_pass = True
    denial_metrics: dict = {}
    if not args.skip_cross_org:
        denial_metrics, denial_pass = bench_cross_org_denial()

    print()
    print("=============================================")
    if perf_pass and denial_pass:
        print("S7 Multi-tenant Bench: PASS")
        print("=============================================")
        return 0
    print("S7 Multi-tenant Bench: FAIL")
    print("=============================================")
    return 1


if __name__ == "__main__":
    sys.exit(main())
