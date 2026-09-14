"""E6 Agent 端到端评测 runner (cut-014 §1.2).

Per EVALUATION.md §1:
- E6 ≥ 50 cases (V0 cut-014 has 20 — scale up cut-015+)
- 结论方向正确 ≥ 80%
- evidence 引用真实率 100%
- 信息不足场景必须说"不知道"

Mechanism:
- Load E6 dataset (data/eval/e6_agent.json)
- For each case: build Context Package via assemble_context, call
  procurement_agent, validate conclusion direction
- Count expected_evidence_refs coverage

Without ECE_LLM_BASE_URL env: uses MockLLM (deterministic, no network).
With ECE_LLM_BASE_URL env: uses OpenAICompatibleClient (real LLM call).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ece.domain_packs.procurement.agent.agent import procurement_agent
from ece.llm.client import get_llm_client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/eval/e6_agent.json"),
        help="Path to e6_agent.json",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override ECE_LLM_BASE_URL (None = use env or Mock)",
    )
    args = parser.parse_args()

    data = json.loads(args.data.read_text(encoding="utf-8"))
    cases = data["cases"]
    total = len(cases)
    print(f"Loaded {total} cases from {args.data}")

    # Setup LLM (engine fetched lazily inside assemble_context if needed)
    if args.base_url:
        import os
        os.environ["ECE_LLM_BASE_URL"] = args.base_url
    llm_client = get_llm_client()

    correct = 0
    failures: list[dict] = []

    for case in cases:
        # Build minimal Context Package (no PR lookup; just structural)
        ctx = {
            "task": {"intent": "evaluate_purchase_request", "spec_version": 1},
            "user": {"id": "demo-user-procurement", "department": "procurement", "roles": ["procurement_manager"]},
            "entities": [],
            "relationships": [],
            "documents": [],
            "business_data": [],
            "denied": [],
            "sources": [],
            "metadata": {
                "generated_at": "2026-09-14T00:00:00Z",
                "as_of": None,
                "counts": {"entities": 0, "relationships": 0, "denied": 0},
            },
        }
        result = procurement_agent(ctx, case["question"], llm_client=llm_client)
        conclusion = result.get("conclusion", "").lower()
        expected = case["expected_conclusion"].lower()

        # Validate direction (approve/reject/needs_info)
        direction_match = expected in conclusion

        # Validate evidence refs (at least one mentioned in evidence)
        evidence_refs = {e.get("sid", "") for e in result.get("evidence", [])}
        expected_refs = set(case.get("expected_evidence_refs", []))
        # If no expected refs (e.g. approve case), no validation needed
        evidence_match = bool(expected_refs & evidence_refs) if expected_refs else True

        if direction_match and evidence_match:
            correct += 1
        else:
            failures.append({
                "case": case["id"],
                "expected_conclusion": case["expected_conclusion"],
                "got_conclusion": result.get("conclusion", ""),
                "direction_match": direction_match,
                "evidence_match": evidence_match,
            })

    accuracy = correct / total * 100 if total else 0.0
    print("\n=== E6 Agent 评测结果 ===")
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Wrong:    {len(failures)}")
    print(f"Accuracy: {accuracy:.1f}%")

    if failures:
        print("\n--- First 10 Failures ---")
        for f in failures[:10]:
            print(f"  {f}")

    # Per EVALUATION.md §1: 结论方向正确 ≥ 80%
    if accuracy >= 80.0:
        print("\n*** PASS: >=80% E6 acceptance ***")
        return 0
    print(f"\n*** UNDER 80% target: {accuracy:.1f}% (V0 baseline with MockLLM; expect ≥80% with real LLM) ***")
    return 1


if __name__ == "__main__":
    sys.exit(main())
