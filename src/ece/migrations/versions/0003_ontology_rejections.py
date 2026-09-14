"""S2.4 ontology rejection log migration.

Per cut-005 §7.4 gap (a): ontology 拒绝 must be persisted for auditability
(E2 = 0 unauthorized exposure + ontology reject trail).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003_ontology_rejections"
down_revision: str | None = "0002_relationship_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ontology_rejections (
            id              bigserial PRIMARY KEY,
            src_display_id  text NOT NULL,
            relation       text NOT NULL,
            dst_display_id  text NOT NULL,
            reason         text NOT NULL,
            rejected_at    timestamp with time zone NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_rejections_at ON ontology_rejections (rejected_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ontology_rejections")
