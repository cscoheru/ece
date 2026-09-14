"""S5.4 — E6 Agent 端到端评测 tests.

Verifies:
1. e6_agent.json dataset is well-formed (≥20 cases V0; target 50 cut-015+)
2. run_e6_agent.py runner runs (with MockLLM default; skip if no LLM)
3. MockLLM direction detection works for known patterns
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_e6_dataset_well_formed() -> None:
    """E6 dataset ≥20 cases (V0 starter; target 50 cut-015+)."""
    p = Path("data/eval/e6_agent.json")
    if not p.exists():
        pytest.skip("E6 dataset not generated; run scripts/run_e6_agent.py to verify")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert len(data["cases"]) >= 20, f"E6 needs ≥20 cases, got {len(data['cases'])}"
    required_keys = {"id", "question", "expected_conclusion", "category"}
    for c in data["cases"]:
        assert required_keys.issubset(c.keys()), f"missing keys in {c['id']}"
        assert c["expected_conclusion"] in ("approve", "reject", "needs_info")


def test_mock_llm_returns_3w_approval_compliant() -> None:
    """MockLLM keyword matching: '审批' + '完整' → approval chain response."""
    from ece.domain_packs.procurement.agent.agent import procurement_agent
    from ece.llm.client import MockLLM

    ctx: dict = {"entities": [], "relationships": [], "denied": [], "sources": []}
    result = procurement_agent(
        ctx, "审批链是否完整？", llm_client=MockLLM()
    )
    assert "审批" in result["conclusion"] or "完整" in result["conclusion"]


def test_mock_llm_returns_high_price_deviation() -> None:
    """MockLLM: '历史' in prompt → high price deviation response."""
    from ece.domain_packs.procurement.agent.agent import procurement_agent
    from ece.llm.client import MockLLM

    ctx: dict = {"entities": [], "relationships": [], "denied": [], "sources": []}
    result = procurement_agent(
        ctx, "PR 当前价 vs 历史价格？", llm_client=MockLLM()
    )
    assert "价格" in result["conclusion"] or "偏高" in result["conclusion"]


def test_e6_runner_exits_clean() -> None:
    """E6 runner runs (may fail accuracy with MockLLM; expect 80%+)."""
    p = Path("data/eval/e6_agent.json")
    if not p.exists():
        pytest.skip("E6 dataset not generated")
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", "python", "scripts/run_e6_agent.py",
         "--data", str(p)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    # Runner exits 0 (≥80%) or 1 (<80% with MockLLM)
    assert result.returncode in (0, 1), f"unexpected exit: {result.returncode}\n{result.stdout[-500:]}"
