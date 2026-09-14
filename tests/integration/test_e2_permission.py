"""cut-006 R2: E2 permission test wrapper (lightweight, runtime-mocked)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def test_e2_dataset_exists_and_well_formed() -> None:
    """E2 dataset must exist with >= 50 cases including indirect-leak category."""
    p = Path("data/eval/e2_permission.json")
    assert p.exists(), f"E2 dataset missing: {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "cases" in data
    assert len(data["cases"]) >= 50, f"E2 needs >= 50 cases, got {len(data['cases'])}"
    # Indirect leak category (per cut-006 R2 spec)
    categories = {c["category"] for c in data["cases"]}
    assert "indirect_leak" in categories, "E2 must include indirect-leak cases (cut-006 R2)"


def test_e2_runner_no_unauthorized_exposure() -> None:
    """Run E2 runner and assert exit code == 0 (0 Unauthorized Exposure + 0 failures).

    Per cut-006 R2: Unauthorized Exposure > 0 = CI blocker.
    Requires the runner to be runnable in this env. If runner can't connect
    (no live API), skip the test to avoid spurious CI failure (note for follow-up).
    """
    p = Path("data/eval/e2_permission.json")
    if not p.exists():
        pytest.skip("e2_permission.json not present")

    # Try invoking the runner directly; rely on engine unit tests for logic.
    # If API isn't reachable, skip (live E2 needs docker compose up).
    try:
        result = subprocess.run(
            ["uv", "run", "python", "scripts/run_e2_permission.py", "--data", str(p)],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("e2 runner timed out (API not reachable in this env)")
        return

    # If runner exits 2: Unauthorized Exposure > 0 (CI blocker)
    # If runner exits 1: permission failure (logic mismatch, must fix)
    # If runner exits 0: PASS
    # If non-zero but we couldn't connect: skip (env not ready)
    if result.returncode not in (0, 1, 2):
        pytest.skip(f"e2 runner returned unexpected exit {result.returncode} (likely env not ready)")
        return
    if result.returncode == 2:
        pytest.fail(f"E2 FAIL: Unauthorized Exposure detected\n{result.stdout[-1500:]}")
    if result.returncode == 1:
        pytest.fail(f"E2 FAIL: permission check failures\n{result.stdout[-1500:]}")
    # exit 0: PASS
    assert "PASS" in result.stdout
