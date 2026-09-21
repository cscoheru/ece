"""S4 (V0 Technical Spike) — `apply_context_update` integration test.

Per `docs/v0/V0_EXECUTION_SPEC.md` §8 (Context Update) and §9 step [6].
Per the binding acceptance criteria for S4 (审验者裁定, 2026-09-21).

The behavior under test lives in `src/ece/context/update.py`; this file checks the
**re-read** path (`assemble_context(...)` must read back the new business state),
not the SQL rowcount — that distinction is the whole point of §8.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from ece.context.assembly import ContextPackage, assemble_context
from ece.context.update import apply_context_update
from ece.db import get_engine
from ece.domain_packs.procurement.agent.v0_rules import (
    build_decision,
    evaluate_rule_R_SPIKE_REVIEW,
)
from ece.evidence import get_evidence_for_decision, persist_evidence

FIXTURE_SYSTEM = "spike:v0-technical-fixture"
PR_SOURCE_ID = "SPIKE-PR-001"


# ---------- fixtures ----------

@pytest.fixture(scope="module", autouse=True)
def spike_fixture_seed() -> None:
    """Run the spike seeder once so the spike PR exists; on teardown, restore the PR's
    `attributes` to the snapshot taken right after seeding. We do NOT re-seed in teardown
    because that would mutate the spike fixture's entity ids and any out-of-band rows
    pointing at them. Direct UPDATE is precise and cheap.
    """
    repo = Path(__file__).resolve().parents[2]
    subprocess.run(
        ["uv", "run", "python", "scripts/seed_v0_spike_fixture.py"],
        cwd=str(repo), capture_output=True, text=True, check=True, timeout=120,
    )
    with get_engine().connect() as conn:
        original = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).scalar_one()
    yield
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE entities SET attributes = CAST(:a AS jsonb) "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"a": json.dumps(original or {}), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        )


@pytest.fixture()
def evidence_cleanup() -> list[str]:
    """Record decision_ids created by tests; delete their evidence rows on teardown.

    Evidence rows are not in the spike fixture's source_system scope (the fixture wipes
    entities/relationships in that scope), so they need an explicit cleanup here.
    """
    decision_ids: list[str] = []
    yield decision_ids
    if decision_ids:
        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM evidence_records WHERE decision_id = ANY(:ids)"),
                {"ids": decision_ids},
            )


# ---------- helpers ----------

def _pr_display_id() -> str:
    with get_engine().connect() as conn:
        return conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).scalar_one()


def _build_ctx_with_pr(display_id: str) -> ContextPackage:
    """Hand-built ContextPackage shaped like the real one (`assembly.py:43-...`),
    with the spike PR embedded so `persist_evidence` finds exactly one purchase_request.
    """
    return ContextPackage(
        package_id=f"ctx_{uuid.uuid4().hex[:24]}",
        request_id=str(uuid.uuid4()),
        task={"intent": "evaluate_purchase_request", "spec_version": 1},
        user={
            "id": "spike-user-procurement", "display_id": "U-SYNTHETIC", "name": "",
            "department": "procurement", "roles": ["buyer"], "is_management": False,
        },
        entities=[{
            "ref": display_id,
            "type": "purchase_request",
            "name": "SPIKE-PR-001",
            "attrs": {"amount": 1_280_000, "review_status": "pending"},
            "src": {"system": FIXTURE_SYSTEM, "record_id": PR_SOURCE_ID},
        }],
        relationships=[],
        denied=[],
        sources=[],
        metadata={},
    )


def _produce_decision_and_first_evidence_id(
    ctx: ContextPackage, amount: int, quote_count: int
) -> tuple[dict, str]:
    """Build the Decision the way S5 will, persist Evidence the way S5 will, and return
    the `(decision, first-evidence-id)` pair `apply_context_update` needs."""
    conditions = evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)
    decision = build_decision(conditions, ctx)
    persist_evidence(get_engine(), ctx, decision)
    rows = get_evidence_for_decision(get_engine(), decision["decision_id"])
    assert rows, f"no Evidence rows persisted for {decision['decision_id']}"
    return decision, rows[0]["evidence_id"]


def _read_pr_attrs() -> dict:
    """Reassemble and return the PR's attributes. This is the criterion's `re-read`."""
    display_id = _pr_display_id()
    ctx = assemble_context(
        get_engine(), "spike-user-procurement", "evaluate_purchase_request",
        [{"type": "purchase_request", "id": display_id}],
    )
    pr = next((e for e in ctx.entities if e["type"] == "purchase_request"), None)
    assert pr is not None, (
        f"re-read failed: PR {display_id!r} did not appear in the assembled Context "
        f"({len(ctx.entities)} entities, denied={len(ctx.denied)})"
    )
    return pr["attrs"], display_id


# ---------- the four binding acceptance criteria that translate to tests ----------

def test_happy_path_re_read_shows_review_required_and_four_keys(
    evidence_cleanup: list[str],
) -> None:
    """Criterion 1, 3, 4: re-assembled attrs carry review_status, review_decision_id,
    review_evidence_id, review_updated_at — AND the original attrs are preserved.
    """
    display_id = _pr_display_id()
    ctx = _build_ctx_with_pr(display_id)
    decision, evidence_id = _produce_decision_and_first_evidence_id(ctx, 1_280_000, 1)
    evidence_cleanup.append(decision["decision_id"])

    apply_context_update(
        get_engine(), PR_SOURCE_ID, FIXTURE_SYSTEM, decision, evidence_id,
    )

    attrs, _ = _read_pr_attrs()
    assert attrs["review_status"] == "review_required"
    assert attrs["review_decision_id"] == decision["decision_id"]
    assert attrs["review_evidence_id"] == evidence_id
    assert "review_updated_at" in attrs
    # original attrs preserved (the function does `attributes || jsonb_build_object(...)`,
    # i.e. append — not overwrite)
    assert attrs["amount"] == 1_280_000


def test_review_updated_at_parses_as_iso_timestamp() -> None:
    """Criterion 3 implicit: the timestamp is machine-readable."""
    from datetime import datetime

    display_id = _pr_display_id()
    ctx = _build_ctx_with_pr(display_id)
    decision, evidence_id = _produce_decision_and_first_evidence_id(ctx, 1_280_000, 1)

    apply_context_update(
        get_engine(), PR_SOURCE_ID, FIXTURE_SYSTEM, decision, evidence_id,
    )

    attrs, _ = _read_pr_attrs()
    raw = attrs["review_updated_at"]
    assert isinstance(raw, str), f"review_updated_at must be a string, got {type(raw).__name__}"
    parsed = datetime.fromisoformat(raw)  # raises if malformed
    assert parsed.tzinfo is not None, "review_updated_at must be timezone-aware"


def test_target_missing_raises() -> None:
    """Criterion 5 (negative control): if the fixture's PR were absent, the function
    must refuse rather than ghost-writing a fresh row.
    """
    decision = {"decision_value": "review_required", "decision_id": "dec_<nope>"}
    with pytest.raises(ValueError, match="no entity"):
        apply_context_update(
            get_engine(), "NO-SUCH-SOURCE-ID", FIXTURE_SYSTEM, decision, "ev_<nope>",
        )


def test_ambiguous_target_raises() -> None:
    """Criterion 5: two entities with the same (source_id, source_system) must not be
    silently merged into one update.
    """
    decoy_id = str(uuid.uuid4())
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO entities (id, entity_type, source_id, source_system, "
                "display_id, name, normalized_name, attributes) VALUES "
                "(:id, 'supplier', :sid, :sys, :did, :name, :nname, '{}'::jsonb)"
            ),
            {"id": decoy_id, "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM,
             "did": f"SUP-DECOY-{uuid.uuid4().hex[:6]}",
             "name": "decoy", "nname": "decoy"},
        )
    try:
        decision = {"decision_value": "review_required", "decision_id": "dec_<amb>"}
        with pytest.raises(ValueError, match="refusing to guess"):
            apply_context_update(
                get_engine(), PR_SOURCE_ID, FIXTURE_SYSTEM, decision, "ev_<amb>",
            )
    finally:
        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM entities WHERE id = :id"), {"id": decoy_id}
            )


def test_no_new_entity_inserted() -> None:
    """Criterion 5 (literal): 'INSERT' of new entities is forbidden. The function must
    not change the entity count.
    """
    display_id = _pr_display_id()
    ctx = _build_ctx_with_pr(display_id)
    decision, evidence_id = _produce_decision_and_first_evidence_id(ctx, 1_280_000, 1)

    with get_engine().connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM entities")).scalar_one()

    apply_context_update(
        get_engine(), PR_SOURCE_ID, FIXTURE_SYSTEM, decision, evidence_id,
    )

    with get_engine().connect() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM entities")).scalar_one()
    assert after == before, (
        f"entity count changed: before={before} after={after} — apply_context_update "
        "must not INSERT"
    )
