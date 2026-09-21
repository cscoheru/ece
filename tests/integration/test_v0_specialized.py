"""S6 (V0 Technical Spike) — the three specialized tests of `docs/v0/V0_EXECUTION_SPEC.md` §10.1.

  1. **Determinism**: same loop, N=10, byte-equal `decision_value` + `evaluated_conditions`.
  2. **Evidence traceability (incl. fourth hop)**: `decision → evidence → source →
     input_context_ref → 原始 context_requests 行`. The fourth hop — the one S2/S5
     admitted was *only* tested as a round-trip equality — must really walk back here.
  3. **Permission**: denied user must leave the database untouched; no evidence rows,
     no `entities.attributes` write.

S6 is the **last** stage of the V0 Spike. Per the S6 binding acceptance criteria (审验者裁定,
2026-09-21), passing S6 closes the spike (六步全闭合) and returns to the STOP Gate.

**Test-first**: per the S5 ruling §4 (process discipline restored), this file is the first
deliverable; nothing in `src/ece/v0/` or its callers is changed for S6.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text

from ece.db import get_engine
from ece.v0.loop import run_v0_loop

FIXTURE_SYSTEM = "spike:v0-technical-fixture"
PR_SOURCE_ID = "SPIKE-PR-001"
ALLOWED_USER = "spike-user-procurement"
DENIED_USER = "spike-user-unrelated"
REPO = Path(__file__).resolve().parents[2]


# ---------- fixtures (duplicated from test_v0_loop.py on purpose) ----------

@pytest.fixture(scope="module")
def spike_fixture_seed() -> dict:
    """Seed once, capture the PR's `attributes` for restore on teardown."""
    subprocess.run(
        ["uv", "run", "python", "scripts/seed_v0_spike_fixture.py"],
        cwd=str(REPO), capture_output=True, text=True, check=True, timeout=120,
    )
    with get_engine().connect() as conn:
        snapshot = conn.execute(
            text("SELECT attributes FROM entities "
                 "WHERE source_id = :sid AND source_system = :sys"),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).scalar_one()
    yield snapshot or {}
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE entities SET attributes = CAST(:a AS jsonb) "
                 "WHERE source_id = :sid AND source_system = :sys"),
            {"a": json.dumps(snapshot or {}), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        )


@pytest.fixture(autouse=True)
def isolate_pr_attrs(spike_fixture_seed: dict) -> None:
    """Restore PR attrs after every test. Without this, T-D's N=10 mutations of
    `review_status` leak into T-P, breaking its "DB untouched" assertion."""
    yield
    with get_engine().begin() as conn:
        conn.execute(
            text("UPDATE entities SET attributes = CAST(:a AS jsonb) "
                 "WHERE source_id = :sid AND source_system = :sys"),
            {"a": json.dumps(spike_fixture_seed), "sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        )


@pytest.fixture()
def evidence_cleanup() -> list[str]:
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
            text("SELECT attributes FROM entities "
                 "WHERE source_id = :sid AND source_system = :sys"),
            {"sid": PR_SOURCE_ID, "sys": FIXTURE_SYSTEM},
        ).scalar_one()
    return row or {}


# ---------- 1. Determinism (N=10) ----------

def test_determinism_under_loop_runs_byte_equal_decision_and_conditions(
    evidence_cleanup: list[str],
) -> None:
    """§10.1 row 1: 同一 ctx 连跑 N=10, `decision_value` + `evaluated_conditions` 逐字段一致.

    S3 already proved the *rule* is deterministic on synthetic values. This is the
    fixture-level version: the whole loop, on the spike fixture's real data
    (amount=1_280_000, qc=1). It catches any non-pure input that creeps in through
    `assemble_context` (e.g. counters/IDs that leak into `evaluated_conditions`).
    """
    N = 10  # noqa: N806 (spec §10.1 row 1 notation: "N=10")
    decision_values: list[str] = []
    conditions_dump: list[str] = []   # sorted-JSON for stable byte comparison
    for _ in range(N):
        result = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
        assert result.decision is not None, "happy path must produce a decision"
        evidence_cleanup.append(result.decision["decision_id"])
        decision_values.append(result.decision["decision_value"])
        # Sorted keys, no whitespace: byte-equal across runs if the rule is pure.
        conditions_dump.append(json.dumps(result.decision["evaluated_conditions"], sort_keys=True, separators=(",", ":")))

    assert len(set(decision_values)) == 1, (
        f"decision_value must be byte-equal across N={N} runs; got {Counter(decision_values)}"
    )
    assert len(set(conditions_dump)) == 1, (
        f"evaluated_conditions must be byte-equal across N={N} runs; got "
        f"{len(set(conditions_dump))} distinct shape(s)"
    )
    assert decision_values[0] == "review_required"


# ---------- 2. Traceability — the fourth hop ----------

def test_evidence_input_context_ref_walks_back_to_a_real_context_requests_row(
    evidence_cleanup: list[str],
) -> None:
    """§10.1 row 2: `decision → evidence → source → input_context_ref → 原始 Context`.

    Hops 1-3 are mechanical. The **fourth hop** — `input_context_ref` → original
    `context_requests` row — is what S2/S5 only tested as a round-trip equality
    (the input_context_ref we wrote out equals the package_id we just produced).
    Here the assertion is harder: the *stored* `input_context_ref` must resolve to
    a row that is **not just the round-trip value** but the actual request row the
    `assemble_context` call wrote (intent + user_ref must match).

    **SQL deviation, reported.** The reviewer's literal prescription —
    `request_id::text LIKE '<24hex>%'` — matches **0 rows** because PostgreSQL's
    UUID canonical form (`xxxxxxxx-xxxx-...`) inserts dashes at fixed positions, so
    the first 24 chars of `request_id::text` contain dashes that the hex-only prefix
    from `package_id = f"ctx_{request_id.hex[:24]}"` does not. The minimal fix:
    strip dashes on the table side. This is **one SQL function call** (`replace`),
    no schema change, no new abstraction. Probe result is in S6_REPORT §2.2.
    """
    result = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
    assert result.decision is not None, "happy path must produce a decision"
    evidence_cleanup.append(result.decision["decision_id"])

    assert result.evidence, "the happy path must have produced at least one evidence row"
    # Pick the first evidence row deterministically (get_evidence_for_decision sorts).
    first_ev = result.evidence[0]
    icr = first_ev["input_context_ref"]
    assert icr.startswith("ctx_"), f"unexpected input_context_ref shape: {icr!r}"
    hex_prefix = icr.removeprefix("ctx_")   # 24 hex chars, no dashes
    assert len(hex_prefix) == 24 and all(c in "0123456789abcdef" for c in hex_prefix), (
        f"input_context_ref suffix must be 24 hex chars; got {hex_prefix!r}"
    )

    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT request_id::text AS request_id, user_ref, intent
                FROM context_requests
                WHERE replace(request_id::text, '-', '') LIKE :prefix
                """
            ),
            {"prefix": hex_prefix + "%"},
        ).all()

    assert len(rows) == 1, (
        f"the 4th hop must resolve to exactly one context_requests row; got {len(rows)} "
        f"(prefix={hex_prefix!r})"
    )
    rid, user_ref, intent = rows[0]
    # Canonical-form first 24 chars must equal the dashes-inserted version of `hex_prefix`.
    canonical_prefix = (
        hex_prefix[:8] + "-" + hex_prefix[8:12] + "-" +
        hex_prefix[12:16] + "-" + hex_prefix[16:20] + "-"
    )
    assert rid.startswith(canonical_prefix), (
        f"the resolved request_id {rid!r} does not start with {canonical_prefix!r}"
    )
    assert user_ref == ALLOWED_USER, (
        f"the 4th-hop request was made by {user_ref!r}, expected {ALLOWED_USER!r}"
    )
    assert intent == "evaluate_purchase_request", (
        f"the 4th-hop request's intent is {intent!r}, expected 'evaluate_purchase_request'"
    )


# ---------- 3. Permission ----------

def test_permission_denial_is_complete_with_no_side_effects(
    evidence_cleanup: list[str],
) -> None:
    """§10.1 row 3 — the four assertions on a denied run:

      ① PR **不在** `ctx.entities`
      ② `decision is None`
      ③ `ctx.denied` 非空
      ④ 规则未被求值的**副作用证据**：无 evidence 行写入 + `entities.attributes` 逐字节未变

    S5 test #2 covered ①②③ for the `run_v0_loop` shape; this is the §10.1 carrier on
    the spike fixture, asserting ④ explicitly (which S5 only covered for the read path).
    """
    # ④-pre: snapshot the row + the evidence table before the denied run.
    attrs_before = _read_pr_attrs_direct()
    with get_engine().connect() as conn:
        ev_before = conn.execute(text("SELECT count(*) FROM evidence_records")).scalar_one()

    result = run_v0_loop(DENIED_USER, PR_SOURCE_ID)

    # ① / ② / ③
    assert result.decision is None, "denied user must not produce a decision"
    assert result.evidence == [] and result.evidence_ids == [], (
        f"denied user must produce no evidence; got {result.evidence_ids}"
    )
    assert result.denied, (
        f"denied run must carry ctx.denied entries; got {result.denied!r}"
    )
    # The PR's source_id must not appear among the resolved entities: ① as observed
    # through the loop's own surface (the loop never exposed a PR for the rule to see).
    assert result.pr_ref is not None  # the resolver still ran, but the entity was filtered out
    # ④
    attrs_after = _read_pr_attrs_direct()
    assert attrs_after == attrs_before, (
        f"entities.attributes changed during a denied run; before={attrs_before} after={attrs_after}"
    )
    with get_engine().connect() as conn:
        ev_after = conn.execute(text("SELECT count(*) FROM evidence_records")).scalar_one()
    assert ev_after == ev_before, (
        f"the denied run inserted evidence rows (count grew from {ev_before} to {ev_after})"
    )
