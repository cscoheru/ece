"""S2.3 R4 (cut-006 §7.3): pending resolution queue table."""
from collections.abc import Sequence

from alembic import op

revision: str = "0004_resolution_pending"
down_revision: str | None = "0003_ontology_rejections"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE resolution_pending (
            id              bigserial PRIMARY KEY,
            mention        text NOT NULL,
            entity_type    text,
            candidates     jsonb NOT NULL DEFAULT '[]',
            status         text NOT NULL DEFAULT 'pending',
            created_at     timestamp with time zone NOT NULL DEFAULT now(),
            resolved_at    timestamp with time zone
        )
    """)
    op.execute("CREATE INDEX idx_pending_status ON resolution_pending (status, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resolution_pending")
