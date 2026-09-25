"""OEI-009 — per-result permission filter for engine recall.

This module is the **only** place where engine recall is mapped onto ECE's
permission model. It is intentionally split from `engine_merge.py` so it
can be unit-tested without spinning up an Onyx adapter.

The contract (TASK v1.3 §4 step 2):

  EngineDocument → (engine_name, title, source_type)
                       │
                       ▼
              source_type == "user_file"?
                       │ yes
                       ▼
        registry.lookup_by_engine_filename(engine_name, title)
                       │
       ┌───────────────┴───────────────┐
       │ found                          │ not found
       ▼                                ▼
  run check_permission              hidden_count += 1
  (subject from identity only,     reason="no_registry"
   classification from row)        (FAIL-CLOSED — never reveal)
       │
  ┌────┴────┐
  allowed   denied
  ▼         ▼
  keep      hidden_count += 1
            reason="denied"

  Anonymous identity: only `classification == "public"` rows are allowed
  regardless of ACL entries. (A6: "匿名按最小权限（仅 public 档）".)
  The matrix already defaults internal to allow, but for anonymous the
  filter narrows further — this is the ONE place where "minimum
  permission" is enforced for the anonymous caller.

  Multiple chunks of the same source doc -> one EngineItem. Dedup happens
  here, by `engine_filename` (= the title the engine returned), keeping
  the first EngineDocument we see.

  Side-channel rules (A6):
    - The returned `engine_items` list IS the authorized set. Period.
    - No "hidden N" count surfaced. We only expose `hidden_count` to
      tests / audit, never to the client.
    - Order is the natural order returned by the engine after our
      internal filter; we do NOT add ordering signals based on what got
      dropped.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import text as _sql_text
from sqlalchemy.engine import Engine

from ece.connectors.onyx.port import EngineDocument
from ece.consulting.models import EngineItem
from ece.consulting.registry import RegistryRow, lookup_by_engine_filename
from ece.identity.parser import Identity
from ece.permissions.engine import check_permission


@dataclass
class FilterResult:
    """Internal result of `filter_engine_items`.

    `hidden_count` and `hidden_by_reason` are bookkeeping for the per-result
    audit row (see Step 5 / 09-design-engine-audit.md). They are NEVER
    surfaced to the client.
    """

    allowed_items: list[EngineItem] = field(default_factory=list)
    hidden_count: int = 0
    hidden_by_reason: dict[str, int] = field(default_factory=dict)

    def hide(self, reason: str) -> None:
        self.hidden_count += 1
        self.hidden_by_reason[reason] = self.hidden_by_reason.get(reason, 0) + 1


# Object type used for ACL + check_permission. Distinct from "entity" /
# "document" so an engine doc cannot piggyback on an entity ACL row.
_ENGINE_DOC_OBJECT_TYPE = "engine_document"


def _is_anonymous(identity: Identity | None) -> bool:
    """Anonymous = no authenticated user_ref (header absent AND no JWT).

    Identified via `identity.user_ref` being None or empty string — matches
    what `caller_from_request_headers` produces for an unauthenticated
    request (see connectors/onyx/caller.py).
    """
    if identity is None:
        return True
    ref = (identity.user_ref or "").strip()
    return not ref


def _load_acl_for_engine_doc(
    sql_engine: Engine, registry_id: int
) -> list[dict]:
    """Load all acl_entries rows for one engine_document registry row.

    Reads from `acl_entries` keyed on `object_type='engine_document'` and
    `object_ref='engine_document:<id>'` (RegistryRow.object_ref format).
    Returns a list of dicts shaped like the rows check_permission expects.
    """
    object_ref = f"{_ENGINE_DOC_OBJECT_TYPE}:{registry_id}"
    with sql_engine.connect() as conn:
        rows = conn.execute(
            _sql_text(
                """
                SELECT subject_type, subject_ref, effect, valid_from, valid_to, source_system
                FROM acl_entries
                WHERE object_type = :otype AND object_ref = :oref
                """
            ),
            {"otype": _ENGINE_DOC_OBJECT_TYPE, "oref": object_ref},
        ).fetchall()
    return [
        {
            "subject_type": r[0],
            "subject_ref": r[1],
            "effect": r[2],
            "valid_from": r[3],
            "valid_to": r[4],
            "source_system": r[5],
        }
        for r in rows
    ]


def filter_engine_items(
    items: Iterable[EngineDocument],
    *,
    sql_engine: Engine,
    content_engine_name: str,
    identity: Identity | None,
) -> FilterResult:
    """Per-result permission filter for engine recall.

    Parameters
    ----------
    items:
        EngineDocuments returned by the engine. Order is preserved for the
        caller; this function does not reorder.
    sql_engine:
        SQLAlchemy engine for registry + ACL lookups. Must be connected
        (the consulting router supplies the process-wide engine).
    content_engine_name:
        The Port's `engine_name` (e.g. "onyx"). Used as the registry's
        `engine_name` column.
    identity:
        The authenticated principal. `None` or empty-user_ref is treated
        as anonymous (public-only).

    Returns
    -------
    FilterResult:
        `allowed_items` — DEDUPED by `engine_filename`, one EngineItem per
        registry row. The first EngineDocument wins (we keep the snippet
        / updated_at of the first chunk; the SPA draws the card from the
        card payload only).
        `hidden_count` — number of inputs we filtered out (for audit).
        `hidden_by_reason` — breakdown (`no_registry` / `denied` /
        `non_user_file` / `anonymous_restricted`) for the audit row.
    """
    out = FilterResult()
    seen_filenames: set[str] = set()

    for doc in items:
        # 1. Source-type guard. The contract is "user_file" only — non-file
        #    engine hits (web, slack, ...) cannot be authorized because we
        #    have no registry row for them.
        if (doc.source_type or "") != "user_file":
            out.hide("non_user_file")
            continue

        # 2. Lookup.
        registry_row: RegistryRow | None = lookup_by_engine_filename(
            sql_engine, content_engine_name, doc.title
        )
        if registry_row is None:
            out.hide("no_registry")
            continue

        # 3. Dedup — first chunk wins per engine_filename.
        if registry_row.engine_filename in seen_filenames:
            # already added; don't count as hidden, just collapse
            continue
        seen_filenames.add(registry_row.engine_filename)

        # 4. Anonymous -> public only. Done BEFORE check_permission so the
        #    matrix-defaulted "internal" / "department" rows don't sneak
        #    through. A6 verbatim.
        if _is_anonymous(identity):
            if registry_row.classification == "public":
                _append_allowed(out, doc)
            else:
                out.hide("anonymous_restricted")
            continue

        # 5. Identified: full check_permission.
        acl_entries = _load_acl_for_engine_doc(sql_engine, registry_row.id)
        decision = check_permission(
            identity=identity,
            object_type=_ENGINE_DOC_OBJECT_TYPE,
            object_ref=registry_row.object_ref,
            classification=registry_row.classification,
            acl_entries=acl_entries,
            engine=sql_engine,
        )
        if decision.allowed:
            _append_allowed(out, doc)
        else:
            out.hide("denied")

    return out


def _append_allowed(out: FilterResult, doc: EngineDocument) -> None:
    """Append one allowed EngineDocument as an EngineItem (card payload)."""
    out.allowed_items.append(
        EngineItem(
            engine_doc_id=doc.engine_doc_id,
            title=doc.title,
            snippet=doc.snippet,
            source_type=doc.source_type,
            updated_at=doc.updated_at,
            source="engine",
        )
    )


__all__ = [
    "FilterResult",
    "filter_engine_items",
    "_ENGINE_DOC_OBJECT_TYPE",
]