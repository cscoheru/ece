"""LLM client (per ECE/CLAUDE.md §4 + ADR-006).

OpenAI-compatible HTTP endpoint. Configuration via env:
- ECE_LLM_BASE_URL: e.g. http://localhost:11434/v1 (Ollama) or https://api.openai.com/v1
- ECE_LLM_API_KEY: bearer token (default 'EMPTY' for local)
- ECE_LLM_MODEL: model name (default 'gpt-4' or local model like 'qwen2.5:14b')

If ECE_LLM_BASE_URL not set, returns MockLLM (deterministic for v0 tests).
"""
from __future__ import annotations

import json
import os
import urllib.request


class LLMClient:
    """Abstract LLM client interface (per ECE/CLAUDE.md §4)."""

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        """Call LLM with prompt, return response text (typically JSON)."""
        raise NotImplementedError


class MockLLM(LLMClient):
    """Deterministic mock LLM (v0 testing; per ECE/CLAUDE.md no hardcoded vendor).

    Returns structured JSON responses based on prompt keywords. Used by
    E2E Agent tests when ECE_LLM_BASE_URL not configured.
    """

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        """Return deterministic JSON based on question + rules findings status.

        Per cut-015a §4.1: status-field-based matching instead of fragile
        substring match. Extracts the question from prompt (between
        "# 用户问题" and "# Context Package") to determine what the user
        is asking about, then checks the corresponding rule's status field.

        Falls back to substring match if question can't be extracted.
        """
        # Extract question from prompt (between "# 用户问题" and "# Context Package").
        # If markers not found (direct test with bare prompt), fall back to
        # using the entire prompt as the "question" so keyword checks work.
        if "# 用户问题" in prompt and "# Context Package" in prompt:
            start = prompt.index("# 用户问题") + len("# 用户问题")
            end = prompt.index("# Context Package")
            question = prompt[start:end].strip()
        else:
            question = prompt

        # Question-driven matching (priority: what user is asking about)
        if "审批" in question:
            # approval_chain rule + status field
            if '"rule": "approval_chain"' in prompt and '"status": "violated"' in prompt:
                return json.dumps({
                    "conclusion": "审批链不完整",
                    "reasoning_summary": "缺失部分审批人",
                    "risks": [
                        {"type": "approval", "detail": "缺失部分审批人",
                         "evidence_sid": "POL-2026-03"}
                    ],
                    "recommendation": "补充缺失审批人",
                    "evidence": [],
                    "confidence": 0.85,
                }, ensure_ascii=False)
            return json.dumps({
                "conclusion": "审批链完整",
                "reasoning_summary": "部门经理 + 财务总监 + CEO 三级审批已齐。",
                "risks": [],
                "recommendation": "可以继续执行",
                "evidence": [],
                "confidence": 0.9,
            }, ensure_ascii=False)

        if "比价" in question:
            # price_comparison_threshold rule + status field
            if (
                '"rule": "price_comparison_threshold"' in prompt
                and '"status": "violated"' in prompt
            ):
                return json.dumps({
                    "conclusion": "需要三家比价",
                    "reasoning_summary": "金额 ≥ 100万阈值，需三家比价。",
                    "risks": [
                        {"type": "policy", "detail": "缺比价记录",
                         "evidence_sid": "POL-2026-03"}
                    ],
                    "recommendation": "补充三家比价材料后再进入下一审批阶段",
                    "evidence": [
                        {"sid": "POL-2026-03",
                         "fact": "100万阈值 + 三家比价要求",
                         "src": {"system": "docs", "document_id": "POL-2026-03", "page": 0}}
                    ],
                    "confidence": 0.9,
                }, ensure_ascii=False)
            return json.dumps({
                "conclusion": "无需比价",
                "reasoning_summary": "金额 < 100万阈值，无需比价。",
                "risks": [],
                "recommendation": "按正常流程执行",
                "evidence": [
                    {"sid": "POL-2026-03",
                     "fact": "< 100万阈值无需比价",
                     "src": {"system": "docs", "document_id": "POL-2026-03", "page": 0}}
                ],
                "confidence": 0.85,
            }, ensure_ascii=False)

        if "历史" in question or "historical" in question.lower():
            return json.dumps({
                "conclusion": "价格偏高",
                "reasoning_summary": "当前价高于历史平均价超过 10% 阈值。",
                "risks": [
                    {"type": "price_deviation", "detail": "高于历史价 15%",
                     "evidence_sid": "POL-2026-03"}
                ],
                "recommendation": "需要额外审批或重新议价",
                "evidence": [
                    {"sid": "POL-2026-03",
                     "fact": "价格偏离带规则：>10% 触发额外审批",
                     "src": {"system": "docs", "document_id": "POL-2026-03", "page": 0}}
                ],
                "confidence": 0.8,
            }, ensure_ascii=False)

        # Default
        return json.dumps({
            "conclusion": "未发现明确问题",
            "reasoning_summary": (
                "Mock LLM 默认响应（建议配置 ECE_LLM_BASE_URL 启用真实 LLM）"
            ),
            "risks": [],
            "recommendation": "无",
            "evidence": [],
            "confidence": 0.5,
        }, ensure_ascii=False)


class OpenAICompatibleClient(LLMClient):
    """OpenAI-compatible HTTP client (per ECE/CLAUDE.md §4)."""

    def __init__(self, base_url: str, api_key: str = "EMPTY", model: str = "gpt-4"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        """POST /v1/chat/completions; OpenAI-compatible schema."""
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def get_llm_client() -> LLMClient:
    """Factory: real LLM if ECE_LLM_BASE_URL set, else MockLLM (v0 default)."""
    base_url = os.environ.get("ECE_LLM_BASE_URL")
    if base_url:
        api_key = os.environ.get("ECE_LLM_API_KEY", "EMPTY")
        model = os.environ.get("ECE_LLM_MODEL", "gpt-4")
        return OpenAICompatibleClient(
            base_url=base_url, api_key=api_key, model=model
        )
    return MockLLM()
