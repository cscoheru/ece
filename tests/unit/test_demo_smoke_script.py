"""cut-045 — Demo deployment smoke script static binding tests.

Per `codex给cut-045的指令.md §5`: `scripts/cut_045_demo_deployment_smoke.py`
  - 通过 `DEMO_BASE_URL` env 走单一 origin
  - 10 checks (SPA / domains / 3 valid / 3 denied / 422 / 零 CDN)
  - 不得直连 API upstream

RED on cut-044R2 baseline: `scripts/cut_045_demo_deployment_smoke.py` 不存在.
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_PATH = REPO_ROOT / "scripts" / "cut_045_demo_deployment_smoke.py"


@pytest.fixture(scope="module")
def smoke_source() -> str:
    if not SMOKE_PATH.exists():
        pytest.fail(
            f"cut-045 deliverable missing: {SMOKE_PATH} "
            f"(Codex directive §5 requires this deployment smoke script)"
        )
    return SMOKE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def smoke_ast(smoke_source: str) -> ast.Module:
    """Parse the smoke script as Python AST (validates syntax + structure)."""
    try:
        return ast.parse(smoke_source)
    except SyntaxError as exc:
        pytest.fail(f"smoke script has syntax error: {exc}")


# ---------------------------------------------------------------------------
# File + syntax — RED until scripts/cut_045_demo_deployment_smoke.py 存在
# ---------------------------------------------------------------------------


def test_smoke_script_exists() -> None:
    """scripts/cut_045_demo_deployment_smoke.py must exist."""
    assert SMOKE_PATH.exists(), (
        f"cut-045 deliverable missing: {SMOKE_PATH}"
    )


def test_smoke_script_is_valid_python(smoke_ast: ast.Module) -> None:
    """smoke script must parse without SyntaxError."""
    assert isinstance(smoke_ast, ast.Module)


# ---------------------------------------------------------------------------
# DEMO_BASE_URL env injection — directive §5.1
# ---------------------------------------------------------------------------


def test_smoke_script_uses_demo_base_url_env(smoke_source: str) -> None:
    """Script must read DEMO_BASE_URL from environment (directive §5.1)."""
    assert "DEMO_BASE_URL" in smoke_source, (
        "smoke script must use DEMO_BASE_URL env (directive §5.1)"
    )
    # Allow: os.environ["DEMO_BASE_URL"], os.environ.get("DEMO_BASE_URL", ...),
    # os.getenv("DEMO_BASE_URL", ...), or DEMO_BASE_URL reference inside os.environ.getenv chain.
    patterns = (
        r'os\.environ(?:\.get)?\s*\(\s*["\']DEMO_BASE_URL',
        r"os\.getenv\s*\(\s*['\"]DEMO_BASE_URL",
    )
    if not any(re.search(p, smoke_source) for p in patterns):
        pytest.fail(
            "smoke script must read DEMO_BASE_URL via os.environ[...] / "
            "os.environ.get(...) / os.getenv(...) — none found."
        )


def test_smoke_script_has_hardcoded_localhost_fallback(smoke_source: str) -> None:
    """Script must have a sensible localhost default when DEMO_BASE_URL unset."""
    # e.g. `os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8080")`
    assert re.search(
        r'os\.environ\.get\(\s*["\']DEMO_BASE_URL["\']\s*,\s*["\']http://127\.0\.0\.1',
        smoke_source,
    ) or "DEMO_BASE_URL" in smoke_source and "8080" in smoke_source, (
        "smoke script should fall back to http://127.0.0.1:<port> when env unset"
    )


# ---------------------------------------------------------------------------
# No direct API upstream in main check path — directive §5.3
# ---------------------------------------------------------------------------


def test_smoke_script_does_not_hardcode_api_upstream(smoke_source: str) -> None:
    """Script must NOT hardcode API upstream URL (e.g. http://127.0.0.1:8765) in main path.

    The single origin (`DEMO_BASE_URL`) must be the only target. Any
    hardcoded API upstream is a R5-B3-style bypass of single-origin.
    """
    # Allow 8765 in COMMENTS only (after `#`)
    non_comment_lines = [
        line for line in smoke_source.splitlines() if not line.lstrip().startswith("#")
    ]
    non_comment = "\n".join(non_comment_lines)
    # Exclude DEMO_BASE_URL fallback patterns
    assert "127.0.0.1:8765" not in non_comment, (
        "smoke script hardcodes API upstream 127.0.0.1:8765 in main path — "
        "must route everything via DEMO_BASE_URL (directive §5.3)"
    )


# ---------------------------------------------------------------------------
# Check list completeness — directive §5.2 (10 checks)
# ---------------------------------------------------------------------------


def test_smoke_script_has_at_least_10_check_functions(smoke_ast: ast.Module) -> None:
    """Script must define at least 10 check functions (directive §5.2)."""
    check_funcs = [
        node for node in ast.walk(smoke_ast)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_check_")
    ]
    assert len(check_funcs) >= 10, (
        f"smoke script must have ≥10 _check_* functions; got {len(check_funcs)}. "
        f"(directive §5.2 lists 10 checks)"
    )


def test_smoke_script_has_main_entry(smoke_ast: ast.Module) -> None:
    """Script must have a `main()` entry point."""
    func_names = {
        node.name for node in ast.walk(smoke_ast) if isinstance(node, ast.FunctionDef)
    }
    assert "main" in func_names, "smoke script must define a `main()` entry point"


# ---------------------------------------------------------------------------
# Zero CDN check — directive §5.2.10
# ---------------------------------------------------------------------------


def test_smoke_script_has_zero_cdn_check(smoke_source: str) -> None:
    """Script must include a 'no external CDN' check (directive §5.2.10)."""
    # Look for any check referencing https:// / CDN / external script
    assert re.search(
        r"cdn|https?://|外部\s*CDN|external",
        smoke_source,
        re.IGNORECASE,
    ), "smoke script must include zero-CDN check (directive §5.2.10)"


# ---------------------------------------------------------------------------
# PASS / SKIP / FAIL output — directive §5.4
# ---------------------------------------------------------------------------


def test_smoke_script_outputs_pass_skip_fail(smoke_source: str) -> None:
    """Output must summarize PASS= / SKIP= / FAIL= counts (directive §5.4)."""
    for token in ("PASS", "SKIP", "FAIL"):
        assert token in smoke_source, (
            f"smoke script must output {token}= counts (directive §5.4)"
        )


def test_smoke_script_is_executable() -> None:
    """Smoke script should have a shebang + executable bit (deployment runs it)."""
    if not SMOKE_PATH.exists():
        pytest.skip("smoke script not yet shipped")
    assert os.access(SMOKE_PATH, os.X_OK), (
        "smoke script must be executable (chmod +x for deploy runbook §9)"
    )