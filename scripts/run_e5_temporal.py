"""E5 Temporal runner (cut-008 §1.2).

Per EVALUATION.md §1:
- E5 ≥ 30 cases
- as_of/between accuracy ≥ 95%
- Includes 2025/2026 procurement manager change example

cut-040R-2 R40R2.7 (runner ↔ runtime contract fix):
  1. `assemble_context()` returns a **ContextPackage dataclass**, not a dict.
     `pkg.get(...)` raised `AttributeError: 'ContextPackage' object has no
     attribute 'get'`. Fix: convert via `.to_dict()`.
  2. The dataset's `as_of` is an ISO **string**; `assemble_context()` is typed
     `as_of: date | None`. Passing the raw string raised
     `'str' object has no attribute 'isoformat'`. Fix: `date.fromisoformat()`
     at the boundary.
  Test semantics, expectations and the dataset are unchanged.

Note: E5 depends on temporal relationships being seeded.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ece.context.assembly import assemble_context
from ece.db import get_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/eval/e5_temporal.json"))
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
        # R40R2.7: `as_of` in the dataset is an ISO string ("2024-01-01") but
        # assemble_context() is typed `as_of: date | None`. Passing the raw
        # string raised `'str' object has no attribute 'isoformat'` deep inside
        # the pipeline. Convert at the boundary — the dataset is unchanged.
        raw_as_of = case.get("as_of")
        as_of = date.fromisoformat(raw_as_of) if raw_as_of else None
        try:
            # R40R2.7: assemble_context() returns ContextPackage (dataclass);
            # .to_dict() restores the dict shape this runner expects.
            pkg = assemble_context(
                engine=engine,
                user_ref=case["user"],
                intent="evaluate_purchase_request",
                entities=[{"type": "purchase_request", "id": case["from"]}],
                as_of=as_of,
            ).to_dict()
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        rels = pkg.get("relationships", [])
        count = len(rels)
        expected = case.get("expected_count", 0)

        if count == expected:
            correct += 1
        else:
            failures.append({
                "case": case["id"],
                "reason": f"count {count} expected {expected}",
            })

    accuracy = correct / total * 100 if total else 0.0
    print("\n=== E5 Temporal Results ===")
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Wrong:    {len(failures)}")
    print(f"Accuracy: {accuracy:.1f}%")

    if failures:
        print("\n--- First 10 Failures ---")
        for f in failures[:10]:
            print(f"  {f}")

    if accuracy >= 95.0:
        print("\n*** PASS: >=95% R3 acceptance ***")
        return 0
    print(f"\n*** UNDER 95% target: {accuracy:.1f}% ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
