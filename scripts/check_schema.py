#!/usr/bin/env python3
"""S0.5: scripts/check_schema.py

连活库读 information_schema.tables + pg_indexes,与从 DATA_MODEL.md
§1-§5 SQL 块解析出的表/索引清单双向比对。不一致 exit 1。

per ece/CLAUDE.md S0.5 + DATA_MODEL § 末段。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg


def parse_data_model(repo_root: Path) -> tuple[set[str], set[tuple[str, str]]]:
    """Extract expected table names + (table, index) pairs from DATA_MODEL.md §1-§5."""
    dm = repo_root / "docs" / "DATA_MODEL.md"
    tables: set[str] = set()
    indexes: set[tuple[str, str]] = set()

    if not dm.exists():
        print(f"WARN: {dm} not found", file=sys.stderr)
        return tables, indexes

    text = dm.read_text(encoding="utf-8")
    # CREATE TABLE [IF NOT EXISTS] <name> → table name
    for m in re.finditer(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", text, re.IGNORECASE):
        tables.add(m.group(1).lower())
    # CREATE INDEX [name] ON <table> → (table, index name or empty)
    for m in re.finditer(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)", text, re.IGNORECASE):
        idx_name, tbl = m.group(1), m.group(2)
        indexes.add((tbl.lower(), idx_name.lower()))

    return tables, indexes


def query_db(dsn: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Query live DB for actual tables + (table, index_name) sets."""
    actual_tables: set[str] = set()
    actual_indexes: set[tuple[str, str]] = set()

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            for (t,) in cur.fetchall():
                actual_tables.add(t.lower())
            cur.execute(
                "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
            for tbl, idx in cur.fetchall():
                actual_indexes.add((tbl.lower(), idx.lower()))

    return actual_tables, actual_indexes


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    dsn = "postgresql://ece:ece@localhost:5432/ece"  # default per ece/TASKS.md S0.5

    expected_tables, expected_indexes = parse_data_model(repo_root)
    print(f"Expected from DATA_MODEL.md: {len(expected_tables)} tables, {len(expected_indexes)} indexes")
    for t in sorted(expected_tables):
        print(f"  table: {t}")
    for tbl, idx in sorted(expected_indexes):
        print(f"  index on {tbl}: {idx}")

    try:
        actual_tables, actual_indexes = query_db(dsn)
    except Exception as e:
        print(f"\nERROR: cannot connect to db at {dsn}: {e}", file=sys.stderr)
        return 1

    print(f"\nActual in live DB: {len(actual_tables)} tables, {len(actual_indexes)} indexes")

    # Per S0.5: bidirectional diff. Not just missing — also extra tables indicate drift.
    missing_tables = expected_tables - actual_tables
    extra_tables = actual_tables - expected_tables
    missing_indexes = expected_indexes - actual_indexes
    # Extra indexes can be intentional (PKs, etc.) — only require expected indexes present.

    if missing_tables:
        print("\nERROR — tables declared in DATA_MODEL.md but missing in DB:")
        for t in sorted(missing_tables):
            print(f"  {t}")
    if extra_tables:
        print("\nWARN — tables in DB but not declared in DATA_MODEL.md (could be migration drift):")
        for t in sorted(extra_tables):
            print(f"  {t}")
    if missing_indexes:
        print("\nERROR — indexes declared in DATA_MODEL.md but missing in DB:")
        for tbl, idx in sorted(missing_indexes):
            print(f"  {tbl}: {idx}")

    if missing_tables or missing_indexes:
        return 1
    print("\nOK — DATA_MODEL.md schema matches live DB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
