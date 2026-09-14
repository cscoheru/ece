"""Ingest sample procurement policy documents for cut-010 Sprint 4 entry.

Seeds documents from data/demo_docs/*.md into documents + doc_chunks tables.
Run after `make seed`:
    uv run python scripts/ingest_demo_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from ece.connectors.docs import ingest_document
from ece.db import get_engine


def main() -> int:
    engine = get_engine()

    docs_root = Path("data/demo_docs")
    if not docs_root.exists():
        print(f"ERROR: {docs_root} not found", file=sys.stderr)
        return 1

    ingested = []
    for md_file in sorted(docs_root.glob("*.md")):
        # display_id from filename: POL-2026-03.md → POL-2026-03
        display_id = md_file.stem
        title = display_id  # simple title
        doc_type = "procurement_policy" if display_id.startswith("POL-") else "other"

        doc_id = ingest_document(
            engine,
            display_id=display_id,
            title=title,
            doc_type=doc_type,
            source_system="demo:ingest_demo_docs",
            file_path=str(md_file),
            classification="department",
        )
        ingested.append((display_id, doc_id))

    print(f"Ingested {len(ingested)} documents:")
    for did, doc_id in ingested:
        print(f"  {did}: {doc_id}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
