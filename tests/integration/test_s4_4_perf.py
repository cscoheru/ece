"""S4.4 — Performance benchmark test: p95 < 1.5s SLA (per ADR-009).

Verifies /context assembly meets latency SLA on seed-full data.
Cut-012 also covers this via scripts/perf_bench.py; test is for CI.

Per docs/ARCHITECTURE.md §11 + ADR-009: bench /context with seed full;
verify p95 < 1.5s on local Docker. If > 1.5s, add indexes / materialized
views (no Redis per ADR-009).
"""
from __future__ import annotations

import statistics
import time

import pytest
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine

SLA_P95_MS = 1500.0
N_QUERIES = 30  # smaller than bench script (N=50) for CI speed


def test_perf_p95_under_1_5s() -> None:
    """Verify p95 < 1.5s for /context assembly (per ADR-009 SLA)."""
    engine = get_engine()
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

    if len(pr_ids) < 5:
        pytest.skip(f"need ≥5 PRs for bench, got {len(pr_ids)}; run make seed first")

    # Warm up (3 queries) — exclude from measurement
    for pr_id in pr_ids[:3]:
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

    p95 = statistics.quantiles(latencies_ms, n=20)[18]  # 95th percentile
    assert p95 < SLA_P95_MS, (
        f"p95 latency {p95:.1f}ms exceeds {SLA_P95_MS}ms SLA "
        f"(n={len(pr_ids)} queries on demo seed)"
    )
