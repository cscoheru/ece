"""R3 -- 0002 migration: add unique index for relationships.

Per Cline cut-005 §7.4 R3:
- (src_entity_id, relation, dst_entity_id, valid_from) should be unique
  so identical triples inserted twice do not produce duplicate rows.
- backfill: no existing duplicates expected (v0 fresh DB per cut-005)
- downstream: upsert_relationship uses ON CONFLICT DO NOTHING
  (this migration enables that semantic by creating the underlying unique
  constraint that ON CONFLICT targets)
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_relationship_unique"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_relationships_triple
        ON relationships (src_entity_id, relation, dst_entity_id, COALESCE(valid_from, DATE '0001-01-01'))
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_relationships_triple")
