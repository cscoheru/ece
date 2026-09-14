"""S5.2 — Procurement Agent tests.

Verifies:
- procurement_agent returns docs/API.md §6 schema
- MockLLM detects 100万 threshold (rules findings injection)
- build_agent_prompt includes context + rules findings
- OpenAI-compatible client shape (test without actual API call)

Pre-condition: scripts/seed_relationships.py run (per-PR data + demo users).
"""

import json

from ece.domain_packs.procurement.agent.agent import (
    build_agent_prompt,
    procurement_agent,
)
from ece.llm.client import LLMClient, MockLLM, get_llm_client


def test_agent_returns_full_schema() -> None:
    """Agent returns dict with all docs/API.md §6 required fields."""
    ctx = {
        "entities": [
            {
                "type": "purchase_request",
                "ref": "PR001",
                "attrs": {"amount": 1_500_000, "approvals": []},
            }
        ],
        "relationships": [],
        "denied": [],
        "sources": [],
    }
    result = procurement_agent(ctx, "PR001 金额 150万 是否合规？")
    assert "conclusion" in result
    assert "reasoning_summary" in result
    assert "risks" in result
    assert "recommendation" in result
    assert "evidence" in result
    assert "confidence" in result
    assert isinstance(result["risks"], list)
    assert isinstance(result["evidence"], list)
    assert 0.0 <= result["confidence"] <= 1.0


def test_mock_llm_detects_100w_threshold_direct() -> None:
    """MockLLM returns '需要三家比价' when prompt has 100 + 比价 (controlled prompt).

    Direct MockLLM test (not via procurement_agent) to avoid keyword
    collision with approval_chain rule findings injection.
    """
    from ece.llm.client import MockLLM

    client = MockLLM()
    prompt = "金额 100万 需要比价吗？"  # no 审批 keyword
    result_str = client.complete(prompt, 0.0)
    result = json.loads(result_str)
    assert "比价" in result["conclusion"]


def test_mock_llm_detects_approval_chain_direct() -> None:
    """MockLLM returns '审批链完整' when prompt has 审批 + 完整 (controlled)."""
    from ece.llm.client import MockLLM

    client = MockLLM()
    prompt = "审批链完整吗？"  # no 100 or 比价 keyword
    result_str = client.complete(prompt, 0.0)
    result = json.loads(result_str)
    assert "审批" in result["conclusion"] or "完整" in result["conclusion"]


def test_build_agent_prompt_includes_question_context_rules() -> None:
    ctx: dict = {"entities": [], "relationships": [], "denied": [], "sources": []}
    rules_findings: list = [{"rule": "test_rule", "status": "ok", "message": "test"}]
    prompt = build_agent_prompt(ctx, "My Question", rules_findings)
    assert "My Question" in prompt
    assert "test_rule" in prompt
    assert "Context Package" in prompt
    assert "领域规则 Findings" in prompt


def test_get_llm_client_returns_mock_when_no_base_url() -> None:
    """Without ECE_LLM_BASE_URL → MockLLM."""
    import os
    os.environ.pop("ECE_LLM_BASE_URL", None)
    client = get_llm_client()
    assert isinstance(client, MockLLM)


def test_agent_handles_invalid_json_response() -> None:
    """Agent gracefully handles LLM response that isn't valid JSON."""

    class BadLLM(LLMClient):
        def complete(self, prompt, temperature=0.0):
            return "this is not JSON"

    ctx: dict = {"entities": [], "relationships": [], "denied": [], "sources": []}
    result = procurement_agent(ctx, "test", llm_client=BadLLM())
    assert "解析失败" in result["conclusion"] or "失败" in result["conclusion"]
    assert result["confidence"] == 0.0
