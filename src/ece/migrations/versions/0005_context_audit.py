"""S3.3 — context_requests + context_items tables (DATA_MODEL §5).

Audit trail for Context Assembly:
- context_requests: per-call row (user_ref, intent, counts, status, latency).
- context_items: per-included/denied row (request_id, item_kind, ref, source,
                 decision, reason, score).

Per ADR-004 + DATA_MODEL §5; enables /audit/context/{request_id} + Debugger UI
(Sprint 6).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_context_audit"
down_revision: str | None = "0004_resolution_pending"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE context_requests (
            request_id   uuid PRIMARY KEY,
            user_ref     text NOT NULL,
            intent       text NOT NULL,
            spec_version int,
            root_entities jsonb NOT NULL DEFAULT '[]',
            as_of        date,
            counts       jsonb NOT NULL DEFAULT '{}',
            latency_ms   int,
            llm_model    text,
            status       text NOT NULL DEFAULT 'ok',
            created_at   timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_ctx_req_user ON context_requests (user_ref, created_at DESC)")
    op.execute("CREATE INDEX idx_ctx_req_status ON context_requests (status, created_at DESC)")

    op.execute("""
        CREATE TABLE context_items (
            id        bigserial PRIMARY KEY,
            request_id uuid NOT NULL REFERENCES context_requests(request_id) ON DELETE CASCADE,
            seq       int NOT NULL,
            item_kind text NOT NULL,
            ref       text NOT NULL,
            source    jsonb NOT NULL DEFAULT '{}',
            decision  text NOT NULL,
            reason    text,
            score     numeric(8,4)
        )
    """)
    op.execute("CREATE INDEX idx_citems_req ON context_items (request_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS context_items")
    op.execute("DROP TABLE IF EXISTS context_requests")
