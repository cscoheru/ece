"""S2.9 (OEI-009) — `engine_documents` registry table.

Per TASK v1.3 §1.2 (mapping contract, set by codex after step 1.1 停手):

  Write side: ECE generates a *controlled* engine filename
              `ece-<docref>-<slug>.<ext>` where docref = first 12 chars
              of sha256(user_ref + original_filename).
              -> `engine_filename` (UNIQUE with engine_name)

  Read  side: /api/search result `title` (= the engine filename Onyx returns
              for each chunk) -> lookup `(engine_name, engine_filename)`.
              If found -> `check_permission(identity, object_type='engine_document',
              object_ref=<registry row primary key as text>, classification=row.classification)`.
              If NOT found -> fail-closed (drop the result, do NOT expose
              existence via count/order/title/snippet).

  Multiple chunks: same `title` in one query -> one registry row ->
  one permission decision -> one EngineItem. Per-row dedup happens at the
  filter layer, NOT at the engine layer (engine returns whatever it returns;
  ECE decides what to show).

Why a new table and not an extension to `documents`:
- `documents` is the *native ingest* path (doc_chunks / FTS / vector),
  read by `context/assembly.py`. Stuffing engine pointers into it would
  couple a *replaceable* engine to the *native* pipeline — exactly the
  boundary `port.py` is designed to protect.
- Backfill semantics differ: backfilled rows use the *existing*
  `engine_filename` (= the historical title in Onyx), which does not
  start with `ece-`. So the column must be free-form text.

Why `(engine_name, engine_filename)` unique and not
`(engine_name, engine_document_id)`:
- `engine_document_id` is the Onyx user_file.id (write-side UUID) and
  is *not* returned by /api/search. It exists only for write-side
  traceability. It MUST NOT appear in the lookup path — comment in
  `registry.py` says so.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_engine_documents"
down_revision: str | Sequence[str] | None = "0008_evidence_records"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE engine_documents (
            id                bigserial PRIMARY KEY,
            engine_name       text NOT NULL,
            engine_project_id int    NOT NULL,
            -- The name Onyx returns for this doc's chunks in /api/search.
            -- For new uploads: 'ece-<docref>-<slug>.<ext>'.
            -- For backfilled historical docs: the historical title verbatim.
            -- (Engine-side NOT a path; just a stable string id.)
            engine_filename   text NOT NULL,
            -- The name the *caller* gave (kept for display). May differ from
            -- engine_filename (always differs for new uploads).
            original_filename text NOT NULL,
            -- Onyx user_file.id (UUID). WRITE-SIDE traceability only.
            -- NEVER used in the read-side lookup path; see registry.py.
            engine_document_id text,
            title             text,
            content_sha256    text,
            classification    text NOT NULL DEFAULT 'public',
            uploaded_by       text NOT NULL,
            department        text NOT NULL DEFAULT '',
            org_id            text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            UNIQUE (engine_name, engine_filename)
        )
    """)
    op.execute(
        "CREATE INDEX idx_engine_docs_project ON engine_documents (engine_project_id)"
    )
    op.execute(
        "CREATE INDEX idx_engine_docs_uploader ON engine_documents (uploaded_by)"
    )
    # For the read-side lookup path: we ALWAYS join by (engine_name, engine_filename).
    # The UNIQUE constraint already covers this; the index below makes the lookup
    # fast even when the table grows.
    op.execute(
        "CREATE INDEX idx_engine_docs_lookup ON engine_documents (engine_name, engine_filename)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS engine_documents")