"""S5 (V0 Technical Spike) — `run_v0_loop` integration test.

Per `docs/v0/V0_EXECUTION_SPEC.md` §9 (six steps) + §10 (verifications) + §11 (output).
Per the binding acceptance criteria for S5 (审验者裁定, 2026-09-21).

**Test-first (per S4 ruling §4):** this file is the FIRST deliverable; the impl in
`src/ece/v0/loop.py` does not yet exist. The red→green→mutation sequence is recorded in
`docs/v0/S5_REPORT.md`.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from ece.db import get_engine
from ece.evidence import get_evidence_for_decision
from ece.v0.loop import V0LoopResult, run_v0_loop

FIXTURE_SYSTEM = "spike:v0-technical-fixture"
PR_SOURCE_ID = "SPIKE-PR-001"
ALLOWED_USER = "spike-user-procurement"
DENIED_USER = "spike-user-unrelated"


# ---------- fixtures ----------

@pytest.fixture(scope="module", autouse=True)
def spike_fixture_seed() -> None:
    """Seed the spike fixture once; on teardown, restore the PR's `attributes` directly
    (re-seeding would churn entity ids and break other rows pointing at them).
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
    """Record decision_ids the loop created; delete their evidence rows on teardown."""
    decision_ids: list[str] = []
    yield decision_ids
    if decision_ids:
        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM evidence_records WHERE decision_id = ANY(:ids)"),
                {"ids": decision_ids},
            )


# ---------- helpers ----------

def _read_pr_attrs_direct() -> dict:
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).scalar_one()
    return row or {}


# ---------- tests ----------

def test_happy_path_runs_all_six_steps_and_re_read_matches_decision(
    evidence_cleanup: list[str],
) -> None:
    """Criterion 1, 2, 3, 4: six steps chained, re-read carries dec.decision_value.

    Spike fixture default: amount=1_280_000, qc=1 → review_required.
    """
    result = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
    evidence_cleanup.append(result.decision["decision_id"])

    assert isinstance(result, V0LoopResult)
    assert result.package_id.startswith("ctx_")
    assert result.reason == "ok"
    assert result.decision is not None
    assert result.decision["decision_value"] == "review_required"
    assert result.decision["rule_id"] == "R-SPIKE-REVIEW"
    assert result.decision["decision_key"] == "review_status"

    # Step [5] produced evidence (2 passed conditions → 2 rows)
    assert len(result.evidence_ids) == 2
    rows = get_evidence_for_decision(get_engine(), result.decision["decision_id"])
    assert len(rows) == 2

    # §8 / criterion 3: re-read carries the decision value verbatim
    assert result.re_read_attrs["review_status"] == "review_required"
    # original attrs preserved (append, not overwrite)
    assert result.re_read_attrs["amount"] == 1_280_000
    # Step [6] wired dec <-> ev: the first evidence id is what step [6] used
    first_ev_id = result.evidence_ids[0]
    assert result.decision["decision_id"].startswith("dec_")
    # The re-read carries the same four review_* keys
    assert result.re_read_attrs["review_decision_id"] == result.decision["decision_id"]
    assert result.re_read_attrs["review_evidence_id"] == first_ev_id
    assert "review_updated_at" in result.re_read_attrs


def test_denied_branch_returns_no_permitted_context_and_does_not_modify_db(
    evidence_cleanup: list[str],
) -> None:
    """Criterion 1: when the user is denied and PR not in entities, decision=None,
    steps [3]-[6] skipped, DB unchanged.
    """
    before = _read_pr_attrs_direct()
    result = run_v0_loop(DENIED_USER, PR_SOURCE_ID)

    assert result.decision is None
    assert result.evidence_ids == []
    assert result.reason == "no permitted context"
    assert result.package_id.startswith("ctx_")  # step [1] ran

    # The re-read itself just shows the DB was untouched (still 'pending').
    assert result.re_read_attrs["review_status"] == "pending"

    # Independent direct DB read confirms no half-product.
    after = _read_pr_attrs_direct()
    assert after.get("review_status", "pending") == "pending"
    assert "review_decision_id" not in after
    assert "review_evidence_id" not in after
    assert "review_updated_at" not in after
    # Sanity: nothing else in attrs changed either.
    assert before == after


def test_auto_approved_path_also_propagates_decision_value_through(
    evidence_cleanup: list[str],
) -> None:
    """Regression for the S4 condition (F) at the loop level: auto_approved must
    also reach the DB unchanged — a hardcoded bind to "review_required" would fail here.
    """
    original = _read_pr_attrs_direct()
    # Temporarily lower the amount to 500_000 (below PRICE_COMPARISON_THRESHOLD=1_000_000).
    # qc=1 still passes quote_count_lt_required, but amount_gte_threshold fails
    # → AND fails → decision_value="auto_approved".
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "UPDATE entities SET attributes = attributes || jsonb_build_object("
                "'amount', CAST(:a AS text)) "
                "WHERE source_id = :sid AND source_system = :sys"
            ),
            {"a": json.dumps(500_000), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        )
    try:
        result = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
        evidence_cleanup.append(result.decision["decision_id"])

        assert result.decision["decision_value"] == "auto_approved"
        assert result.re_read_attrs["review_status"] == "auto_approved", (
            "loop must propagate decision_value verbatim; if it hardcoded 'review_required'"
            " this would say review_required"
        )
        # 1 passed condition → 1 evidence row
        assert len(result.evidence_ids) == 1
    finally:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "UPDATE entities SET attributes = CAST(:a AS jsonb) "
                    "WHERE source_id = :sid AND source_system = :sys"
                ),
                {"a": json.dumps(original or {}), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
            )


def test_loop_module_does_not_route_decision_through_an_llm() -> None:
    """Criterion 7: the loop is orchestration; the Decision stays deterministic."""
    import ece.v0.loop as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("openai", "anthropic", "provider", "llm"):
        assert forbidden not in src.lower(), (
            f"the loop module must not route through an LLM; found {forbidden!r}"
        )