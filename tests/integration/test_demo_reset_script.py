"""cut-045 — Demo reset-fixtures script binding tests.

Per `codex给cut-045的指令.md §4.1.4`:
  - alembic upgrade head
  - seed procurement fixture
  - seed knowledge fixture
  - seed compliance fixture
  - 一键重置 demo fixture

RED on cut-044R2 baseline: `deploy/scripts/reset-demo-fixtures.sh` 不存在.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RESET_SCRIPT = REPO_ROOT / "deploy" / "scripts" / "reset-demo-fixtures.sh"


@pytest.fixture(scope="module")
def script_text() -> str:
    if not RESET_SCRIPT.exists():
        pytest.fail(
            f"cut-045 deliverable missing: {RESET_SCRIPT} "
            f"(Codex directive §4.1.4 requires this reset script)"
        )
    return RESET_SCRIPT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File + executable bit
# ---------------------------------------------------------------------------


def test_reset_script_exists() -> None:
    """deploy/scripts/reset-demo-fixtures.sh must exist."""
    assert RESET_SCRIPT.exists(), f"reset script missing: {RESET_SCRIPT}"


def test_reset_script_is_executable() -> None:
    """Reset script must be executable (chmod +x; deployment runs it)."""
    if not RESET_SCRIPT.exists():
        pytest.skip("reset script not yet shipped")
    assert os.access(RESET_SCRIPT, os.X_OK), (
        "reset script must be executable (chmod +x for deploy runbook §9.10)"
    )


def test_reset_script_has_shebang(script_text: str) -> None:
    """Reset script must declare a shebang (bash/sh)."""
    assert script_text.startswith("#!"), "reset script must start with shebang"
    assert re.search(r"#!/(?:bin/bash|bin/sh|usr/bin/env bash)", script_text), (
        "reset script shebang must be bash or sh"
    )


# ---------------------------------------------------------------------------
# Required operations — directive §4.1.4
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "required_token",
    [
        "alembic upgrade head",
        "seed_v0_spike_fixture",  # procurement
        "seed_knowledge_fixture",
        "seed_compliance_fixture",
    ],
)
def test_reset_script_invokes_required_command(script_text: str, required_token: str) -> None:
    """Reset script must invoke alembic upgrade + 3 seed scripts (directive §4.1.4)."""
    assert required_token in script_text, (
        f"reset script missing required command {required_token!r}"
    )


def test_reset_script_references_working_directory_resolution(script_text: str) -> None:
    """Reset script must resolve its own location (cd $(dirname ...)/../..) to find repo root.

    Per directive, deployment runs from any cwd; script must locate the
    project root so alembic + seeds are invokable.
    """
    assert re.search(
        r"cd\s+\$\(?dirname", script_text
    ) or re.search(
        r"cd\s+`dirname", script_text
    ) or "BASH_SOURCE" in script_text or "SCRIPT_DIR" in script_text, (
        "reset script must `cd $(dirname $0)/../..` (or similar) to find repo root"
    )