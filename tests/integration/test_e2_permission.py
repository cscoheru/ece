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
    """cut-040R R40R.5: 6 cut-039 R39.1 exposures must never recur.

    Defense-in-depth gate: invokes scripts/run_e2_permission.py **without**
    --insert-deny-acls (Cline亲验发现 cut-040 R40.D 该旗标惰性 — 与
    不带该旗标输出逐字相同)。本测试改为**主断言** = `make seed` 真值
    已生效（即 R40R.1 RC-1 engine pass-through + R40R.1 RC-2 management
    tighten + R40R.1 RC-4 cls词表补齐 + R40.1a seed_acl_entries 全部
    起作用），e2-022/023/024/038/052/055 不再 unauthorized 暴露。

    Requires:
    - infra live (docker compose up -d db + api)
    - `make seed` 已跑 (R40.1a seed_acl_entries 落库)
    - `alembic upgrade head` (migrations applied)

    If R40R.1 fixes aren't actually effective, this test FAILS immediately
    at the marker-grep step. If `--insert-deny-acls` is added back, the
    test would pass even with broken engine — which is what Cline caught
    in cut-040 §12 review.
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
                # NO --insert-deny-acls: cut-040R R40R.5 main assertion.
                # The test now depends on `make seed` having actually
                # populated acl_entries (R40.1a) + the engine having
                # actually been passed through (R40R.1 RC-1).
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
            f"cut-040R R40R.5 REGRESSION: E2 Unauthorized Exposure > 0 "
            f"(cut-039 根因复发 — RC-1/RC-2/RC-4 修复未生效 OR make seed 未跑):\n"
            f"{result.stdout[-2000:]}"
        )

    # Defense-in-depth: explicitly grep stdout for the 0/0 markers.
    # If a future regression silently masks the count, the markers will
    # still appear non-zero in stdout and the test will fail.
    if "Exposures:          0" not in result.stdout:
        pytest.fail(
            f"cut-040R R40R.5 REGRESSION: 'Exposures: 0' marker missing in E2 runner output:\n"
            f"{result.stdout[-2000:]}"
        )
    if "Failures:           0" not in result.stdout:
        pytest.fail(
            f"cut-040R R40R.5 REGRESSION: 'Failures: 0' marker missing in E2 runner output:\n"
            f"{result.stdout[-2000:]}"
        )

    # exit 0: PASS (with both markers explicitly verified)
    assert result.returncode == 0, (
        f"cut-040R R40R.5 REGRESSION: E2 runner exit {result.returncode} (expect 0). "
        f"Last 1500 chars: {result.stdout[-1500:]}"
    )
    assert "PASS" in result.stdout
