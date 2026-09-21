"""S2 (V0 Technical Spike) — Evidence persistence + reverse lookup.

Covers exactly what the Codex ruling on `docs/v0/V0_EXECUTION_SPEC.md` asked S2 to
deliver: minimal `evidence_records` persistence, plus the
`decision_id -> evidence -> source -> input_context_ref` chain of §10.1.

Two habits this file keeps, because the V0 spike is testing a *chain*, not a function:

1. **It checks the DATABASE, not what `persist_evidence` returned.** A function's own
   return value is a self-report; the claim "the rows exist" has to be evidenced by a
   fresh SELECT that does not go through `store.py`.
2. **Every guard in `store.py` gets a negative control.** A `raise` nobody ever makes
   fire is an unverified assertion — the same pattern that produced this project's
   earlier fake greens.

The Context is hand-built to the exact shape `assemble_context` produces
(`src/ece/context/assembly.py:234-240`), so S2 does not depend on the spike fixture
being seeded. Wiring against a real package is S5/S6's job.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text

from ece.context.assembly import ContextPackage
from ece.db import get_engine
from ece.evidence import get_evidence_for_decision, persist_evidence

FIXTURE_SYSTEM = "spike:v0-technical-fixture"
PR_SOURCE_ID = "SPIKE-PR-001"


def _context(*, package_id: str, subject_count: int = 1, with_provenance: bool = True) -> ContextPackage:
    """A ContextPackage shaped like the real one, not a convenient fiction."""
    entities: list[dict[str, Any]] = []
    for i in range(subject_count):
        entity: dict[str, Any] = {
            "ref": f"PR-SYNTHETIC-{i}",  # never resolved against the DB in S2
            "type": "purchase_request",
            "name": PR_SOURCE_ID,
            "attrs": {"amount": 1_280_000, "review_status": "pending"},
        }
        if with_provenance:
            entity["src"] = {"system": FIXTURE_SYSTEM, "record_id": PR_SOURCE_ID}
        entities.append(entity)

    return ContextPackage(
        package_id=package_id,
        request_id=str(uuid.uuid4()),
        task={"intent": "evaluate_purchase_request", "spec_version": 1},
        user={
            "id": "spike-user-procurement",  # the original X-User-Id (Identity.user_ref)
            "display_id": "U-SYNTHETIC",
            "name": "Spike Buyer",
            "department": "procurement",
            "roles": ["buyer"],
            "is_management": False,
        },
        entities=entities,
        relationships=[
            {
                "from": "PR-SYNTHETIC-0",
                "rel": "SELECTS",
                "to": "SUP-SYNTHETIC",
                "valid": [None, None],
                "src": {"system": FIXTURE_SYSTEM, "record_id": ""},
            }
        ],
        denied=[],
        sources=[{"sid": 1, "system": FIXTURE_SYSTEM, "record_id": PR_SOURCE_ID}],
        metadata={"generated_at": "2026-09-21T00:00:00Z", "counts": {"entities": 1, "relationships": 1}},
    )


def _conditions() -> list[dict[str, Any]]:
    """Two passing conditions and one failing one, per the spec's §6 shape.

    `claim` / `threshold` ride along with the four keys §6 lists — see the note in
    `store.persist_evidence` on why §6 and §7 cannot both be satisfied otherwise.
    """
    return [
        {
            "name": "amount_gte_threshold",
            "expr": "amount >= 1000000",
            "actual": 1_280_000,
            "threshold": 1_000_000,
            "passed": True,
            "claim": "金额 1,280,000 ≥ 1,000,000（100万阈值）",
        },
        {
            "name": "quote_count_lt_required",
            "expr": "quote_count < 3",
            "actual": 1,
            "threshold": 3,
            "passed": True,
            "claim": "报价家数 1 < 3",
        },
        {
            "name": "supplier_blacklisted",
            "expr": "blacklisted == true",
            "actual": False,
            "threshold": None,
            "passed": False,
            "claim": "供应商在黑名单",
        },
    ]


def _decision(decision_id: str, ctx: ContextPackage, conditions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "decision_id": decision_id,
        "rule_id": "R-SPIKE-REVIEW",
        "decision_key": "review_status",
        "decision_value": "review_required",
        "evaluated_conditions": conditions,
        "reason": "金额 1,280,000 ≥ 1,000,000 且仅 1 家报价（需 3 家）→ 需人工复核",
        "input_context_ref": ctx.package_id,
        "request_id": ctx.request_id,
    }


def _rows_in_db(decision_id: str) -> list[dict[str, Any]]:
    """Independent read: deliberately NOT via `ece.evidence`."""
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT evidence_id, decision_id, rule_id, claim, source_system, "
                "       source_record_id, observed_value, threshold_value, "
                "       actor_user_ref, input_context_ref, evidence_timestamp "
                "FROM evidence_records WHERE decision_id = :d"
            ),
            {"d": decision_id},
        ).mappings().all()
    return [dict(r) for r in rows]


@pytest.fixture()
def cleanup() -> Any:
    """Delete only the rows this module wrote, scoped by decision_id."""
    written: list[str] = []
    yield written
    if written:
        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM evidence_records WHERE decision_id = ANY(:ids)"),
                {"ids": written},
            )


def test_persist_evidence_writes_one_row_per_passed_condition(cleanup: list[str]) -> None:
    decision_id = f"dec_{uuid.uuid4()}"
    cleanup.append(decision_id)
    ctx = _context(package_id="ctx_000000000000000000000001")

    returned = persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, _conditions()))

    rows = _rows_in_db(decision_id)
    assert len(rows) == 2, (
        "expected one Evidence row per PASSED condition (2 of 3 pass); "
        f"the database holds {len(rows)}"
    )
    assert len(returned) == len(rows), (
        "the function's return value disagrees with the database: "
        f"returned {len(returned)}, stored {len(rows)}"
    )
    assert {r["claim"] for r in rows} == {
        "金额 1,280,000 ≥ 1,000,000（100万阈值）",
        "报价家数 1 < 3",
    }, "the failing condition must not produce Evidence"
    for row in rows:
        assert row["evidence_id"].startswith("ev_")
        assert row["rule_id"] == "R-SPIKE-REVIEW"
        assert row["actor_user_ref"] == "spike-user-procurement"
        assert row["evidence_timestamp"] is not None


def test_reverse_chain_decision_to_evidence_to_source_to_context(cleanup: list[str]) -> None:
    """The §10.1 chain: every hop must be resolvable from the row alone."""
    decision_id = f"dec_{uuid.uuid4()}"
    cleanup.append(decision_id)
    ctx = _context(package_id="ctx_000000000000000000000002")
    persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, _conditions()))

    found = get_evidence_for_decision(get_engine(), decision_id)
    assert len(found) == 2

    for evidence in found:
        # decision -> evidence -> source
        assert evidence["decision_id"] == decision_id
        assert evidence["source_system"] == FIXTURE_SYSTEM
        assert evidence["source_record_id"] == PR_SOURCE_ID
        # ... -> input_context_ref -> the original Context package
        assert evidence["input_context_ref"] == ctx.package_id, (
            "the hop back to the originating Context must be recorded, otherwise this "
            "is a citation and not traceable evidence"
        )
    # Ordered deterministically even though the schema has no sequence column.
    assert [e["claim"] for e in found] == sorted(e["claim"] for e in found)


def test_evidence_is_scoped_to_its_own_decision(cleanup: list[str]) -> None:
    """Two decisions in the same table must not see each other's Evidence."""
    first, second = f"dec_{uuid.uuid4()}", f"dec_{uuid.uuid4()}"
    cleanup.extend([first, second])

    ctx_a = _context(package_id="ctx_00000000000000000000000a")
    ctx_b = _context(package_id="ctx_00000000000000000000000b")
    persist_evidence(get_engine(), ctx_a, _decision(first, ctx_a, _conditions()[:1]))
    persist_evidence(get_engine(), ctx_b, _decision(second, ctx_b, _conditions()))

    assert len(get_evidence_for_decision(get_engine(), first)) == 1
    assert len(get_evidence_for_decision(get_engine(), second)) == 2
    assert len(_rows_in_db(first)) == 1


def test_no_passed_condition_writes_nothing(cleanup: list[str]) -> None:
    """A decision with nothing satisfied produces no Evidence — and no error."""
    decision_id = f"dec_{uuid.uuid4()}"
    cleanup.append(decision_id)
    ctx = _context(package_id="ctx_000000000000000000000003")
    failed_only = [c for c in _conditions() if not c["passed"]]

    assert persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, failed_only)) == []
    assert _rows_in_db(decision_id) == []


def test_missing_claim_on_a_passed_condition_fails_loudly() -> None:
    """Negative control: the `claim` guard must actually bite."""
    decision_id = f"dec_{uuid.uuid4()}"
    ctx = _context(package_id="ctx_000000000000000000000004")
    no_claim = [{k: v for k, v in c.items() if k != "claim"} for c in _conditions()[:1]]

    with pytest.raises(ValueError, match="claim"):
        persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, no_claim))
    assert _rows_in_db(decision_id) == [], "a refused write must leave nothing behind"


def test_ambiguous_subject_fails_loudly() -> None:
    """Negative control: two PRs in one Context must not be silently resolved."""
    decision_id = f"dec_{uuid.uuid4()}"
    ctx = _context(package_id="ctx_000000000000000000000005", subject_count=2)

    with pytest.raises(ValueError, match="exactly one"):
        persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, _conditions()))


def test_subject_entity_filter_is_enforced(cleanup: list[str]) -> None:
    """Negative control for the type filter that earlier mutation testing found uncovered.

    The original seven tests all happen to use a single purchase_request as subject, so
    nothing distinguishes "the filter picked the PR" from "the filter ignored every type".
    These two cases close that gap.

    Case ① — no purchase_request at all. `_subject_entity` would otherwise return nothing
    or pick wrong; the guard must refuse.
    Case ② — a purchase_request among other entities. The filter must pick the PR and
    the row's `source` must come from the PR's `src`, not from whatever happens to be
    first in the list.
    """
    # ① zero purchase_request, only a supplier — the filter must bite.
    decision_id = f"dec_{uuid.uuid4()}"
    cleanup.append(decision_id)
    ctx = _context(package_id="ctx_000000000000000000000006")
    ctx.entities = [
        {
            "ref": "SUP-SYNTHETIC-A",
            "type": "supplier",
            "name": "Supplier A",
            "attrs": {"name": "Supplier A"},
            "src": {"system": FIXTURE_SYSTEM, "record_id": "SPIKE-SUP-A"},
        }
    ]
    with pytest.raises(ValueError, match="exactly one"):
        persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, _conditions()))

    # ② a purchase_request mixed with a supplier — the filter must pick the PR.
    # The supplier is intentionally placed at index 0 so a broken "return
    # ctx.entities[0]" implementation cannot accidentally pass on fixture shape.
    decision_id_pr = f"dec_{uuid.uuid4()}"
    cleanup.append(decision_id_pr)
    ctx_mixed = _context(package_id="ctx_000000000000000000000007", subject_count=0)
    pr_entity = _context(package_id="ctx_000000000000000000000007", subject_count=1).entities[0]
    pr_src = pr_entity["src"]
    ctx_mixed.entities = [
        {
            "ref": "SUP-SYNTHETIC-B",
            "type": "supplier",
            "name": "Supplier B",
            "attrs": {"name": "Supplier B"},
            "src": {"system": "other:system", "record_id": "SUPPLIER-B"},
        },
        pr_entity,
    ]
    rows = persist_evidence(get_engine(), ctx_mixed, _decision(decision_id_pr, ctx_mixed, _conditions()))
    assert {r["source_record_id"] for r in rows} == {pr_src["record_id"]}, (
        "the subject filter must pick the purchase_request and source from its src, "
        "not from whatever entity happens to be first"
    )
    assert {r["source_system"] for r in rows} == {pr_src["system"]}


def test_missing_entity_provenance_fails_loudly() -> None:
    """Negative control: Evidence with no source is not evidence."""
    decision_id = f"dec_{uuid.uuid4()}"
    ctx = _context(package_id="ctx_000000000000000000000006", with_provenance=False)

    with pytest.raises(ValueError, match="provenance"):
        persist_evidence(get_engine(), ctx, _decision(decision_id, ctx, _conditions()))
