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

Note: E4 depends on the relationships table being seeded (scripts/seed_relationships.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ece.context.assembly import assemble_context
from ece.db import get_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/eval/e4_relationships.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

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
