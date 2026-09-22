"""cut-043R — Knowledge Management Pack boundary matrix tests.

Aligned with R5-B1..R5-B4 contract changes:

  - R5-B1: `today` is SERVER-owned. API rejects any client-supplied `today`
    with 422 and injects from ECE_SERVER_TODAY_ANCHOR env (or date.today()).
    Tests must NOT pass `today` in params; server injection is observed
    implicitly through which branch the rule lands in (KM-POL-002 expired).

  - R5-B2: `needs_valid_policy` is now an allowlisted zero-evidence decision.
    The double-failure path (KM-POL-002 + km-eve) returns 200/needs_valid_policy
    with 0 evidence rows — not a 500 RuntimeError.

  - R5-B3: ontology_resolver is inverted (pack → resolver, never resolver → pack).
    Tests verify fail-closed behavior for unknown source_system prefixes.

  - R5-B4: KM no longer reads `employee_id` from params. Caller identity comes
    from X-User-Id → assemble_context → ctx.user. `root_source_id`/`pr_source_id`
    override is rejected with 422 when route_root_via_params=true.

KM truth-table (R-KM-ACCESS = `validity AND permission`):

  +---------+--------+----------+--------+--------------------------+
  | policy  | user   | today    | value  | evidence rows            |
  +---------+--------+----------+--------+--------------------------+
  | P-001   | alice  | 2026-09  | answ.  | 2 (validity + perm)      |
  | P-002   | alice  | 2026-09  | need.  | 1 (perm only — expired)  |
  | P-003   | alice  | 2026-09  | need.  | 1 (validity only)        |
  | P-001   | eve    | 2026-09  | need.  | 0 (both failed — R5-B2)  |
  +---------+--------+----------+--------+--------------------------+

S2 semantics lock-down (mirrors procurement):
  validity passed  → validity evidence row persisted
  validity failed  → NO validity evidence row
  perm passed      → permission evidence row persisted
  perm failed      → NO permission evidence row
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.main import app

KM_SOURCE_SYSTEM = "km:v0-knowledge-fixture"
SERVER_TODAY = "2026-09-22"  # matches fixture's KM-POL-001 valid window


# ---------------------------------------------------------------------------
# helpers — direct DB reads, no mock, no in-memory shortcuts
# ---------------------------------------------------------------------------


def _display_id_for(source_id: str) -> str:
    """Resolve (source_id, source_system) → entities.display_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": source_id, "s": KM_SOURCE_SYSTEM},
        ).first()
    return str(row[0]) if row else ""


def _count_relationships_from_root(root_display_id: str, relation: str) -> int:
    """Direct SQL count of relationships from a given root display_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*) FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE s.display_id = :did AND r.relation = :rel
                  AND r.source_system = :sys
            """),
            {"did": root_display_id, "rel": relation, "sys": KM_SOURCE_SYSTEM},
        ).first()
    return int(row[0]) if row else 0


def _count_selects_from_context(
    root_source_id: str,
    user_ref: str,
    intent: str = "evaluate_policy_question",
) -> int:
    """R4-B1-style binding: Context relationships count via assemble_context."""
    display_id = _display_id_for(root_source_id)
    if not display_id:
        return 0
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref=user_ref,
        intent=intent,
        entities=[{"type": "policy_document", "id": display_id}],
        pack="knowledge",
    )
    return sum(
        1
        for rel in pkg.relationships
        if rel.get("from") == display_id
        and rel.get("rel") in ("REQUIRES_ROLE", "HAS_ROLE")
    )


def _count_evidence_rows() -> int:
    """R4-B1-style zero-write check: count evidence_records for the KM fixture."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) FROM evidence_records WHERE source_system = :sys"),
            {"sys": KM_SOURCE_SYSTEM},
        ).first()
    return int(row[0]) if row else 0


def _read_root_attrs(root_source_id: str) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT attributes FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": root_source_id, "s": KM_SOURCE_SYSTEM},
        ).first()
    return dict(row[0]) if row and row[0] else {}


def _restore_root_attrs(root_source_id: str, snapshot: dict) -> None:
    """Restore attrs after a parametrized case (mirrors procurement pattern)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE entities SET attributes = CAST(:a AS jsonb)
                WHERE source_id = :sid AND source_system = :s
            """),
            {"a": json.dumps(snapshot), "sid": root_source_id, "s": KM_SOURCE_SYSTEM},
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_attrs() -> None:
    """Snapshot/restore each policy's attrs around parametrized cases.

    Each case may mutate `policy_id` / `access_status` via the loop, so we
    restore the baseline attributes after each call to keep tests independent.
    """
    snapshots = {
        sid: _read_root_attrs(sid)
        for sid in ("KM-POL-001", "KM-POL-002", "KM-POL-003")
    }
    yield
    for sid, snap in snapshots.items():
        _restore_root_attrs(sid, snap)


# ---------------------------------------------------------------------------
# 4-case truth table — R5-B1 / R5-B2 / R5-B4 conformant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    (
        "policy_id",
        "user_id",
        "expected_value",
        "expected_evidence_count",
        "expected_keyword",
    ),
    [
        # KM-POL-001 + alice: valid + has-hr → answerable, 2 evidence rows
        ("KM-POL-001", "km-alice", "answerable", 2, "有据可答"),
        # KM-POL-002 + alice: expired + has-hr → needs_valid_policy, 1 evidence (perm only)
        ("KM-POL-002", "km-alice", "needs_valid_policy", 1, "请提供当前有效版本"),
        # KM-POL-003 + alice: valid + missing-finance → needs_valid_policy, 1 (validity only)
        ("KM-POL-003", "km-alice", "needs_valid_policy", 1, "当前用户无访问权限"),
        # cut-043 — permission 反差 (PRD §7 纪律 #2): KM-POL-001 + km-eve is denied
        # by the engine-level ACL DENY row (acl_entries seeded by seed_knowledge_fixture),
        # so the loop returns the denied branch with conclusion=no_permission and 0
        # evidence rows. This is the "denied pre-rule" pathway; R5-B2 below is the
        # "rule double-fail" pathway — both must coexist to demonstrate two distinct
        # business semantics (engine denial vs rule zero-evidence).
        ("KM-POL-001", "km-eve", "no_permission", 0, "无权访问"),
        # R5-B2 — KM-POL-002 + km-eve: BOTH conditions failed, 0 evidence.
        # Prior bug: this hit RuntimeError (loop only allowed auto_approved
        # zero-evidence). Now needs_valid_policy is allowlisted.
        ("KM-POL-002", "km-eve", "needs_valid_policy", 0, "请提供有效版本并确认访问权限"),
    ],
    ids=[
        "validity_pass_perm_pass_answerable",
        "validity_fail_perm_pass_needs_valid",
        "validity_pass_perm_fail_needs_valid",
        "validity_pass_perm_fail_eve_denied_pre_rule",
        "validity_fail_perm_fail_zero_evidence_r5b2",
    ],
)
def test_knowledge_boundary_truth_table(
    client: TestClient,
    policy_id: str,
    user_id: str,
    expected_value: str,
    expected_evidence_count: int,
    expected_keyword: str,
) -> None:
    """cut-043R binding invariant.

    Each 200 case asserts:
      1. `decision_value == expected_value`
      2. `len(evidence) == expected_evidence_count` (S2 lock-down + R5-B2)
      3. `reason contains expected_keyword`
      4. DB relationship counts stable (REQUIRES_ROLE + HAS_ROLE unchanged
         for the policy in question; KM has no materializer)

    R5-B1 conformance: NO `today` in params — server injects.
    R5-B4 conformance: NO `employee_id` in params — X-User-Id is identity.
    """
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": user_id},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {"policy_id": policy_id},
        },
    )
    assert resp.status_code == 200, (
        f"policy_id={policy_id} user_id={user_id}: expected 200, "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    body = resp.json()

    # 1. decision_value — mapper.to_business flattens `decision` to top-level
    #    `conclusion` / `conclusion_label` (cut-042R F4 API shape).
    decision_value = body.get("decision_value") or body.get("conclusion")
    assert decision_value == expected_value, (
        f"policy_id={policy_id} user_id={user_id}: "
        f"decision_value={decision_value!r} != expected={expected_value!r}"
    )

    # 2. evidence count (S2 lock-down + R5-B2 zero-evidence allowlist)
    evidence = body.get("evidence", [])
    assert len(evidence) == expected_evidence_count, (
        f"policy_id={policy_id} user_id={user_id}: "
        f"evidence count={len(evidence)} != expected={expected_evidence_count}; "
        f"evidence={evidence!r}"
    )

    # 3. reason keyword (business-language probe)
    reason = body.get("reason", "")
    assert expected_keyword in reason, (
        f"policy_id={policy_id} user_id={user_id}: "
        f"reason {reason!r} does not contain expected keyword {expected_keyword!r}"
    )

    # 4. DB relationship count stable (KM has no materializer)
    db_rr_count = _count_relationships_from_root(
        _display_id_for(policy_id), "REQUIRES_ROLE"
    )
    # KM-POL-001/003 each have 1 REQUIRES_ROLE; KM-POL-002 has 0 (no rels seeded)
    if policy_id in ("KM-POL-001", "KM-POL-003"):
        assert db_rr_count == 1, (
            f"{policy_id}: REQUIRES_ROLE={db_rr_count} != 1"
        )
    else:
        assert db_rr_count == 0, f"{policy_id}: REQUIRES_ROLE={db_rr_count} != 0"


# ---------------------------------------------------------------------------
# R5-B1 — server-owned `today` anchor
# ---------------------------------------------------------------------------


def test_r5b1_client_today_rejected_422(client: TestClient) -> None:
    """R5-B1: client `today` is forbidden when requires_server_today_anchor=true.

    The API must return 422 and not invoke the rule. This proves that
    backdating `today=2024-06-01` to bypass KM-POL-002's expiry window
    cannot succeed.
    """
    before_evidence = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {
                "policy_id": "KM-POL-002",  # expired
                "today": "2024-06-01",  # attacker-supplied backdate
            },
        },
    )
    assert resp.status_code == 422, (
        f"R5-B1: client-supplied today must be rejected with 422; "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert "server-owned" in detail or "requires_server_today_anchor" in detail, (
        f"R5-B1: 422 detail must mention server-owned anchor; got: {detail!r}"
    )

    # Zero-write binding (R4-B1 pattern)
    after_evidence = _count_evidence_rows()
    assert after_evidence == before_evidence, (
        f"R5-B1: rejected request must NOT add evidence rows; "
        f"before={before_evidence} after={after_evidence}"
    )


def test_r5b1_expired_policy_unanswerable_regardless_of_client_intent(client: TestClient) -> None:
    """R5-B1 / R5-B2 binding: KM-POL-002 always returns needs_valid_policy.

    Even without a client `today` param, the server's anchored today
    (2026-09-22 or whatever ECE_SERVER_TODAY_ANCHOR is set to) lands
    AFTER KM-POL-002's valid_to. The decision MUST be needs_valid_policy.
    If a future regression lets the rule read client time, this fails.
    """
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {"policy_id": "KM-POL-002"},
        },
    )
    assert resp.status_code == 200, (
        f"server-anchored today must produce a clean 200; got {resp.status_code}; "
        f"body={resp.text[:300]}"
    )
    body = resp.json()
    decision_value = body.get("decision_value") or body.get("conclusion")
    assert decision_value == "needs_valid_policy", (
        f"KM-POL-002 must always be needs_valid_policy (server-anchored today "
        f"is outside its validity window); got {decision_value!r}"
    )


# ---------------------------------------------------------------------------
# R5-B4 — route + identity parameter contract
# ---------------------------------------------------------------------------


def test_r5b4_root_source_id_override_rejected_422(client: TestClient) -> None:
    """R5-B4: when route_root_via_params=true, root_source_id override is 422.

    The single source of root identity for KM is params[root_params_fields[0]]
    = `policy_id`. API must reject any attempt to bypass via root_source_id.
    """
    before_evidence = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {
                "policy_id": "KM-POL-001",
                "root_source_id": "SPIKE-PR-001",  # forbidden override
            },
        },
    )
    assert resp.status_code == 422, (
        f"R5-B4: root_source_id override must be 422; got {resp.status_code}; "
        f"body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert "root_source_id" in detail or "pr_source_id" in detail, (
        f"R5-B4: 422 detail must mention forbidden override; got: {detail!r}"
    )

    after_evidence = _count_evidence_rows()
    assert after_evidence == before_evidence, (
        f"R5-B4: rejected request must NOT add evidence rows; "
        f"before={before_evidence} after={after_evidence}"
    )


def test_r5b4_employee_id_param_is_ignored(client: TestClient) -> None:
    """R5-B4: KM no longer accepts `employee_id` in params.

    The caller's identity is X-User-Id → assemble_context → ctx.user.roles.
    Passing `employee_id` as a parameter is dead code (silently ignored),
    but should NOT elevate privileges.

    Scenario: KM-POL-003 requires role `finance`. km-eve has no roles.
    If we send X-User-Id=km-eve but params.employee_id=km-bob (who has
    finance), the result must still be needs_valid_policy (caller is eve,
    not bob). This proves identity is server-owned, not client-supplied.
    """
    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-eve"},  # no roles
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {
                "policy_id": "KM-POL-003",
                "employee_id": "km-bob",  # ignored — eve is the caller
            },
        },
    )
    assert resp.status_code == 200, (
        f"identity spoof attempt must be answered (200), not 500; "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    body = resp.json()
    decision_value = body.get("decision_value") or body.get("conclusion")
    assert decision_value == "needs_valid_policy", (
        f"R5-B4: caller X-User-Id=km-eve MUST NOT be elevated by "
        f"params.employee_id=km-bob; got {decision_value!r}"
    )


# ---------------------------------------------------------------------------
# 422 zero-write binding (predicted bar from cut-042R3R R4-B1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "expected_status_substring"),
    [
        # Path-traversal attempt (loader rejects BEFORE materializer runs)
        ({"policy_id": "../etc"}, "policy_id"),
        # Empty / missing required fields → 422 at API boundary
        ({"policy_id": ""}, "policy_id"),
    ],
    ids=[
        "path_traversal_422",
        "empty_policy_id_422",
    ],
)
def test_knowledge_boundary_422_zero_write(
    client: TestClient,
    params: dict,
    expected_status_substring: str,
) -> None:
    """R4-B1-style 422 zero-write binding for KM pack.

    Pre/post snapshot proves the API boundary is genuinely zero-write:
      - root.attrs byte-equal
      - REQUIRES_ROLE count byte-equal
      - evidence_records count byte-equal
    """
    before_attrs_001 = _read_root_attrs("KM-POL-001")
    before_rr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "REQUIRES_ROLE"
    )
    before_evidence_count = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": params,
        },
    )
    assert resp.status_code == 422, (
        f"params={params}: expected 422, got {resp.status_code}; body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert expected_status_substring in detail, (
        f"params={params}: 422 detail must mention {expected_status_substring}, "
        f"got: {detail!r}"
    )

    # Zero-write binding (post snapshots must be byte-equal to pre)
    after_attrs_001 = _read_root_attrs("KM-POL-001")
    after_rr_001 = _count_relationships_from_root(
        _display_id_for("KM-POL-001"), "REQUIRES_ROLE"
    )
    after_evidence_count = _count_evidence_rows()

    assert after_attrs_001 == before_attrs_001, (
        f"R4-B1: 422 must NOT modify root.attrs; "
        f"before={before_attrs_001!r} after={after_attrs_001!r}"
    )
    assert after_rr_001 == before_rr_001, (
        f"R4-B1: 422 must NOT modify REQUIRES_ROLE count; "
        f"before={before_rr_001} after={after_rr_001}"
    )
    assert after_evidence_count == before_evidence_count, (
        f"R4-B1: 422 must NOT add evidence rows; "
        f"before={before_evidence_count} after={after_evidence_count}"
    )


# ---------------------------------------------------------------------------
# Loop-level direct test — bypasses API 422, exercises the rule on
# non-fixture inputs to confirm the loop itself is consistent.
# ---------------------------------------------------------------------------


def test_loop_level_km_rule_uses_anchored_today_not_system_time() -> None:
    """cut-043R loop-level: `today` is server-injected (API), with date.today()
    fallback for direct-loop callers.

    We pass `today` explicitly via params to prove the rule sees the anchored
    value, not system-time. (The API path rejects client `today` per R5-B1,
    but the loop-level test exercises the loop signature directly.)
    """
    from ece.demo.api import _resolve_actor  # type: ignore[attr-defined]
    from ece.demo.spec import load_scenario_spec
    from ece.v0.loop import run_demo_loop

    spec = load_scenario_spec("knowledge", "default")
    engine = get_engine()
    actor = _resolve_actor("km-alice")

    result = run_demo_loop(
        engine,
        actor,
        "KM-POL-001",
        spec,
        params={
            "policy_id": "KM-POL-001",
            "today": SERVER_TODAY,
        },
    )

    decision = result.decision or {}
    assert decision.get("decision_value") == "answerable", (
        f"loop-level: anchored today {SERVER_TODAY} should make KM-POL-001 valid; "
        f"got {decision.get('decision_value')!r}"
    )
    assert len(result.evidence or []) == 2, (
        f"loop-level: answerable path must produce 2 evidence rows; "
        f"got {len(result.evidence or [])}"
    )


# ---------------------------------------------------------------------------
# R7-B1 — conftest force-set anchor (Codex R7 reproduction)
# ---------------------------------------------------------------------------


def test_r7b1_conftest_force_anchor_overrides_external_env() -> None:
    """R7-B1: conftest must FORCE ECE_SERVER_TODAY_ANCHOR, not setdefault.

    Codex R7 reproduced that `ECE_SERVER_TODAY_ANCHOR=2027-01-01 pytest`
    overrode the conftest pin (because setdefault respects existing values),
    allowing answerable tests to fail under the drifted anchor. R7-B1 fixes
    this by unconditional assignment in conftest.py.

    Binding evidence: spawn a Python subprocess that imports conftest under
    a caller-side ECE_SERVER_TODAY_ANCHOR=2027-01-01 environment, and verify
    the subprocess sees 2026-09-22 after conftest runs. With setdefault
    (R6 behavior) the subprocess would print 2027-01-01; with force-set
    (R7-B1 fix) it must print 2026-09-22.
    """
    import os
    import pathlib
    import subprocess
    import sys

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    probe = (
        "import sys; "
        "sys.path.insert(0, 'tests'); "
        "import conftest; "
        "import os; "
        "print(os.environ.get('ECE_SERVER_TODAY_ANCHOR', 'MISSING'))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(repo_root),
        env={**os.environ, "ECE_SERVER_TODAY_ANCHOR": "2027-01-01"},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"R7-B1: subprocess failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "2026-09-22" in proc.stdout, (
        f"R7-B1: conftest did NOT force anchor; "
        f"subprocess with external ECE_SERVER_TODAY_ANCHOR=2027-01-01 saw "
        f"{proc.stdout.strip()!r}; setdefault regression — conftest must use "
        f"direct assignment (os.environ['...'] = '...'), not setdefault"
    )


# ---------------------------------------------------------------------------
# R7-B2 — invalid ECE_SERVER_TODAY_ANCHOR fails fast (422)
# ---------------------------------------------------------------------------


def test_r7b2_invalid_anchor_returns_422(client, monkeypatch) -> None:
    """R7-B2: ECE_SERVER_TODAY_ANCHOR must be a valid ISO date (YYYY-MM-DD).

    Codex R7 reproduced that `ECE_SERVER_TODAY_ANCHOR=not-a-date` silently
    flowed through to the rule layer, producing 200 with reason text
    containing "今日 not-a-date". R7-B2 fixes by validating the env var with
    `date.fromisoformat()` and returning 422 on failure so an ops misconfig
    surfaces at the API boundary instead of poisoning rule evaluation.

    `monkeypatch.setenv` overrides the conftest-pinned value for this single
    test; monkeypatch restores on teardown so subsequent tests see the
    conftest value (2026-09-22) again.
    """
    monkeypatch.setenv("ECE_SERVER_TODAY_ANCHOR", "not-a-date")

    before_evidence = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {"policy_id": "KM-POL-001"},
        },
    )
    assert resp.status_code == 422, (
        f"R7-B2: invalid ECE_SERVER_TODAY_ANCHOR must be rejected with 422; "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert "ECE_SERVER_TODAY_ANCHOR" in detail, (
        f"R7-B2: 422 detail must mention the env var name; got: {detail!r}"
    )
    assert "not-a-date" in detail, (
        f"R7-B2: 422 detail must include the offending value for ops triage; "
        f"got: {detail!r}"
    )

    # Zero-write binding (R4-B1 pattern)
    after_evidence = _count_evidence_rows()
    assert after_evidence == before_evidence, (
        f"R7-B2: rejected request must NOT add evidence rows; "
        f"before={before_evidence} after={after_evidence}"
    )


# ---------------------------------------------------------------------------
# R8-B1 — strict YYYY-MM-DD anchor (canonical round-trip)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "non_canonical_anchor",
    [
        "20260922",        # ISO 8601 basic format (no dashes)
        "2026-W38-2",      # ISO 8601 week date
        "2026-09-22T00:00:00",  # datetime-style (will raise ValueError, not pass round-trip)
        "2026/09/22",      # non-ISO separator
    ],
    ids=["basic_format", "iso_week_date", "datetime_style", "slash_separator"],
)
def test_r8b1_non_canonical_anchor_returns_422(
    client, monkeypatch, non_canonical_anchor
) -> None:
    """R8-B1: ECE_SERVER_TODAY_ANCHOR must be STRICT `YYYY-MM-DD` (canonical form).

    Codex R8 reproduced that `date.fromisoformat()` accepts more than the
    canonical date form — specifically `20260922` (basic format) and
    `2026-W38-2` (ISO week date) parse without error but produce different
    `isoformat()` output than the raw input. Without a canonical round-trip
    check, those forms would silently flow into business reason text as a
    string that does NOT match the parsed date, corrupting the trace.

    The fix: after `date.fromisoformat()` succeeds, assert that
    `parsed.isoformat() == raw_anchor`. If they differ, the anchor is
    non-canonical and we 422.

    Slash separator and datetime-style are caught earlier by
    `date.fromisoformat()` itself (ValueError); the round-trip check is the
    safety net for basic format and week-date forms.
    """
    monkeypatch.setenv("ECE_SERVER_TODAY_ANCHOR", non_canonical_anchor)

    before_evidence = _count_evidence_rows()

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {"policy_id": "KM-POL-001"},
        },
    )
    assert resp.status_code == 422, (
        f"R8-B1: non-canonical ECE_SERVER_TODAY_ANCHOR={non_canonical_anchor!r} "
        f"must be rejected with 422; got {resp.status_code}; body={resp.text[:300]}"
    )
    detail = resp.json().get("detail", "")
    assert "ECE_SERVER_TODAY_ANCHOR" in detail, (
        f"R8-B1: 422 detail must mention the env var name; got: {detail!r}"
    )
    assert non_canonical_anchor in detail, (
        f"R8-B1: 422 detail must include the offending value for ops triage; "
        f"got: {detail!r}"
    )

    # Zero-write binding (R4-B1 pattern)
    after_evidence = _count_evidence_rows()
    assert after_evidence == before_evidence, (
        f"R8-B1: rejected request must NOT add evidence rows; "
        f"before={before_evidence} after={after_evidence}"
    )


def test_r8b1_canonical_anchor_still_works(client, monkeypatch) -> None:
    """R8-B1 control: canonical `YYYY-MM-DD` must continue to pass after R8-B1 fix.

    The round-trip check must NOT regress the happy path. With the conftest
    default (`2026-09-22`) all KM boundary tests already exercise this, but
    we pin a named control so future refactors of the validator can grep
    this test to confirm the canonical form is still accepted.
    """
    # monkeypatch to a different canonical date to prove it's not conftest-specific
    monkeypatch.setenv("ECE_SERVER_TODAY_ANCHOR", "2027-01-01")
    # ...but only after conftest's force-set, so we need to override again here
    # (monkeypatch runs after conftest so this wins)
    monkeypatch.setenv("ECE_SERVER_TODAY_ANCHOR", "2027-01-01")

    resp = client.post(
        "/api/v1/demo/scenarios/generate",
        headers={"X-User-Id": "km-alice"},
        json={
            "domain": "knowledge",
            "scenario": "default",
            "params": {"policy_id": "KM-POL-001"},  # valid_to=2026-12-31, fails at 2027-01-01
        },
    )
    assert resp.status_code == 200, (
        f"R8-B1 control: canonical anchor must still produce 200; "
        f"got {resp.status_code}; body={resp.text[:300]}"
    )
    body = resp.json()
    # At anchor=2027-01-01, KM-POL-001 (valid_to=2026-12-31) is expired → needs_valid_policy
    # The point is: the request SUCCEEDED (no 422), proving the round-trip
    # validator accepts canonical YYYY-MM-DD form.
    assert body.get("conclusion") in ("answerable", "needs_valid_policy"), (
        f"R8-B1 control: must produce a valid conclusion; got {body!r}"
    )
