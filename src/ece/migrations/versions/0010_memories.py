"""S2.10 (OEI-010) — `memories` table: persistent context memory.

Per TASK §3.1. A memory is a **domain object**, not a cache entry:

  | column                    | meaning                                        |
  |---------------------------|------------------------------------------------|
  | `scope`                   | `user` (owner = one person) / `org` (owner = one org) |
  | `owner_ref`               | user scope -> `user_ref`; org scope -> `org_id` |
  | `statement`               | the remembered text (EXPLICIT writes only)      |
  | `classification`          | existing classification matrix; default `restricted` = DEFAULT DENY |
  | `source` / `source_ref`   | provenance of the write (e.g. `explicit:api`)   |
  | `confidence`              | optional, explicit — never model-derived        |
  | `expires_at`              | NULL = never expires                            |
  | `deleted_at`              | SOFT delete (compliance requires traceability)  |

Why `classification` defaults to `restricted`:
`DEFAULT_CLASSIFICATION_MATRIX` maps `restricted -> default deny`, so a memory
is invisible until an explicit ACL `allow` row exists for it. Visibility is
therefore **fail-closed by construction** — the write path inserts the matching
ACL row in the same transaction (`src/ece/api/memory.py`), and nothing is
readable merely by existing.

Why `deleted_at` and not `DELETE`:
the cut's compliance requirement is "可查看 / 可删除 / **可追溯**". A physical
delete would erase the fact that the memory was once injected into a context
package — `context_items` rows reference `memory:<id>` and must stay
interpretable. `GET /api/v1/memory` hides soft-deleted rows by default and
surfaces the caller's own ones behind `?include_inactive=true`.

Why `UNIQUE (scope, owner_ref, statement)`:
it is the **idempotent create** precondition (TASK §5 步骤 4.3): re-posting the
same statement must return the existing row with `created: false` instead of
growing the table. `statement` is `text` and unbounded, so the index is a real
one — at v1's scale (explicit writes, tens of rows) that is acceptable; a
future cut that ingests bulk memory should switch to a statement digest.

Scope of the table: user-scope rows are keyed on `user_ref`, org-scope rows on
`org_id` — **never both in one column meaning two things**. `owner_ref` holds
whichever the `scope` says; the CHECK on `scope` is what keeps that honest.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_memories"
down_revision: str | Sequence[str] | None = "0009_engine_documents"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE memories (
            id             bigserial PRIMARY KEY,
            -- user = one person owns it; org = everyone in that org sees it.
            scope          text NOT NULL,
            -- user scope -> user_ref; org scope -> org_id (per `scope`).
            owner_ref      text NOT NULL,
            -- The remembered statement. Written EXPLICITLY (API / seed).
            -- There is NO model-extraction path in this cut (TASK §2).
            statement      text NOT NULL,
            -- Existing classification vocabulary. 'restricted' is the default
            -- and maps to default-deny in permissions/engine.py, so a memory
            -- is invisible until an explicit ACL allow row exists.
            classification text NOT NULL DEFAULT 'restricted',
            source         text NOT NULL,          -- e.g. 'explicit:api'
            source_ref     text,                   -- optional external ref
            confidence     numeric(3,2),           -- 0.00..1.00, NULL = unstated
            created_at     timestamptz NOT NULL DEFAULT now(),
            updated_at     timestamptz NOT NULL DEFAULT now(),
            expires_at     timestamptz,            -- NULL = never expires
            deleted_at     timestamptz,            -- soft delete; NULL = live
            CONSTRAINT ck_memories_scope CHECK (scope IN ('user', 'org')),
            CONSTRAINT ck_memories_confidence
                CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            -- Idempotent create: same (scope, owner_ref, statement) -> one row.
            CONSTRAINT uq_memories_scope_owner_ref_statement
                UNIQUE (scope, owner_ref, statement)
        )
    """)
    # Candidate-set lookup for the read step (context/memory.py):
    #   WHERE scope = :s AND owner_ref = :o  (plus the deleted/expires guards)
    op.execute(
        "CREATE INDEX idx_memories_scope_owner ON memories (scope, owner_ref)"
    )
    # The default `GET /api/v1/memory` list and the read step both filter on
    # `deleted_at IS NULL`; the expiry guard is a range on `expires_at`.
    op.execute("CREATE INDEX idx_memories_deleted_at ON memories (deleted_at)")
    op.execute("CREATE INDEX idx_memories_expires_at ON memories (expires_at)")


def downgrade() -> None:
    # CI (.github/workflows/ci.yml:57-60) runs `downgrade base` then
    # `upgrade head` to prove the chain replays, so this must fully drop the
    # table (indexes and constraints go with it).
    op.execute("DROP TABLE IF EXISTS memories")
