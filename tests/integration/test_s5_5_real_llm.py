"""S5.4 follow-up — Real LLM integration tests (cut-015b).

Per EVALUATION.md §1: E6 ≥80% accuracy gate. With MockLLM (cut-014/015a),
accuracy depends on keyword matching. With real LLM (set ECE_LLM_BASE_URL),
accuracy measures real Agent quality.

All tests skip if ECE_LLM_BASE_URL not set (V0 CI without real LLM).
Run with: ECE_LLM_BASE_URL=http://your-llm-endpoint/v1 \
           ECE_LLM_API_KEY=... \
           ECE_LLM_MODEL=... \
           uv run pytest tests/integration/test_s5_5_real_llm.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _real_llm_configured() -> bool:
    """True if ECE_LLM_BASE_URL is set (real LLM available)."""
    return bool(os.environ.get("ECE_LLM_BASE_URL"))


def test_openai_compatible_client_shape():
    """OpenAICompatibleClient with ECE_LLM_BASE_URL: POST /v1/chat/completions.

    Sends simple JSON prompt, validates response is valid JSON.
    Skip if no LLM endpoint configured.
    """
    if not _real_llm_configured():
        pytest.skip("ECE_LLM_BASE_URL not set; skipping real LLM client test")

    from ece.llm.client import OpenAICompatibleClient

    client = OpenAICompatibleClient(
        base_url=os.environ["ECE_LLM_BASE_URL"],
        api_key=os.environ.get("ECE_LLM_API_KEY", "EMPTY"),
        model=os.environ.get("ECE_LLM_MODEL", "gpt-4"),
    )
    result = client.complete(
        'Return JSON only: {"msg": "hello"}',
        temperature=0,
    )
    parsed = json.loads(result)
    # Either 'msg' field exists OR 'hello' substring in response
    assert "msg" in parsed or "hello" in str(parsed).lower()


def test_get_llm_client_returns_openai_compatible_when_env_set():
    """get_llm_client() returns OpenAICompatibleClient when ECE_LLM_BASE_URL set.

    Manipulates env vars in test scope to verify factory behavior.
    Skip if no real LLM env set in current process.
    """
    if not _real_llm_configured():
        pytest.skip("ECE_LLM_BASE_URL not set")

    from ece.llm.client import OpenAICompatibleClient, get_llm_client

    # Save + set + restore
    saved_base = os.environ.get("ECE_LLM_BASE_URL")
    saved_key = os.environ.get("ECE_LLM_API_KEY")
    saved_model = os.environ.get("ECE_LLM_MODEL")
    os.environ["ECE_LLM_BASE_URL"] = "http://fake-llm:8080/v1"
    os.environ["ECE_LLM_API_KEY"] = "test-key"
    os.environ["ECE_LLM_MODEL"] = "test-model"
    try:
        client = get_llm_client()
        assert isinstance(client, OpenAICompatibleClient)
        assert client.base_url == "http://fake-llm:8080/v1"
        assert client.model == "test-model"
    finally:
        if saved_base is None:
            os.environ.pop("ECE_LLM_BASE_URL", None)
        else:
            os.environ["ECE_LLM_BASE_URL"] = saved_base
        if saved_key is None:
            os.environ.pop("ECE_LLM_API_KEY", None)
        else:
            os.environ["ECE_LLM_API_KEY"] = saved_key
        if saved_model is None:
            os.environ.pop("ECE_LLM_MODEL", None)
        else:
            os.environ["ECE_LLM_MODEL"] = saved_model


def test_e6_runner_real_llm_accuracy_above_80_percent():
    """E6 runner with real LLM: ≥80% accuracy (EVALUATION.md §1 gate).

    Runs scripts/run_e6_agent.py subprocess with --base-url, parses accuracy
    from output, asserts ≥80% per EVALUATION.md §1 SLA.
    Skip if no LLM endpoint OR dataset not generated.
    """
    if not _real_llm_configured():
        pytest.skip("ECE_LLM_BASE_URL not set; skipping real LLM E6 accuracy test")

    p = Path("data/eval/e6_agent.json")
    if not p.exists():
        pytest.skip("E6 dataset not generated; run scripts/run_e6_agent.py to verify")

    result = subprocess.run(
        [
            sys.executable, "-m", "uv", "run", "python", "scripts/run_e6_agent.py",
            "--data", str(p), "--base-url", os.environ["ECE_LLM_BASE_URL"],
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,  # 50 cases × real LLM latency
    )
    # Parse accuracy from output
    accuracy = None
    for line in result.stdout.splitlines():
        if "Accuracy:" in line:
            try:
                accuracy = float(line.split("Accuracy:")[1].strip().rstrip("%"))
                break
            except (IndexError, ValueError):
                pass
    if accuracy is None:
        pytest.fail(
            f"Accuracy line not found in runner output.\n"
            f"stdout (last 500): {result.stdout[-500:]}\n"
            f"stderr (last 200): {result.stderr[-200:]}"
        )
    assert accuracy >= 80.0, (
        f"real LLM E6 accuracy {accuracy}% < 80% gate "
        f"(EVALUATION.md §1 baseline; ≥80% required for production cut-over)"
    )
