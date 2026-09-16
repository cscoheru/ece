"""S4.1 — Document ingestion connector.

Reads local markdown/text files, chunks by paragraphs, persists to
documents + doc_chunks tables. Re-ingest on same display_id replaces
existing chunks (delete + insert) and updates content_sha256 for change
detection.

Per docs/DATA_MODEL.md §4 (documents + doc_chunks):
- documents: metadata (display_id, title, doc_type, classification)
- doc_chunks: text + tsv (GENERATED to_tsvector('simple')) + embedding
  (vector(512)) — embedding deferred to Sprint 4 (vector route); for
  cut-010 only tsv is populated.

Run:
    uv run python scripts/ingest_demo_docs.py
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


CHUNK_SIZE = 500
CHUNK_OVERLAP = 50  # reserved for future use (currently no overlap)


def _chunk_text(content: str) -> list[str]:
    """Paragraph-based chunking: split by \n\n, accumulate to CHUNK_SIZE chars.

    Simple v0 chunker. v1 may use sentence-boundary detection + overlap.
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > CHUNK_SIZE and current:
            chunks.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingest_document(
    engine: Engine,
    *,
    display_id: str,
    title: str,
    doc_type: str,
    source_system: str,
    file_path: str,
    classification: str = "department",
) -> str:
    """Read file, chunk, persist to documents + doc_chunks. Returns document_id (uuid).

    Re-ingest on same display_id: UPSERT document (refresh sha256 + metadata),
    DELETE existing chunks + INSERT new. Idempotent w.r.t. document identity
    (sha256 reflects content).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {file_path}")

    content = path.read_text(encoding="utf-8")
    chunks = _chunk_text(content)
    content_sha = _content_sha256(content)

    with engine.begin() as conn:
        doc_row = conn.execute(
            text("""
                INSERT INTO documents
                    (display_id, title, doc_type, source_system, file_path,
                     classification, content_sha256)
                VALUES (:did, :title, :dt, :ss, :fp, :cls, :sha)
                ON CONFLICT (display_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    doc_type = EXCLUDED.doc_type,
                    source_system = EXCLUDED.source_system,
                    file_path = EXCLUDED.file_path,
                    classification = EXCLUDED.classification,
                    content_sha256 = EXCLUDED.content_sha256,
                    updated_at = now()
                RETURNING id
            """),
            {
                "did": display_id,
                "title": title,
                "dt": doc_type,
                "ss": source_system,
                "fp": file_path,
                "cls": classification,
                "sha": content_sha,
            },
        ).first()
        assert doc_row is not None, "INSERT...RETURNING failed (no row)"
        doc_id = str(doc_row[0])

        # Re-ingest semantics: delete existing chunks then insert new
        conn.execute(
            text("DELETE FROM doc_chunks WHERE document_id = :d"),
            {"d": doc_id},
        )

        for i, chunk_text in enumerate(chunks):
            token_count = len(chunk_text.split())
            conn.execute(
                text("""
                    INSERT INTO doc_chunks
                        (document_id, chunk_index, text, token_count)
                    VALUES (:d, :i, :t, :tc)
                """),
                {
                    "d": doc_id,
                    "i": i,
                    "t": chunk_text,
                    "tc": token_count,
                },
            )

        logger.info(
            f"Ingested {display_id}: {len(chunks)} chunks, "
            f"sha256={content_sha[:12]}, doc_id={doc_id}"
        )

    return doc_id


def search_documents(
    engine: Engine,
    *,
    query: str,
    top_k: int = 10,
    doc_type_filter: str | None = None,
) -> list[dict]:
    """FTS search against doc_chunks.tsv (PostgreSQL 'simple' tokenizer).

    Per docs/ARCHITECTURE.md §4: PostgreSQL FTS via tsvector (GENERATED) +
    to_tsquery('simple', ...) for v0 (zhparser optional per ADR-009 appendix).

    Returns ranked list of dicts:
        {chunk_id, document_id, document_display_id, chunk_index,
         text, snippet, rank}

    Note: 'simple' tokenizer is whitespace-based; Chinese tokenization limited
    in v0. v1 may add bigram fallback or zhparser.
    """
    if not query or not query.strip():
        return []

    terms = [t for t in query.split() if t]
    if not terms:
        return []

    # Build prefix-match tsquery: each term with :* for prefix matching
    ts_query = " & ".join(f"{t}:*" for t in terms)

    params: dict[str, object] = {
        "q": ts_query,
        "limit": top_k,
    }
    type_filter_sql = ""
    if doc_type_filter:
        type_filter_sql = "AND d.doc_type = :dt"
        params["dt"] = doc_type_filter

    sql = f"""
        SELECT dc.id, dc.document_id, d.display_id, dc.chunk_index, dc.text,
               d.classification, d.title,
               GREATEST(
                 ts_rank(dc.tsv, plainto_tsquery('simple', :q)),
                 similarity(dc.text, :q)
               ) AS rank
        FROM doc_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE (
            dc.tsv @@ plainto_tsquery('simple', :q)
            OR dc.text % :q  -- pg_trgm trigram fallback (per cut-012 S4.4)
        )
        {type_filter_sql}
        ORDER BY rank DESC
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    return [
        {
            "chunk_id": r[0],
            "document_id": str(r[1]),
            "document_display_id": r[2],
            "chunk_index": r[3],
            "text": r[4],
            "snippet": r[4][:200],
            "rank": float(r[5]),
        }
        for r in rows
    ]


def search_documents_vector(
    engine: Engine,
    *,
    query_embedding: list[float],
    top_k: int = 10,
    doc_type_filter: str | None = None,
) -> list[dict]:
    """Vector similarity search via pgvector cosine distance.

    Per docs/ARCHITECTURE.md §4 + DATA_MODEL §4: doc_chunks.embedding
    is vector(512) (bge-small-zh-v1.5 default per ADR-009). Cosine distance
    via pgvector `<=>` operator; similarity = 1 - distance.

    Args:
        engine: SQLAlchemy Engine
        query_embedding: 512-dim query vector (caller must pre-compute via
            bge-small-zh-v1.5 or similar; cut-013 v0 has no embedding model)
        top_k: max results
        doc_type_filter: optional doc_type filter

    Returns ranked list of {chunk_id, document_id, document_display_id,
    chunk_index, text, snippet, similarity}. Empty if no docs have embeddings
    (V0: all NULL since no embedding model run yet).

    R3 (cut-035R): wrong-dim embeddings now return [] gracefully instead
    of raising DataError. pgvector strictly enforces dimension match at
    query plan time (BEFORE WHERE filtering), so any non-512-dim input
    fails on the cast even when no rows have embeddings. Caller-friendly
    fallback: log a warning and return [].
    """
    # R3 fix: dim mismatch (non-512-dim input) → return [] with warning
    # instead of letting pgvector raise DataError.
    expected_dim = 512
    if len(query_embedding) != expected_dim:
        logger.warning(
            "search_documents_vector: query_embedding dim=%d != expected %d; returning []",
            len(query_embedding),
            expected_dim,
        )
        return []

    type_filter_sql = ""
    # Serialize embedding as pgvector-compatible string '[a,b,c,...]'
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    params: dict[str, object] = {
        "q_vec": embedding_str,
        "limit": top_k,
    }
    if doc_type_filter:
        type_filter_sql = "AND d.doc_type = :dt"
        params["dt"] = doc_type_filter

    sql = f"""
        SELECT dc.id, dc.document_id, d.display_id, dc.chunk_index, dc.text,
               d.classification, d.title,
               1 - (dc.embedding <=> CAST(:q_vec AS vector)) AS similarity
        FROM doc_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE dc.embedding IS NOT NULL
        {type_filter_sql}
        ORDER BY dc.embedding <=> CAST(:q_vec AS vector)
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    return [
        {
            "chunk_id": r[0],
            "document_id": str(r[1]),
            "document_display_id": r[2],
            "chunk_index": r[3],
            "text": r[4],
            "snippet": r[4][:200],
            "similarity": float(r[5]),
        }
        for r in rows
    ]
