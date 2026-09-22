"""S4 (V0 Technical Spike) — `apply_context_update`.

Per `docs/v0/V0_EXECUTION_SPEC.md` §8 (Context Update) and §9 step [6].
Per the binding acceptance criteria for S4 (审验者裁定, 2026-09-21).

Hard contract enforced here (and asserted by `tests/integration/test_v0_apply_context_update.py`):

  - **Re-read is the criterion.** A test that only inspects the UPDATE rowcount is not
    a valid S4 test. The point is to prove that a fresh `assemble_context(...)` reads
    the new business state back.
  - **Address by `source_id` + `source_system`, not display_id.** FER history: display_ids
    drift and silently invalidate tests.
  - **`review_evidence_id` is singular.** The caller chooses one; S2's
    `get_evidence_for_decision` is sorted deterministically.
  - **No new entity is inserted.** The function UPDATEs an existing row; if zero rows
    match, it raises rather than ghost-writing.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

__all__ = ["apply_context_update"]

_REVIEW_KEYS = (
    "review_status",
    "review_decision_id",
    "review_evidence_id",
    "review_updated_at",
)

_UPDATE_SQL = text("""
    UPDATE entities
    SET attributes = COALESCE(attributes, '{}'::jsonb) || jsonb_build_object(
        'review_status',      CAST(:review_status AS text),
        'review_decision_id', CAST(:review_decision_id AS text),
        'review_evidence_id', CAST(:review_evidence_id AS text),
        'review_updated_at',  CAST(:review_updated_at AS text))
    WHERE id = :entity_id
""")


def apply_context_update(
    engine: Engine,
    source_id: str,
    source_system: str,
    decision: Mapping[str, Any],
    evidence_id: str | None,  # cut-042R F4: None allowed for auto_approved
    *,
    zero_evidence_decisions: tuple[str, ...] | None = None,  # cut-043R R5-B2
) -> None:
    """Write the four `review_*` keys onto the entity identified by `(source_id, source_system)`.

    cut-042R F4: `evidence_id` may be None when `decision_value == "auto_approved"`.
    S2 evidence persistence is locked to "only passed conditions produce rows";
    when all conditions fail (e.g. amount < threshold AND quote_count >= REQUIRED),
    evidence_ids is empty. We still need to write `review_status = auto_approved`,
    but `review_evidence_id` is NULL in that case. For `review_required` decisions
    we still require at least one Evidence row (the loop enforces this check).

    cut-043R R5-B2 — generalize: zero-evidence decision_values must be passed
    via `scenario_spec.zero_evidence_decisions` (already enforced by the loop
    upstream); this layer mirrors the allowlist so a misbehaving caller cannot
    write `review_evidence_id=NULL` for an unsupported value.

    Raises:
      * `ValueError` — no entity matches, or more than one matches (refuses to guess).
      * `ValueError` — `decision` is missing required keys.
      * `ValueError` — `evidence_id` is empty AND decision is not on the
        `zero_evidence_decisions` allowlist.
      * `RuntimeError` — the UPDATE did not affect exactly one row.
    """
    decision_value = decision["decision_value"]
    decision_id = decision["decision_id"]
    if not decision_value or not decision_id:
        raise ValueError("decision['decision_value'] and decision['decision_id'] are required")
    # cut-043R R5-B2 — read allowlist from kwargs (caller passes spec.zero_evidence_decisions).
    # Fallback to the historical hard-coded allowlist so legacy callers (V0 spike)
    # keep working without modification.
    allowed = set(zero_evidence_decisions or ("auto_approved",))
    # cut-042R F4 — only decisions on the allowlist may have evidence_id=None.
    if not evidence_id and decision_value not in allowed:
        raise ValueError(
            f"evidence_id is required for decision_value={decision_value!r}; "
            f"only {sorted(allowed)} are allowed zero-evidence decisions "
            f"(set scenario_spec.zero_evidence_decisions to extend)"
        )

    entity_id = _resolve_entity_id(engine, source_id, source_system)
    updated_at = datetime.now(UTC).isoformat()

    with engine.begin() as conn:
        result = conn.execute(
            _UPDATE_SQL,
            {
                "review_status": decision_value,
                "review_decision_id": decision_id,
                # cut-042R F4 — None → jsonb null in attributes
                "review_evidence_id": evidence_id,
                "review_updated_at": updated_at,
                "entity_id": entity_id,
            },
        )
    if result.rowcount != 1:
        # Defensive: SQL must affect exactly the one row we resolved.
        # A future schema change must not silently write nothing.
        raise RuntimeError(
            f"UPDATE affected {result.rowcount} rows; expected 1 (entity_id={entity_id})"
        )


def _resolve_entity_id(engine: Engine, source_id: str, source_system: str) -> Any:
    """Resolve (source_id, source_system) to the entity's primary key.

    Refuses to guess on ambiguity: zero matches and multiple matches both raise.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": source_system},
        ).all()
    if not rows:
        raise ValueError(
            f"no entity with source_id={source_id!r} source_system={source_system!r}"
        )
    if len(rows) > 1:
        raise ValueError(
            f"{len(rows)} entities match source_id={source_id!r} "
            f"source_system={source_system!r}; refusing to guess which one to update"
        )
    return rows[0][0]
