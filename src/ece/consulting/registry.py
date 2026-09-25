"""OEI-009 — engine_documents registry (read-side + write-side helpers).

This module is the **single owner** of the mapping contract between ECE and
the engine (TASK v1.3 §1.2):

  Write:  `compute_controlled_filename(user_ref, original_filename)`
          -> "ece-<docref>-<slug>.<ext>"  (deterministic, N=5 stable)

  Read:   `lookup_by_engine_filename(engine_name, engine_filename)`
          -> RegistryRow | None

  Register: `register(...)` — INSERT a row, return its primary key id (as int).

The lookup key is **(engine_name, engine_filename)** where `engine_filename`
is exactly what the engine returns in /api/search's `title` field. That is
the *only* viable mapping key in Onyx CE v4.7.8 (see `VERDICT.md` §3 for the
rejection of citation_id / document_id / link / content_sha256).

`engine_document_id` (the Onyx user_file.id UUID returned by upload) is
**stored for write-side traceability only** — it MUST NOT appear in the
read-side lookup. Anyone reading this file should not re-derive the wrong
contract.

DB-freeness: the pure helpers (`compute_controlled_filename`,
`slugify_for_filename`) are DB-free and safe in unit tests. The DB-touching
helpers (`lookup_by_engine_filename`, `register`, `backfill_demo_files`) take
a `sqlalchemy.engine.Engine` parameter explicitly so they can be unit-tested
against a temp PG (see `tests/integration/test_*`) or skipped in DB-free runs.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Engine

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Pure helpers — deterministic filename generation (DB-free, unit-testable).
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_for_filename(stem: str) -> str:
    """Lowercase, collapse non-alphanumeric runs into '-', strip leading/trailing '-'.

    Empty result is replaced with 'doc' so the filename always has a stem.
    Deterministic — same input N=5 produces byte-identical output.
    """
    s = _SLUG_RE.sub("-", (stem or "").lower()).strip("-")
    return s or "doc"


def _docref(user_ref: str, original_filename: str) -> str:
    """Stable 12-char token derived from (user_ref, original_filename).

    Pure function of inputs — same (user, file) → same docref forever.
    We don't reuse the registry row id because:
      (a) we don't have the row id BEFORE the insert, so this can't be the
          value we upload to the engine in the first place;
      (b) we want the filename to be a pure function of the caller's input
          so we can re-derive it for retries / lookups.

    SHA-256 truncated to 12 hex chars = 48 bits. Per-user, per-filename —
    collision probability ~2^-48 * (users * files). For demo scale (single
    user uploading a handful of files) this is fine; if it ever becomes
    tight, bump to 16 chars.
    """
    h = hashlib.sha256()
    h.update((user_ref or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((original_filename or "").encode("utf-8"))
    return h.hexdigest()[:12]


def compute_controlled_filename(
    user_ref: str | None,
    original_filename: str,
) -> str:
    """Return the controlled engine filename for a NEW upload.

    Format: `ece-<docref>-<slug>.<ext>` (TASK v1.3 §1.2 + §4 step 1.3).

    `user_ref` is the upload's authenticated caller — when the route is
    anonymous-rejected this is always non-None, but we accept None for
    test ergonomics and substitute "anon" so the prefix is always stable.

    Determinism: identical (user_ref, original_filename) -> byte-identical
    filename. `compute_controlled_filename(u, n) == compute_controlled_filename(u, n)`
    across calls and processes (verified by A1′).
    """
    if not original_filename:
        raise ValueError("original_filename is empty")
    user_ref = user_ref or "anon"
    base, dot, ext = original_filename.rpartition(".")
    if not dot or not ext:
        raise ValueError(f"original_filename has no extension: {original_filename!r}")
    slug = slugify_for_filename(base)
    docref = _docref(user_ref, original_filename)
    return f"ece-{docref}-{slug}.{ext.lower()}"


# ---------------------------------------------------------------------------
# DB-backed helpers — used by the upload route, the filter layer, and the
# backfill script.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegistryRow:
    """One row of `engine_documents`, shaped for read-side filter use."""

    id: int
    engine_name: str
    engine_project_id: int
    engine_filename: str
    original_filename: str
    engine_document_id: str | None
    title: str | None
    classification: str
    uploaded_by: str
    department: str
    org_id: str | None
    created_at: datetime

    @property
    def object_ref(self) -> str:
        """Stable string to pass as `object_ref` to `check_permission`.

        The registry row id is the stable cross-session identifier for an
        engine document — unlike the engine_filename which is the read-side
        *lookup key* (kept human-readable), this is the *permission decision
        object* (kept opaque + numeric + monotonic). ACL entries key on it.
        """
        return f"engine_document:{self.id}"


_SELECT_BY_FILENAME = text("""
    SELECT id, engine_name, engine_project_id, engine_filename, original_filename,
           engine_document_id, title, classification, uploaded_by, department,
           org_id, created_at
    FROM engine_documents
    WHERE engine_name = :ename AND engine_filename = :fname
    LIMIT 1
""")


def lookup_by_engine_filename(
    engine: Engine,
    engine_name: str,
    engine_filename: str,
) -> RegistryRow | None:
    """Return the registry row for an /api/search result, or None.

    This is the ONLY function that maps a search result to a permission
    decision. Callers MUST call this for every result before deciding to
    surface it.
    """
    with engine.connect() as conn:
        row = conn.execute(
            _SELECT_BY_FILENAME,
            {"ename": engine_name, "fname": engine_filename},
        ).first()
    if row is None:
        return None
    return RegistryRow(
        id=int(row[0]),
        engine_name=str(row[1]),
        engine_project_id=int(row[2]),
        engine_filename=str(row[3]),
        original_filename=str(row[4]),
        engine_document_id=str(row[5]) if row[5] is not None else None,
        title=str(row[6]) if row[6] is not None else None,
        classification=str(row[7]),
        uploaded_by=str(row[8]),
        department=str(row[9]),
        org_id=str(row[10]) if row[10] is not None else None,
        created_at=row[11],
    )


def register(
    engine: Engine,
    *,
    engine_name: str,
    engine_project_id: int,
    engine_filename: str,
    original_filename: str,
    engine_document_id: str | None,
    title: str | None,
    classification: str,
    uploaded_by: str,
    department: str = "",
    org_id: str | None = None,
) -> int:
    """INSERT a registry row. Returns the new row's primary key id.

    Idempotency: `ON CONFLICT (engine_name, engine_filename) DO UPDATE SET
    engine_document_id = EXCLUDED.engine_document_id` so a retry of the
    same controlled filename re-uses the same row (the engine_document_id
    is the Onyx UUID and may change between upload attempts if the prior
    one was orphaned by Onyx's GC). The id is stable across retries.
    """
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                INSERT INTO engine_documents (
                    engine_name, engine_project_id, engine_filename, original_filename,
                    engine_document_id, title, classification, uploaded_by,
                    department, org_id
                )
                VALUES (
                    :engine_name, :engine_project_id, :engine_filename, :original_filename,
                    :engine_document_id, :title, :classification, :uploaded_by,
                    :department, :org_id
                )
                ON CONFLICT (engine_name, engine_filename) DO UPDATE
                  SET engine_document_id = EXCLUDED.engine_document_id,
                      title              = EXCLUDED.title
                RETURNING id
            """),
            {
                "engine_name": engine_name,
                "engine_project_id": engine_project_id,
                "engine_filename": engine_filename,
                "original_filename": original_filename,
                "engine_document_id": engine_document_id,
                "title": title,
                "classification": classification,
                "uploaded_by": uploaded_by,
                "department": department,
                "org_id": org_id,
            },
        ).first()
    return int(row[0])


_COUNT = text("SELECT COUNT(*) FROM engine_documents WHERE engine_name = :ename")


def count_rows(engine: Engine, engine_name: str = "onyx") -> int:
    """Total number of registry rows for one engine. For backfill checks."""
    with engine.connect() as conn:
        return int(conn.execute(_COUNT, {"ename": engine_name}).scalar() or 0)


def backfill_demo_files(
    engine: Engine,
    *,
    demo_files: list[dict],
    engine_name: str = "onyx",
    engine_project_id: int = 1,
    classification: str = "public",
    uploaded_by: str = "system:backfill",
) -> int:
    """Idempotent backfill of historical files (TASK v1.3 §4 step 1.4).

    Each `demo_files` row is `{"engine_filename": ..., "original_filename": ...,
    "engine_document_id": ..., "title": ...}` — typically obtained from
    `GET /api/user/projects/files/1`. Existing rows (matched by
    (engine_name, engine_filename)) are kept; their `engine_document_id` is
    refreshed if a new one is provided.

    Returns the total row count AFTER backfill (so a second call with the
    same input shows the same number → A3 "零新增" verification).
    """
    for f in demo_files:
        register(
            engine,
            engine_name=engine_name,
            engine_project_id=engine_project_id,
            engine_filename=str(f["engine_filename"]),
            original_filename=str(f.get("original_filename") or f["engine_filename"]),
            engine_document_id=f.get("engine_document_id"),
            title=f.get("title"),
            classification=classification,
            uploaded_by=uploaded_by,
        )
    return count_rows(engine, engine_name)


__all__ = [
    "RegistryRow",
    "compute_controlled_filename",
    "slugify_for_filename",
    "lookup_by_engine_filename",
    "register",
    "count_rows",
    "backfill_demo_files",
]