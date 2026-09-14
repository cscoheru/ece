"""S4.4 — Chinese tokenization via pg_trgm.

Adds pg_trgm extension + GIN trigram index on doc_chunks.text.

Trigrams (3-char sliding window) provide language-agnostic substring search:
- English "compare" matches via bigram/trigram overlap
- Chinese "采购" matches "采购比价" via shared 2-char trigrams

Per ADR-009 appendix + cut-010 §4.3: V0 FTS simple tokenizer only supports
English well; pg_trgm adds Chinese (and other non-whitespace languages) support
without requiring zhparser extension.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_pg_trgm"
down_revision: str | None = "0005_context_audit"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_chunks_trgm ON doc_chunks
        USING gin (text gin_trgm_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunks_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
