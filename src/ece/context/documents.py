"""S3.2 step 6 — Document retrieval with permission filter.

Per ARCHITECTURE §3 step 6:
  Retrieve authorized documents: FTS/vector candidates → classification + ACL filter

Cut-011: FTS keyword route only (vector route deferred to cut-012).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.context.spec import ContextSpec
from ece.identity.parser import Identity
from ece.permissions.engine import check_permission


def get_documents(
    engine: Engine,
    spec: ContextSpec,
    identity: Identity,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """FTS-based document retrieval per spec.requires.documents.

    For each RequiredDocument, run a FTS query on doc_chunks.tsv; join
    documents; apply permission filter (classification + ACL).

    Returns list of {doc, chunk, text, snippet, title, src}. Truncated to
    spec.limits.max_chunks.
    """
    if not spec.requires.documents:
        return []

    items: list[dict[str, Any]] = []

    for req_doc in spec.requires.documents:
        # Use doc_type as FTS query (v0 simple heuristic; v1: parse req_doc.match)
        query = req_doc.doc_type.replace("_", " ")

        sql = """
            SELECT dc.document_id, d.display_id, dc.chunk_index, dc.text,
                   d.classification, d.title,
                   ts_rank(dc.tsv, plainto_tsquery('simple', :q)) AS rank
            FROM doc_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE dc.tsv @@ plainto_tsquery('simple', :q)
            ORDER BY rank DESC
            LIMIT :limit
        """

        with engine.connect() as conn:
            rows = conn.execute(
                text(sql), {"q": query, "limit": spec.limits.max_chunks}
            ).fetchall()

        for r in rows:
            doc_id, display_id, chunk_idx, text_content, classification, title, rank = r

            # Permission check (anti-probing: missing = forbidden, uniform envelope)
            # Note: v0 loads no doc-specific ACL (acl_entries table has no doc rows);
            # classification default matrix handles public/department/management/etc.
            decision = check_permission(
                identity=identity,
                object_type="document",
                object_ref=display_id,
                classification=classification,
                acl_entries=[],
            )
            if not decision.allowed:
                continue  # skip denied (uniform envelope; denied[] in package)

            items.append({
                "doc": display_id,
                "chunk": chunk_idx,
                "text": text_content[:200],
                "snippet": text_content[:200],
                "title": title,
                "src": {
                    "system": "docs",
                    "document_id": display_id,
                    "page": chunk_idx,
                },
            })

    return items[: spec.limits.max_chunks]
