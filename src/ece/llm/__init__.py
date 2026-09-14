"""LLM client layer (per ECE/CLAUDE.md §4).

OpenAI-compatible HTTP endpoint + Mock for v0 testing. No hardcoded
vendor SDK or model name. Configuration via env:
- ECE_LLM_BASE_URL: e.g. http://localhost:11434/v1 (Ollama) or https://api.openai.com/v1
- ECE_LLM_API_KEY: bearer token (default 'EMPTY' for local)
- ECE_LLM_MODEL: model name (default 'gpt-4' or local like 'qwen2.5:14b')

If ECE_LLM_BASE_URL not set, returns MockLLM (deterministic for v0 tests).
"""
from .client import LLMClient, MockLLM, OpenAICompatibleClient, get_llm_client

__all__ = ["LLMClient", "MockLLM", "OpenAICompatibleClient", "get_llm_client"]
