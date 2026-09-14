"""S4.4 — Performance benchmark: /context p95 < 1.5s (per ADR-009 SLA).

Per docs/ARCHITECTURE.md §11 + ADR-009: bench /context endpoint with seed
full; verify p95 < 1.5s on local Docker. If > 1.5s, add indexes / materialized
views (no Redis per ADR-009).

Usage:
    uv run python scripts/perf_bench.py
"""
from __future__ import annotations

import statistics
import sys
import time

from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine

SLA_P95_MS = 1500.0
N_QUERIES = 50


def main() -> int:
    engine = get_engine()

    # Fetch sample PRs (deterministic: first 50 by display_id)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'purchase_request'
                ORDER BY display_id
                LIMIT :limit
            """),
            {"limit": N_QUERIES},
        ).fetchall()
    pr_ids = [r[0] for r in rows]

    if len(pr_ids) < 10:
        print(
            f"ERROR: need ≥10 PRs for bench, got {len(pr_ids)}; run make seed first",
            file=sys.stderr,
        )
        return 1

    # Warm up (5 queries) — exclude from measurement (JIT/connection pool)
    for pr_id in pr_ids[:5]:
        assemble_context(
            engine=engine,
            user_ref="demo-user-procurement",
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": pr_id}],
        )

    # Measure
    latencies_ms: list[float] = []
    for pr_id in pr_ids:
        t0 = time.monotonic()
        assemble_context(
            engine=engine,
            user_ref="demo-user-procurement",
            intent="evaluate_purchase_request",
            entities=[{"type": "purchase_request", "id": pr_id}],
        )
        latencies_ms.append((time.monotonic() - t0) * 1000.0)

    latencies_ms.sort()
    n = len(latencies_ms)
    p50 = latencies_ms[n // 2]
    p95 = statistics.quantiles(latencies_ms, n=20)[18]  # 95th percentile
    p99 = statistics.quantiles(latencies_ms, n=100)[98]  # 99th percentile
    mean = statistics.mean(latencies_ms)

    print(f"S4.4 Perf Bench — /context assembly (N={n}, ADR-009 SLA)")
    print(f"  mean: {mean:.1f}ms")
    print(f"  p50:  {p50:.1f}ms")
    print(f"  p95:  {p95:.1f}ms")
    print(f"  p99:  {p99:.1f}ms")
    print(f"  SLA:  p95 < {SLA_P95_MS}ms — {'PASS' if p95 < SLA_P95_MS else 'FAIL'}")

    return 0 if p95 < SLA_P95_MS else 1


if __name__ == "__main__":
    sys.exit(main())
