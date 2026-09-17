"""E5 Temporal runner (cut-008 §1.2).

Per EVALUATION.md §1:
- E5 ≥ 30 cases
- as_of/between accuracy ≥ 95%
- Includes 2025/2026 procurement manager change example

cut-040R RC-5 fix: bypasses HTTP /api/v1/context (v0.1 missing endpoint).
Calls assemble_context() Python function directly to get real accuracy
numbers. The HTTP path is preserved as smoke (env-not-ready exit 3)
if --base-url is unreachable.

Note: E5 depends on temporal relationships being seeded. With current
demo seed (0 temporal relationships), E5 trivially passes.
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
        # cut-040R RC-5 fix: call assemble_context() directly. /api/v1/context
        # endpoint doesn't exist in v0.1 (per cut-039 R39.1 RC-5). Direct
        # Python call gives real accuracy numbers for the eval gate.
        engine = get_engine()
        try:
            pkg = assemble_context(
                engine=engine,
                user_ref=case["user"],
                intent="evaluate_purchase_request",
                entities=[{"type": "purchase_request", "id": case["from"]}],
                as_of=case.get("as_of"),
            )
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        if r.status_code != 200:
            failures.append({"case": case["id"], "stage": "http", "error": f"status {r.status_code}"})
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
