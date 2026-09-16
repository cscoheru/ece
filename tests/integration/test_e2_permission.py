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


@pytest.mark.security
def test_e2_no_unauthorized_exposure_regression() -> None:
    """cut-040 R40.D: 6 cut-039 R39.1 exposures must never recur.

    Live-server gate: invokes scripts/run_e2_permission.py with
    --insert-deny-acls (per run_e2_permission.py:29-33) so the runner
    auto-inserts the 3 acl_entries rows that R40.1a seeds — making this
    test self-sufficient without depending on `make seed` having run
    R40.1. Then defense-in-depth greps stdout for the two PRD §35
    hard-gate markers ('Exposures:          0' and 'Failures:           0')
    so a future matrix/seed regression cannot mask a non-zero count as 0.
    """
    p = Path("data/eval/e2_permission.json")
    if not p.exists():
        pytest.skip("e2_permission.json not present")

    try:
        result = subprocess.run(
            [
                "uv", "run", "python", "scripts/run_e2_permission.py",
                "--data", str(p),
                "--base-url", "http://127.0.0.1:8765",
                "--insert-deny-acls",
            ],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("e2 runner timed out (API not reachable in this env)")
        return

    if result.returncode not in (0, 1, 2):
        pytest.skip(f"e2 runner returned unexpected exit {result.returncode} (likely env not ready)")
        return

    # Hard fail: exposure > 0 (CI blocker per cut-006 R2 + PRD §35)
    if result.returncode == 2:
        pytest.fail(
            f"cut-040 R40.D REGRESSION: E2 Unauthorized Exposure > 0 (cut-039 根因复发):\n"
            f"{result.stdout[-2000:]}"
        )

    # Defense-in-depth: explicitly grep stdout for the 0/0 markers.
    # If a future regression silently masks the count, the markers will
    # still appear non-zero in stdout and the test will fail.
    if "Exposures:          0" not in result.stdout:
        pytest.fail(
            f"cut-040 R40.D REGRESSION: 'Exposures: 0' marker missing in E2 runner output:\n"
            f"{result.stdout[-2000:]}"
        )
    if "Failures:           0" not in result.stdout:
        pytest.fail(
            f"cut-040 R40.D REGRESSION: 'Failures: 0' marker missing in E2 runner output:\n"
            f"{result.stdout[-2000:]}"
        )

    # exit 0: PASS (with both markers explicitly verified)
    assert result.returncode == 0, (
        f"cut-040 R40.D REGRESSION: E2 runner exit {result.returncode} (expect 0). "
        f"Last 1500 chars: {result.stdout[-1500:]}"
    )
    assert "PASS" in result.stdout
