"""S5.2 — Procurement Agent: Context Package + Question → structured output.

Per docs/API.md §6 schema:
  {
    "request_id": str,
    "conclusion": str,
    "reasoning_summary": str,
    "risks": [{"type", "detail", "evidence_sid"}],
    "recommendation": str,
    "evidence": [{"sid", "fact", "src"}],
    "confidence": float,
  }

Per ECE/CLAUDE.md: LLM call via OpenAI-compatible endpoint (env ECE_LLM_*).
Per ADR-006 + ECE/CLAUDE.md iron rule: 禁止硬编码厂商 SDK 或模型名.
Per docs/API.md §6: rules findings 注入 prompt before LLM call.
"""
from __future__ import annotations

import json
from typing import Any

from ece.llm.client import get_llm_client


def build_agent_prompt(
    context_package: dict,
    question: str,
    rules_findings: list[dict],
) -> str:
    """Build LLM prompt with context + question + rules findings (per docs/API.md §6).

    Rules findings 注入 prompt before LLM call so the LLM knows
    deterministic facts (e.g. 100万 threshold violated) before reasoning.
    """
    context_json = json.dumps(context_package, ensure_ascii=False, indent=2)
    rules_json = json.dumps(rules_findings, ensure_ascii=False, indent=2)

    return (
        "你是企业采购分析助手。基于以下 Context Package 和领域规则 findings 回答问题。\n\n"
        "# 用户问题\n"
        f"{question}\n\n"
        "# Context Package\n"
        f"{context_json}\n\n"
        "# 领域规则 Findings (pre-LLM 注入)\n"
        f"{rules_json}\n\n"
        "# 输出要求\n"
        "请输出严格 JSON (无额外文字):\n"
        "{\n"
        '  "conclusion": "<结论>",\n'
        '  "reasoning_summary": "<推理总结>",\n'
        '  "risks": [{"type": "<risk_type>", "detail": "<risk_detail>", '
        '"evidence_sid": "<sid>"}],\n'
        '  "recommendation": "<建议>",\n'
        '  "evidence": [{"sid": "<sid>", "fact": "<fact>", '
        '"src": {"system": "<sys>", "record_id": "<id>"}}],\n'
        '  "confidence": <0.0-1.0>\n'
        "}\n"
    )


def procurement_agent(
    context_package: dict,
    question: str,
    llm_client=None,
) -> dict[str, Any]:
    """Run procurement agent on context + question.

    Returns structured output per docs/API.md §6 schema.
    """
    # 1. Apply domain rules (pre-LLM, per docs/API.md §6)
    from ece.domain_packs.procurement.agent.rules import apply_domain_rules

    rules_findings = apply_domain_rules(context_package, question)

    # 2. Build prompt with context + rules findings
    prompt = build_agent_prompt(context_package, question, rules_findings)

    # 3. Call LLM (per ECE/CLAUDE.md §4)
    client = llm_client or get_llm_client()
    response_text = client.complete(prompt, temperature=0.0)

    # 4. Parse response (graceful fallback if not JSON)
    try:
        output = json.loads(response_text)
    except json.JSONDecodeError:
        return {
            "conclusion": "解析失败",
            "reasoning_summary": (
                f"LLM 响应不是有效 JSON: {response_text[:200]}"
            ),
            "risks": [],
            "recommendation": "请检查 LLM 配置",
            "evidence": [],
            "confidence": 0.0,
        }

    # 5. Ensure schema completeness (per docs/API.md §6)
    output.setdefault("conclusion", "")
    output.setdefault("reasoning_summary", "")
    output.setdefault("risks", [])
    output.setdefault("recommendation", "")
    output.setdefault("evidence", [])
    output.setdefault("confidence", 0.5)

    return output
