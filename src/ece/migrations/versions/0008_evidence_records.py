"""S2 (V0 Technical Spike) — `evidence_records` table.

Per `docs/v0/V0_EXECUTION_SPEC.md` §7 (Evidence 最小 schema).

Why a NEW table, and why this is NOT a new Kernel object
--------------------------------------------------------
Evidence is one of the V3 Kernel's five core objects (`V3_CLOSEOUT.md` §1.2), so this
table **implements an already-defined object** rather than introducing a concept.
It deliberately does NOT reuse `context_items`: that table is *engineering* audit
(`item_kind` / `score` / request bookkeeping), while `KERNEL_BOUNDARY.md` §5 requires
**Business Evidence ≠ engineering trace**. The two answer different questions —
"what did the pipeline do" vs "what does this business conclusion rest on" — and
merging them would destroy the distinction the Kernel is supposed to own.

Scope
-----
Locked by the Codex ruling on the V0 spec: minimal persistence plus the single reverse
lookup §10.1 needs (`decision_id → evidence → source → input_context_ref`).
No ranking / search / graph / versioning / UI.

Column names vs the spec's JSON keys
------------------------------------
`source` is stored flattened (`source_system`, `source_record_id`) so the traceability
query can filter on it; `threshold` becomes `threshold_value` and `timestamp` becomes
`evidence_timestamp` because both are PostgreSQL type names and unqualified use as
column names invites ambiguity.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_evidence_records"
down_revision: str | None = "0007_user_orgs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE evidence_records (
            evidence_id        text PRIMARY KEY,
            decision_id        text NOT NULL,
            rule_id            text NOT NULL,
            claim              text NOT NULL,
            source_system      text NOT NULL,
            source_record_id   text NOT NULL,
            observed_value     numeric,
            threshold_value    numeric,
            actor_user_ref     text NOT NULL,
            input_context_ref  text NOT NULL,
            evidence_timestamp timestamptz NOT NULL,
            created_at         timestamptz NOT NULL DEFAULT now()
        )
    """)
    # The reverse chain the spec's traceability test walks starts here.
    op.execute("CREATE INDEX idx_evidence_decision ON evidence_records (decision_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evidence_records")
