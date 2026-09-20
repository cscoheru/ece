"""E3 Context Completeness runner (cut-008 §1.2).

Per EVALUATION.md §1:
- E3 ≥ 100 cases
- ≥ 90% task gets all Required Context
- On miss: must report insufficient_context

cut-040R-2 R40R2.7 (runner ↔ runtime contract fix):
  `assemble_context()` returns a **ContextPackage dataclass**, not a dict — see
  `src/ece/context/assembly.py` (11 fields + `.to_dict()`). This runner used to
  call `pkg.get(...)`, which raised
  `AttributeError: 'ContextPackage' object has no attribute 'get'`.
  Fix: convert via `.to_dict()`, which preserves the dict shape the helpers
  below (`_collect_refs` / `_check_case`) were written against.
  Test semantics and expectations are unchanged.

  (Historical note: an earlier revision bypassed HTTP /api/v1/context on the
  belief that the endpoint did not exist in v0.1. It does exist — it was added
  in bdf30ec and returns 422 on bad params, not 404. The direct-Python path is
  kept because it removes the HTTP layer as a variable, not because the
  endpoint is missing.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ece.context.assembly import assemble_context
from ece.db import get_engine


def _collect_refs(pkg: dict) -> set[str]:
    """Extract all refs from package (entities, relationship endpoints, docs, rows)."""
    refs: set[str] = set()
    for ent in pkg.get("entities", []):
        refs.add(ent.get("ref", ""))
    for rel in pkg.get("relationships", []):
        refs.add(rel.get("from", ""))
        refs.add(rel.get("to", ""))
    for doc in pkg.get("documents", []):
        refs.add(doc.get("doc", ""))
    for row in pkg.get("business_data", []):
        refs.add(row.get("ref", ""))
    return refs - {""}


def _check_case(case: dict, pkg: dict, refs: set[str]) -> tuple[bool, str]:
    """Validate case against pkg. Returns (correct, reason)."""
    expect = case.get("expect", "ok")
    insufficient = pkg.get("metadata", {}).get("insufficient_context", False)
    required = set(case.get("required_refs", []))
    must_not = set(case.get("must_not_include", []))

    if expect == "insufficient_context":
        if not insufficient:
            return False, "expected insufficient_context, got ok"
        return True, ""

    if expect == "ok":
        if insufficient:
            return False, "expected ok, got insufficient_context"
        missing = required - refs
        if missing:
            return False, f"missing refs: {sorted(missing)}"
        leaked = must_not & refs
        if leaked:
            return False, f"must_not_include leaked: {sorted(leaked)}"
        return True, ""

    return False, f"unknown expect: {expect}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/eval/e3_context.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    cases = data["cases"]
    total = len(cases)
    print(f"Loaded {total} cases from {args.data}")

    correct = 0
    failures: list[dict] = []

    for case in cases:
        root = case.get("root", {})
        engine = get_engine()
        try:
            # R40R2.7: assemble_context() returns ContextPackage (dataclass).
            # .to_dict() restores the dict shape the helpers below expect.
            pkg = assemble_context(
                engine=engine,
                user_ref=case["user"],
                intent=case["intent"],
                entities=[root] if root.get("id") else [],
                as_of=None,
            ).to_dict()
        except Exception as e:
            failures.append({"case": case["id"], "stage": "request", "error": str(e)})
            continue

        refs = _collect_refs(pkg)
        ok, reason = _check_case(case, pkg, refs)
        if ok:
            correct += 1
        else:
            failures.append({"case": case["id"], "reason": reason})

    accuracy = correct / total * 100 if total else 0.0
    print("\n=== E3 Context Completeness Results ===")
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Wrong:    {len(failures)}")
    print(f"Accuracy: {accuracy:.1f}%")

    if failures:
        print("\n--- First 10 Failures ---")
        for f in failures[:10]:
            print(f"  {f}")

    if accuracy >= 90.0:
        print("\n*** PASS: >=90% R3 acceptance ***")
        return 0
    print(f"\n*** UNDER 90% target: {accuracy:.1f}% (R3: report under-target with gap analysis) ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
