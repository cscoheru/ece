#!/usr/bin/env python3
"""S5 — V0 Technical Spike: the six-step loop, printed step by step.

    TECHNICAL SPIKE FIXTURE
    NOT CUSTOMER-VALIDATED
    NOT PRODUCT REFERENCE WORKFLOW

Runs `run_v0_loop` against the spike fixture and prints the output shape of
`docs/v0/V0_EXECUTION_SPEC.md` §11, asserting the per-step checks of §10 as it goes.

This script is the CLI half of S5. The loop itself lives in `src/ece/v0/loop.py` and
is imported, not re-implemented — one implementation, two entry points (the test suite
and this runner), which is the R2 lesson about copies drifting apart.

Usage:
    uv run python scripts/run_v0_loop.py            # seed, run, print, assert
    uv run python scripts/run_v0_loop.py --no-seed  # run against the DB as-is

Exit codes: 0 = every §10 check passed; 1 = at least one check failed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from ece.v0 import V0LoopResult, run_v0_loop

REPO = Path(__file__).resolve().parents[1]

USER_REF = "spike-user-procurement"
PR_SOURCE_ID = "SPIKE-PR-001"

# §11 states these as literals. They are the fixture's contract (see the seeder), so
# asserting them here catches a fixture that silently drifted.
EXPECTED_AMOUNT = 1_280_000
EXPECTED_QUOTES = 1
EXPECTED_DECISION_VALUE = "review_required"
EXPECTED_BEFORE_STATUS = "pending"
EXPECTED_PASSED_CONDITIONS = 2
REVIEW_KEYS = ("review_status", "review_decision_id", "review_evidence_id", "review_updated_at")


def _seed() -> None:
    """Canonical re-seed. Idempotent by contract (DELETE-then-INSERT scoped to the
    fixture's source_system) — which is also what resets `review_status` to 'pending'
    so §11's before/after line is reproducible on a second run."""
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "seed_v0_spike_fixture.py")],
        cwd=str(REPO), check=True,
    )


class Checks:
    """Collect §10's per-step checks instead of failing on the first one.

    A single missing field is rarely the only thing wrong, and a reviewer reading the
    transcript should see the whole picture, not the first brick.
    """

    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, condition: bool, step: str, message: str) -> bool:
        if not condition:
            self.failures.append(f"[{step}] {message}")
        return condition


def _print_header(user_ref: str, pr_source_id: str) -> None:
    print("INPUT")
    print(f"  user_ref = {user_ref}")
    print(f"  root     = {pr_source_id}")


def _print_and_check(result: V0LoopResult, checks: Checks) -> None:
    _print_context(result, checks)
    _print_entity(result, checks)
    _print_rule(result, checks)
    _print_decision(result, checks)
    _print_evidence(result, checks)
    _print_update(result, checks)


def _print_context(result: V0LoopResult, checks: Checks) -> None:
    print("\n[1] CONTEXT")
    print(f"  package_id = {result.package_id}")
    print(f"  counts     = {{entities: {result.counts.get('entities')}, "
          f"relationships: {result.counts.get('relationships')}}}")
    checks.ok(bool(result.package_id), "1", "package_id must be non-empty")
    checks.ok(result.package_id.startswith("ctx_"), "1",
              f"package_id {result.package_id!r} is not the ctx_<24hex> shape")
    # §10: "PR 在 entities 内"
    checks.ok(result.pr_ref is not None and result.counts.get("entities", 0) >= 1, "1",
              "the PR must be resolved and present in ctx.entities")


def _print_entity(result: V0LoopResult, checks: Checks) -> None:
    amount = result.pr_attrs_before.get("amount")
    refs = [q["record_id"] for q in result.quote_refs]
    print("\n[2] ENTITY / KNOWLEDGE")
    print(f"  pr.ref          = {result.pr_ref}   (由 source_id {PR_SOURCE_ID} 运行时解析)")
    print(f"  pr.attrs.amount = {amount}")
    print(f"  quotes          = [{', '.join(refs)}]    → len = {len(result.quotes)}")
    print(f"  knowledge       = {len(result.quotes)} 条 SELECTS 关系 + sources[]")
    checks.ok(amount == EXPECTED_AMOUNT, "2",
              f"attrs.amount is {amount!r}, expected {EXPECTED_AMOUNT}")
    checks.ok(len(result.quotes) == EXPECTED_QUOTES, "2",
              f"len(quotes) is {len(result.quotes)}, expected {EXPECTED_QUOTES}")
    # §1 addressing discipline. The fixture's PR happens to carry an explicit
    # display_id equal to its source_id (it must not perturb the shared PR### numeric
    # space), so equality proves nothing here. What does prove it: the suppliers come
    # back from the Context as display_ids and are *resolved* to their source identity.
    checks.ok(len(result.quote_refs) == len(result.quotes)
              and all(q["record_id"] for q in result.quote_refs), "2",
              "quote sources must be resolved from display_id to source identity")


def _print_rule(result: V0LoopResult, checks: Checks) -> None:
    print(f"\n[3] RULE  {result.rule_id}")
    for cond in result.conditions:
        passed = cond["passed"]
        mark = "passed=true " if passed else "passed=false"
        print(f"  {cond['name']:<23}: {cond['expr']}  (actual={cond['actual']}) → {mark}")
    passed_count = sum(1 for c in result.conditions if c["passed"])
    checks.ok(len(result.conditions) == EXPECTED_PASSED_CONDITIONS, "3",
              f"{len(result.conditions)} condition(s), expected {EXPECTED_PASSED_CONDITIONS}")
    checks.ok(passed_count == EXPECTED_PASSED_CONDITIONS, "3",
              f"{passed_count} condition(s) passed, expected {EXPECTED_PASSED_CONDITIONS}")


def _print_decision(result: V0LoopResult, checks: Checks) -> None:
    dec = result.decision or {}
    print("\n[4] DECISION")
    print(f"  decision_id    = {dec.get('decision_id')}")
    print(f"  decision_key   = {dec.get('decision_key')!r}")
    print(f"  decision_value = {dec.get('decision_value')!r}")
    print(f"  reason         = {dec.get('reason')!r}")
    checks.ok(dec.get("decision_value") == EXPECTED_DECISION_VALUE, "4",
              f"decision_value is {dec.get('decision_value')!r}, "
              f"expected {EXPECTED_DECISION_VALUE!r}")
    checks.ok(dec.get("rule_id") == result.rule_id, "4",
              "the Decision must cite the rule that produced it")


def _print_evidence(result: V0LoopResult, checks: Checks) -> None:
    print("\n[5] EVIDENCE")
    for i, ev in enumerate(result.evidence, start=1):
        src = f"{{{ev['source_system']}, {ev['source_record_id']}}}"
        print(f"  ev_{i}  claim={ev['claim']!r}")
        print(f"        source={src}  observed={ev['observed_value']} "
              f"threshold={ev['threshold_value']}")
        print(f"        input_context_ref={ev['input_context_ref']}  "
              f"ts={ev['evidence_timestamp']}")
    passed_count = sum(1 for c in result.conditions if c["passed"])
    checks.ok(len(result.evidence) == passed_count, "5",
              f"{len(result.evidence)} evidence row(s) for {passed_count} passed condition(s)")
    for ev in result.evidence:
        # §10: "可反查" — every row must carry a complete backtracking tuple.
        checks.ok(bool(ev.get("source_system") and ev.get("source_record_id")), "5",
                  f"evidence {ev.get('evidence_id')} lacks a source identity")
        checks.ok(ev.get("input_context_ref") == result.package_id, "5",
                  f"evidence {ev.get('evidence_id')} points at "
                  f"{ev.get('input_context_ref')!r}, not this package")


def _print_update(result: V0LoopResult, checks: Checks) -> None:
    before = result.pr_attrs_before.get("review_status")
    after = result.re_read_attrs.get("review_status")
    print("\n[6] CONTEXT UPDATE")
    print(f"  {PR_SOURCE_ID}.attrs.review_status : {before!r} → {after!r}")
    for key in REVIEW_KEYS[1:]:
        print(f"  + {key} = {result.re_read_attrs.get(key)!r}")

    dec = result.decision or {}
    print("\nRE-READ")
    print(f"  assemble_context(...).entities[...].attrs.review_status == "
          f"{dec.get('decision_value')!r}   {'✅' if after == dec.get('decision_value') else '❌'}")

    checks.ok(before == EXPECTED_BEFORE_STATUS, "6",
              f"pre-update review_status is {before!r}, expected {EXPECTED_BEFORE_STATUS!r}")
    checks.ok(after == dec.get("decision_value"), "6",
              f"§8 invariant broken: re-read {after!r} != decision_value "
              f"{dec.get('decision_value')!r}")
    checks.ok(all(key in result.re_read_attrs for key in REVIEW_KEYS), "6",
              f"the re-read is missing key(s): "
              f"{[k for k in REVIEW_KEYS if k not in result.re_read_attrs]}")
    # §8 is an append, not an overwrite: the fixture's own facts must survive.
    checks.ok(result.re_read_attrs.get("amount") == EXPECTED_AMOUNT, "6",
              "the update overwrote attrs.amount — §8 requires an append (`||`)")
    # §8: the id written back is the first Evidence row's.
    checks.ok(result.re_read_attrs.get("review_evidence_id") == result.evidence_ids[0], "6",
              "review_evidence_id is not the first Evidence row of this Decision")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-seed", action="store_true",
                        help="skip the canonical re-seed (default: re-seed first)")
    parser.add_argument("--user-ref", default=USER_REF)
    parser.add_argument("--pr", default=PR_SOURCE_ID)
    args = parser.parse_args(argv)

    if not args.no_seed:
        _seed()

    _print_header(args.user_ref, args.pr)
    result = run_v0_loop(args.user_ref, args.pr)

    checks = Checks()
    _print_and_check(result, checks)

    print("\n=== §10 per-step checks ===")
    if checks.failures:
        for failure in checks.failures:
            print(f"  FAIL {failure}")
        print(f"\n*** FAIL: {len(checks.failures)} check(s) failed ***")
        return 1
    print("  all checks passed")
    print("\n*** PASS: six steps chained, loop closed back onto Context ***")
    return 0


if __name__ == "__main__":
    sys.exit(main())
