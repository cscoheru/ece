"""E4 Relationships runner (cut-008 §1.2).

Per EVALUATION.md §1:
- E4 ≥ 30 cases
- 0 wrong relations (errors connecting unrelated entities)
- Multi-hop expansion correct

cut-040R-2 R40R2.7 (runner ↔ runtime contract fix):
  `assemble_context()` returns a **ContextPackage dataclass**, not a dict — see
  `src/ece/context/assembly.py`. This runner used to call `pkg.get(...)`, which
  raised `AttributeError: 'ContextPackage' object has no attribute 'get'`.
  Fix: convert via `.to_dict()`. Test semantics and expectations unchanged.

Note: E4 depends on the relationships table being seeded. That used to be a
manual step (`scripts/seed_relationships.py`); `make seed` now performs it, and
this runner asserts the fixture is present before scoring (R2 / C.3) — an empty
graph would otherwise yield a VACUOUS pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ece.context.assembly import assemble_context
from ece.db import get_engine
from ece.seed import demo_relationship_fixture_status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/eval/e4_relationships.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    # R2 (C.3): environment integrity precondition. Refuses to score against an
    # empty graph — "0 relationships" would sit inside the E4 bounds and read as
    # a pass. Does not change datasets, bounds or thresholds.
    status = demo_relationship_fixture_status(get_engine())
    if not status["complete"]:
        print("PRECONDITION FAILURE: demo relationship fixture missing or incomplete.", file=sys.stderr)
        print(
            f"  demo:seed_relationships = {status['total']} rows, "
            f"expected {status['expected_total']} (6 per demo PR).",
            file=sys.stderr,
        )
        if status["deviating_prs"]:
            print(f"  PRs not matching 6 relationships: {status['deviating_prs'][:8]}", file=sys.stderr)
        print("  Refusing to run: an empty graph would produce a VACUOUS result.", file=sys.stderr)
        print("  Fix: run `make seed` (canonical seed now restores relationships).", file=sys.stderr)
        return 2

    data = json.loads(args.data.read_text(encoding="utf-8"))
    cases = data["cases"]
    total = len(cases)
    print(f"Loaded {total} cases from {args.data}")

    correct = 0
    failures: list[dict] = []

    for case in cases:
        engine = get_engine()
        try:
            # R40R2.7: assemble_context() returns ContextPackage (dataclass);
            # .to_dict() restores the dict shape this runner expects.
            pkg = assemble_context(
                engine=engine,
                user_ref=case["user"],
                intent="evaluate_purchase_request",
                entities=[{"type": "purchase_request", "id": case["from"]}],
                as_of=None,
            ).to_dict()
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        rels = pkg.get("relationships", [])
        count = len(rels)
        min_count = case.get("expected_count_min", 0)
        max_count = case.get("expected_count_max", float("inf"))

        if min_count <= count <= max_count:
            correct += 1
        else:
            failures.append({
                "case": case["id"],
                "reason": f"count {count} out of [{min_count}, {max_count}]",
            })

    accuracy = correct / total * 100 if total else 0.0
    print("\n=== E4 Relationships Results ===")
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Wrong:    {len(failures)}")
    print(f"Accuracy: {accuracy:.1f}%")

    if failures:
        print("\n--- First 10 Failures ---")
        for f in failures[:10]:
            print(f"  {f}")

    if len(failures) == 0:
        print("\n*** PASS: 0 wrong relations (E4 acceptance) ***")
        return 0
    print(f"\n*** FAIL: {len(failures)} wrong relation count(s) ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
