"""Export context_requests + context_items for audit/compliance review.

Cut-017 (v0.1): bulk JSON export with --user and --since filters.
Cut-030 (v0.2): adds --org filter (multi-tenant), --until (date range end),
                 and --format csv (1 row per request).
Cut-033 (v0.2): adds --format items-csv (1 row per item, per-resource).

Usage:
    # JSON (default) — single file with nested items
    uv run python scripts/export_audit.py --output audit.json
    uv run python scripts/export_audit.py --output audit.json --user demo-user-procurement
    uv run python scripts/export_audit.py --output audit.json --since 2026-09-01

    # v0.2 additions
    uv run python scripts/export_audit.py --output audit.json --org org_a
    uv run python scripts/export_audit.py --output audit.json --since 2026-09-01 --until 2026-09-30
    uv run python scripts/export_audit.py --output audit.csv --format csv --org org_a
    uv run python scripts/export_audit.py --output items.csv --format items-csv --org org_a

Schema version: 3 (cut-033 adds items-csv format option).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ece.db import get_engine

SCHEMA_VERSION = 3  # cut-033: +items-csv format


def _build_where(
    args: argparse.Namespace,
) -> tuple[str, dict[str, Any]]:
    """Build WHERE clause + params from args."""
    where_clauses: list[str] = []
    params: dict[str, Any] = {}
    if args.user:
        where_clauses.append("user_ref = :user")
        params["user"] = args.user
    if args.org:
        where_clauses.append("org_id = :org")
        params["org"] = args.org
    if args.since:
        where_clauses.append("created_at >= :since")
        params["since"] = args.since
    if args.until:
        where_clauses.append("created_at <= :until")
        params["until"] = args.until
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return where_sql, params


def _fetch_requests(
    engine: Any, where_sql: str, params: dict[str, Any]
) -> list[dict[str, Any]]:
    """Fetch context_requests + items matching filter."""
    with engine.connect() as conn:
        req_rows = conn.execute(
            text(f"""
                SELECT request_id, user_ref, intent, status, counts,
                       latency_ms, created_at, org_id
                FROM context_requests
                {where_sql}
                ORDER BY created_at
            """),
            params,
        ).fetchall()

        requests_data: list[dict[str, Any]] = []
        for r in req_rows:
            item_rows = conn.execute(
                text("""
                    SELECT seq, item_kind, ref, decision, reason, source
                    FROM context_items
                    WHERE request_id = :r
                    ORDER BY seq
                """),
                {"r": r[0]},
            ).fetchall()
            requests_data.append({
                "request_id": str(r[0]),
                "user_ref": r[1],
                "intent": r[2],
                "status": r[3],
                "counts": r[4] if isinstance(r[4], dict) else {},
                "latency_ms": r[5],
                "created_at": r[6].isoformat() if r[6] else "",
                "org_id": r[7],
                "items": [
                    {
                        "seq": i[0],
                        "item_kind": i[1],
                        "ref": i[2],
                        "decision": i[3],
                        "reason": i[4],
                        "source": i[5] if isinstance(i[5], dict) else {},
                    }
                    for i in item_rows
                ],
            })
    return requests_data


def _write_json(
    requests_data: list[dict[str, Any]], args: argparse.Namespace, output: Path
) -> None:
    """Write JSON output with metadata."""
    out = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now().isoformat(),
        "total_requests": len(requests_data),
        "filter": {
            "user": args.user,
            "org": args.org,
            "since": args.since,
            "until": args.until,
        },
        "requests": requests_data,
    }
    output.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Exported {len(requests_data)} context requests to {output} (JSON)")


def _write_csv(
    requests_data: list[dict[str, Any]], output: Path
) -> None:
    """Write CSV output (one row per request, items flattened to JSON cell)."""
    fieldnames = [
        "request_id",
        "user_ref",
        "org_id",
        "intent",
        "status",
        "latency_ms",
        "created_at",
        "counts",
        "items",
    ]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in requests_data:
            row = {k: r.get(k) for k in fieldnames}
            row["counts"] = json.dumps(r["counts"], ensure_ascii=False)
            row["items"] = json.dumps(r["items"], ensure_ascii=False)
            writer.writerow(row)
    print(f"Exported {len(requests_data)} context requests to {output} (CSV)")


def _write_items_csv(
    requests_data: list[dict[str, Any]], output: Path
) -> None:
    """Write items-csv output (one row per item, cut-033).

    Useful for SIEM / compliance tools that want per-item granularity.
    Each row contains request metadata + item fields.
    """
    fieldnames = [
        "request_id",
        "user_ref",
        "org_id",
        "intent",
        "status",
        "latency_ms",
        "created_at",
        "item_seq",
        "item_kind",
        "item_ref",
        "item_decision",
        "item_reason",
        "item_source",
    ]
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in requests_data:
            base = {k: r.get(k) for k in [
                "request_id", "user_ref", "org_id", "intent",
                "status", "latency_ms", "created_at",
            ]}
            for item in r.get("items", []):
                row = dict(base)
                row["item_seq"] = item.get("seq")
                row["item_kind"] = item.get("item_kind")
                row["item_ref"] = item.get("ref")
                row["item_decision"] = item.get("decision")
                row["item_reason"] = item.get("reason")
                src = item.get("source", {})
                row["item_source"] = json.dumps(src, ensure_ascii=False)
                writer.writerow(row)
    total_items = sum(len(r.get("items", [])) for r in requests_data)
    print(
        f"Exported {total_items} items across {len(requests_data)} "
        f"context requests to {output} (items-csv)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export context_requests + context_items (per docs/API.md §8)"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("audit.json"),
        help="Output file path (default: audit.json)",
    )
    parser.add_argument(
        "--user", help="Filter by user_ref (X-User-Id value)",
    )
    parser.add_argument(
        "--org", help="Filter by org_id (multi-tenant, cut-019)",
    )
    parser.add_argument(
        "--since", help="Filter by created_at >= date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until", help="Filter by created_at <= date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--format", "-f", choices=["json", "csv", "items-csv"], default="json",
        help="Output format (default: json; csv=1row/rq; items-csv=1row/item, cut-033)",
    )
    args = parser.parse_args()

    engine = get_engine()
    where_sql, params = _build_where(args)
    requests_data = _fetch_requests(engine, where_sql, params)

    if args.format == "csv":
        _write_csv(requests_data, args.output)
    elif args.format == "items-csv":
        _write_items_csv(requests_data, args.output)
    else:
        _write_json(requests_data, args, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
