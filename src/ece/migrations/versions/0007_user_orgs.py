"""0007 — add org_id column to context_requests (cut-019 multi-tenant).

Per cut-019: when ECE_USER_ORGS is configured, context_requests rows
record the user's org_id for cross-org isolation enforcement on
/audit and /debug endpoints.

Nullable to keep backward compatibility with rows recorded before
this migration (org_id=NULL means legacy / single-tenant config).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_user_orgs"
down_revision: str | None = "0006_pg_trgm"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE context_requests ADD COLUMN org_id text")
    op.execute(
        "CREATE INDEX idx_ctx_req_org ON context_requests (org_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ctx_req_org")
    op.execute("ALTER TABLE context_requests DROP COLUMN IF EXISTS org_id")
