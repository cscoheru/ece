"""S2 (V0 Technical Spike) — Evidence persistence.

Answers exactly one question: **which Evidence rows support this Decision, and where
did each of them come from?** That is the reverse chain `docs/v0/V0_EXECUTION_SPEC.md`
§10.1 requires:

    decision_id -> evidence_id -> (source.system, source.record_id, input_context_ref)
                -> the original Context package

Scope is locked by the Codex ruling on that spec: minimal persistence plus that one
lookup. Explicitly **not** an Evidence framework — no ranking, search, graph,
versioning or UI. Nothing here exists because it "might be needed later".

Why this is separate from `context_items`: that table is engineering audit, this one
holds *business* evidence. `KERNEL_BOUNDARY.md` §5 requires the two stay distinct —
"what did the pipeline do" is answerable by a trace, "what does this conclusion rest
on" is not.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

if TYPE_CHECKING:
    from ece.context.assembly import ContextPackage

__all__ = ["get_evidence_for_decision", "persist_evidence"]

_INSERT = text("""
    INSERT INTO evidence_records
        (evidence_id, decision_id, rule_id, claim,
         source_system, source_record_id, observed_value, threshold_value,
         actor_user_ref, input_context_ref, evidence_timestamp)
    VALUES
        (:evidence_id, :decision_id, :rule_id, :claim,
         :source_system, :source_record_id, :observed_value, :threshold_value,
         :actor_user_ref, :input_context_ref, :evidence_timestamp)
""")

_SELECT_BY_DECISION = text("""
    SELECT evidence_id, decision_id, rule_id, claim,
           source_system, source_record_id, observed_value, threshold_value,
           actor_user_ref, input_context_ref, evidence_timestamp
    FROM evidence_records
    WHERE decision_id = :decision_id
    ORDER BY evidence_timestamp, claim
""")

# The spec fixes the evidence id shape as `ev_<uuid>` (§7), matching `dec_<uuid>` /
# `ctx_<24hex>` used by the other objects.
_EVIDENCE_ID_PREFIX = "ev_"

# cut-042R F2 — production code path (v0/loop.py) passes `subject_entity_type`
# explicitly via `scenario_spec.subject_entity_type`. The kwarg default exists
# only for backward compat with the 47 V0 spike regression tests, which build
# contexts with a single purchase_request entity and expect the engine to
# default to that subject type. This is a test-fixture convenience, NOT a
# runtime code hardcode — production never relies on it. See
# `tests/integration/test_v0_evidence_persistence.py` for the fixture pattern.

_DEFAULT_SUBJECT_ENTITY_TYPE = "purchase_request"


def persist_evidence(
    engine: Engine,
    ctx: ContextPackage,
    decision: Mapping[str, Any],
    *,
    subject_entity_type: str = _DEFAULT_SUBJECT_ENTITY_TYPE,  # see note above
) -> list[dict[str, Any]]:
    """Write one Evidence row per PASSED condition of `decision`.

    Returns the rows written (same shape the table holds), so the caller can assert on
    them without a re-read. Conditions that did not pass produce no Evidence — a
    condition that failed is not something the conclusion rests on.

    Assumptions, each of which raises rather than guessing:

    * **Exactly one subject entity** (param `subject_entity_type`) in the Context.
      Every Evidence row points at one subject. Zero or several would make the
      subject ambiguous, so this refuses instead of picking one.
    * **`ctx.user.id` is set.** That is the original `X-User-Id` (see
      `Identity.user_ref`), and it is what §7's `actor_user_ref` records.
    * **Passed conditions carry `claim` / `actual` / `threshold`.** The spec's §6
      condition example lists only `name`/`expr`/`actual`/`passed`, while §7 requires
      `claim` and `threshold` on the Evidence — and a claim like "报价家数 1 < 3" cannot
      be derived from an expression string. The rule therefore emits those two keys
      alongside the four; see the note in the S2 report.

    cut-042R F2: `subject_entity_type` is keyword-only and the production code
    path (`run_demo_loop_impl`) passes it explicitly from `scenario_spec`.
    The legacy default `_DEFAULT_SUBJECT_ENTITY_TYPE` is retained only for
    backward compatibility with the 47 V0 spike regression tests.
    """
    decision_id = _required(decision, "decision_id")
    rule_id = _required(decision, "rule_id")
    input_context_ref = _required(decision, "input_context_ref")

    conditions = decision.get("evaluated_conditions")
    if not isinstance(conditions, list):
        raise ValueError("decision['evaluated_conditions'] must be a list")

    actor_user_ref = _actor(ctx)
    subject = _subject_entity(ctx, subject_entity_type)
    source = subject.get("src") or {}
    source_system = str(source.get("system") or "")
    source_record_id = str(source.get("record_id") or "")
    if not source_system or not source_record_id:
        raise ValueError(
            "the subject entity carries no provenance "
            f"(src.system / src.record_id); Evidence cannot record where it came from "
            f"(entity ref={subject.get('ref')!r})"
        )

    timestamp = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for condition in conditions:
        if not condition.get("passed"):
            continue
        rows.append(
            {
                "evidence_id": f"{_EVIDENCE_ID_PREFIX}{uuid.uuid4()}",
                "decision_id": decision_id,
                "rule_id": rule_id,
                "claim": _condition_claim(condition),
                "source_system": source_system,
                "source_record_id": source_record_id,
                "observed_value": condition.get("actual"),
                "threshold_value": condition.get("threshold"),
                "actor_user_ref": actor_user_ref,
                "input_context_ref": input_context_ref,
                "evidence_timestamp": timestamp,
            }
        )

    if not rows:
        return []

    with engine.begin() as conn:
        conn.execute(_INSERT, rows)
    return rows


def get_evidence_for_decision(engine: Engine, decision_id: str) -> list[dict[str, Any]]:
    """Walk the reverse chain: decision -> its Evidence -> where each came from.

    Ordering is by `(evidence_timestamp, claim)` rather than insertion order: the
    spec's minimal schema has no sequence field, and callers on this path need a
    stable result more than they need the original write order.
    """
    with engine.connect() as conn:
        rows = conn.execute(_SELECT_BY_DECISION, {"decision_id": decision_id}).mappings().all()
    return [dict(r) for r in rows]


def _required(decision: Mapping[str, Any], key: str) -> str:
    value = decision.get(key)
    if not value:
        raise ValueError(f"decision[{key!r}] is required to persist Evidence")
    return str(value)


def _actor(ctx: ContextPackage) -> str:
    user = ctx.user or {}
    actor = user.get("id")
    if not actor:
        raise ValueError(
            "ctx.user['id'] (the original X-User-Id) is required as the Evidence actor"
        )
    return str(actor)


def _subject_entity(ctx: ContextPackage, subject_entity_type: str) -> dict[str, Any]:
    subjects = [e for e in ctx.entities if e.get("type") == subject_entity_type]
    if len(subjects) != 1:
        raise ValueError(
            f"expected exactly one {subject_entity_type!r} in the Context, "
            f"found {len(subjects)} — Evidence needs an unambiguous subject"
        )
    return subjects[0]


def _condition_claim(condition: Mapping[str, Any]) -> str:
    claim = condition.get("claim")
    if not claim:
        raise ValueError(
            "a passed condition must carry 'claim' — Evidence records the business "
            f"statement being relied on, not just the expression: {condition!r}"
        )
    return str(claim)
