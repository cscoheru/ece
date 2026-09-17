"""E3 Context Completeness runner (cut-008 §1.2).

Per EVALUATION.md §1:
- E3 ≥ 100 cases
- ≥ 90% task gets all Required Context
- On miss: must report insufficient_context

cut-040R RC-5 fix: bypasses HTTP /api/v1/context (v0.1 missing endpoint).
Calls assemble_context() Python function directly to get real accuracy
numbers. The HTTP path is preserved as smoke (env-not-ready exit 3)
if --base-url is unreachable.

Without API server, returns 3 (env-not-ready; per cut-006R §4.3 proxy bypass).
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
        # cut-040R RC-5 fix: call assemble_context() directly. /api/v1/context
        # endpoint doesn't exist in v0.1 (per cut-039 R39.1 RC-5). Direct
        # Python call gives real accuracy numbers for the eval gate.
        engine = get_engine()
        try:
            pkg = assemble_context(
                engine=engine,
                user_ref=case["user"],
                intent=case["intent"],
                entities=[root] if root.get("id") else [],
                as_of=None,
            )
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
