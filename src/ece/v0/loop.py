"""S5 (V0 Technical Spike) — six-step loop orchestrator.

Per `docs/v0/V0_EXECUTION_SPEC.md` §9 (the six steps), §10 (per-step verifications),
§11 (end-to-end output shape). Per the binding acceptance criteria for S5.

Hard contract enforced here (and asserted by `tests/integration/test_v0_loop.py`):

  - **The loop closes back onto Context.** Step [6] is followed by a re-read that goes
    back through `assemble_context` — the same path step [1] used — not by inspecting
    `apply_context_update`'s return value. A raw-SQL read of the same row is kept as a
    second, independent source; if the two disagree the assembly path and the row have
    diverged and the loop refuses to report success.
  - **Decision stays deterministic.** The function never routes through a model gateway.
  - **No new abstraction.** The function is straight orchestration: it calls the
    existing S2 (`persist_evidence` / `get_evidence_for_decision`), S3 (`evaluate_rule`
    / `build_decision`), and S4 (`apply_context_update`) functions. It does not
    introduce a request abstraction or a runtime wrapper.
  - **Address by `source_id`.** We resolve the `display_id` for `assemble_context`
    via `(source_id, source_system)`; `display_id` itself is never hard-coded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.context.assembly import assemble_context
from ece.context.update import apply_context_update
from ece.db import get_engine
from ece.domain_packs.procurement.agent.v0_rules import (
    DECISION_KEY,
    RULE_ID,
    build_decision,
    evaluate_rule_R_SPIKE_REVIEW,
)
from ece.evidence import get_evidence_for_decision, persist_evidence

__all__ = ["V0LoopResult", "run_v0_loop"]

# Hard-coded for the V0 spike. The fixture's PR lives in this source_system; the loop
# would need a different resolver to support other fixtures, which is post-V0 work.
SPIKE_SOURCE_SYSTEM = "spike:v0-technical-fixture"

# The four keys §8 writes back. Kept here so the re-read cross-check names them once.
REVIEW_KEYS = (
    "review_status",
    "review_decision_id",
    "review_evidence_id",
    "review_updated_at",
)


@dataclass
class V0LoopResult:
    """The closed-loop artifact (§10): every step's product, in one shape.

    The field set mirrors §10's per-step table so that a caller (the §11 script, a
    test) never has to re-derive a step's output by calling the engine again — which
    would be a second implementation of the loop.
    """

    package_id: str
    reason: str
    # [1] CONTEXT
    counts: dict[str, int] = field(default_factory=dict)
    denied: list[dict[str, Any]] = field(default_factory=list)
    # [2] ENTITY / KNOWLEDGE
    pr_ref: str | None = None
    pr_attrs_before: dict[str, Any] = field(default_factory=dict)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    quote_refs: list[dict[str, str]] = field(default_factory=list)
    # [3] RULE
    rule_id: str = RULE_ID
    conditions: list[dict[str, Any]] = field(default_factory=list)
    # [4] DECISION
    decision: dict[str, Any] | None = None
    # [5] EVIDENCE
    evidence: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    # [6] CONTEXT UPDATE + RE-READ
    re_read_attrs: dict[str, Any] = field(default_factory=dict)


def run_v0_loop(
    user_ref: str,
    pr_source_id: str,
    *,
    engine: Engine | None = None,
) -> V0LoopResult:
    """Chain the six steps of `V0_EXECUTION_SPEC.md` §9.

    [1] assemble_context
    [2] extract PR + quotes; if denied and no permitted pr, return early
    [3] evaluate_rule_R_SPIKE_REVIEW
    [4] build_decision
    [5] persist_evidence
    [6] apply_context_update (using the first Evidence row's id)
        + re-read through `assemble_context` and verify §8's invariant
    """
    if engine is None:
        engine = get_engine()

    display_id = _resolve_display_id(engine, pr_source_id)

    # [1]
    ctx = assemble_context(
        engine, user_ref, "evaluate_purchase_request",
        [{"type": "purchase_request", "id": display_id}], pack="procurement",
    )

    # [2]
    pr = next((e for e in ctx.entities if e["type"] == "purchase_request"), None)
    quotes = [r for r in ctx.relationships if r["rel"] == "SELECTS"]

    counts = {"entities": len(ctx.entities), "relationships": len(ctx.relationships)}

    if ctx.denied and pr is None:
        # Nothing the rule may see. The attrs are still read (unpermissioned state
        # inspection is not part of this branch's contract) so a caller can show that
        # the DB was left untouched.
        return V0LoopResult(
            package_id=ctx.package_id,
            reason="no permitted context",
            counts=counts,
            denied=ctx.denied,
            pr_ref=display_id,
            pr_attrs_before=_read_pr_attrs(engine, display_id),
            decision=None,
            evidence=[],
            evidence_ids=[],
            re_read_attrs=_read_pr_attrs(engine, display_id),
        )

    # mypy cannot narrow `pr` across the compound `and` above; the early return is the
    # narrowing. The assert makes that invariant explicit to the type checker rather
    # than casting it away.
    assert pr is not None, "unreachable: the denied branch returned when pr was None"

    pr_attrs_before = dict(pr["attrs"])

    # [3] [4]
    conditions = evaluate_rule_R_SPIKE_REVIEW(pr["attrs"]["amount"], len(quotes))
    dec = build_decision(conditions, ctx)

    # [5]
    persist_evidence(engine, ctx, dec)
    rows = get_evidence_for_decision(engine, dec["decision_id"])
    evidence_ids = [r["evidence_id"] for r in rows]

    # [6] (evidence_id = first row per the S4 ruling; do not deviate from §8)
    apply_context_update(engine, pr_source_id, SPIKE_SOURCE_SYSTEM, dec, evidence_ids[0])

    re_read_attrs = _re_read_through_assembly(engine, user_ref, display_id)
    _assert_loop_closed(dec, re_read_attrs, engine, display_id)

    return V0LoopResult(
        package_id=ctx.package_id,
        reason="ok",
        counts=counts,
        denied=ctx.denied,
        pr_ref=display_id,
        pr_attrs_before=pr_attrs_before,
        quotes=quotes,
        quote_refs=_resolve_source_refs(engine, [q["to"] for q in quotes]),
        conditions=conditions,
        decision=dec,
        evidence=rows,
        evidence_ids=evidence_ids,
        re_read_attrs=re_read_attrs,
    )


def _re_read_through_assembly(engine: Engine, user_ref: str, display_id: str) -> dict[str, Any]:
    """Step [6]'s re-read: ask the assembly path again.

    Reading the row back through `assemble_context` is what makes this a *closed loop*
    rather than "we wrote and then we read". A raw SQL read proves the row moved; it
    does not prove the Context path surfaces the new state, which is the thing V3's
    `Context Update` actually promises.
    """
    re_ctx = assemble_context(
        engine, user_ref, "evaluate_purchase_request",
        [{"type": "purchase_request", "id": display_id}], pack="procurement",
    )
    re_pr = next((e for e in re_ctx.entities if e["type"] == "purchase_request"), None)
    if re_pr is None:
        raise RuntimeError(
            "re-read lost the PR: after the update the assembly path no longer returns "
            f"{display_id!r} (denied={re_ctx.denied})"
        )
    return dict(re_pr["attrs"])


def _assert_loop_closed(
    dec: dict[str, Any],
    re_read_attrs: dict[str, Any],
    engine: Engine,
    display_id: str,
) -> None:
    """§8's invariant, plus a second independent reading of the same row.

    Two sources for one fact: the assembly path (what a caller would see) and a raw
    SELECT (what the table holds). They are produced by different code, so agreement
    is evidence and disagreement is a bug — either way this is not self-reporting.
    """
    if re_read_attrs.get(DECISION_KEY) != dec["decision_value"]:
        raise RuntimeError(
            f"loop did not close: re-read {DECISION_KEY}={re_read_attrs.get(DECISION_KEY)!r} "
            f"!= decision_value={dec['decision_value']!r}"
        )

    direct = _read_pr_attrs(engine, display_id)
    for key in REVIEW_KEYS:
        if direct.get(key) != re_read_attrs.get(key):
            raise RuntimeError(
                f"assembly path and raw row disagree on {key!r}: "
                f"{re_read_attrs.get(key)!r} vs {direct.get(key)!r}"
            )


def _resolve_display_id(engine: Engine, source_id: str) -> str:
    """Resolve a fixture-level `source_id` to the entity's `display_id` for
    `assemble_context`. Refuses to guess if the lookup misses (defensive — the caller
    should have a clear error, not a silent retry).
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": source_id, "sys": SPIKE_SOURCE_SYSTEM},
        ).first()
    if row is None:
        raise ValueError(
            f"no PR with source_id={source_id!r} source_system={SPIKE_SOURCE_SYSTEM!r}"
        )
    return row[0]


def _resolve_source_refs(engine: Engine, display_ids: list[str]) -> list[dict[str, str]]:
    """Map `display_id` → `(source_system, source_id)` for display.

    §11 names suppliers by their source identity (`SPIKE-SUP-A`), while the Context
    shape only carries `display_id` (see `assembly.py` step 5). This is the inverse of
    `_resolve_display_id` and exists only so the §11 output can be printed verbatim.
    """
    if not display_ids:
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT display_id, source_system, source_id FROM entities "
                "WHERE display_id = ANY(:ids)"
            ),
            {"ids": display_ids},
        ).all()
    by_display = {r[0]: {"system": r[1] or "", "record_id": r[2] or ""} for r in rows}
    return [{"display_id": d, **by_display.get(d, {"system": "", "record_id": ""})}
            for d in display_ids]


def _read_pr_attrs(engine: Engine, display_id: str) -> dict[str, Any]:
    """Read the PR's attributes straight from the table.

    Deliberately bypasses `assemble_context`: it is the second, independent witness in
    `_assert_loop_closed`. Nothing here trusts a function's own return value.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT attributes FROM entities WHERE display_id = :did"),
            {"did": display_id},
        ).first()
    return dict(row[0]) if row and row[0] else {}
