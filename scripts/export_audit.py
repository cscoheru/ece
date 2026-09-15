"""Export context_requests + context_items to JSON for audit review (cut-017).

Per docs/API.md §8: "供 Debugger UI 与 `scripts/export_audit.py` 使用".
v0.1 release prep: bulk export for compliance/audit review.

Usage:
    uv run python scripts/export_audit.py --output audit.json
    uv run python scripts/export_audit.py --output audit.json --user demo-user-procurement
    uv run python scripts/export_audit.py --output audit.json --since 2026-09-01
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from ece.db import get_engine


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export context_requests + context_items to JSON (per docs/API.md §8)"
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=Path("audit.json"),
        help="Output file path (default: audit.json)",
    )
    parser.add_argument(
        "--user", help="Filter by user_ref (X-User-Id value)",
    )
    parser.add_argument(
        "--since", help="Filter by created_at >= date (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    engine = get_engine()

    where_clauses: list[str] = []
    params: dict[str, Any] = {}
    if args.user:
        where_clauses.append("user_ref = :user")
        params["user"] = args.user
    if args.since:
        where_clauses.append("created_at >= :since")
        params["since"] = args.since
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with engine.connect() as conn:
        req_rows = conn.execute(
            text(f"""
                SELECT request_id, user_ref, intent, status, counts,
                       latency_ms, created_at
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

    output = {
        "exported_at": datetime.now().isoformat(),
        "total_requests": len(requests_data),
        "filter": {"user": args.user, "since": args.since},
        "requests": requests_data,
    }

    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Exported {len(requests_data)} context requests to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
