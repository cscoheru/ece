"""cut-045R1 R3-B4 — PRD/report/View C consistency binding tests.

Codex R3-B4 finding (cut-045 R1 HOLD): PRD §8 cut-045 row still claimed
"私有化一键包" while the actual delivery was "Demo Deployment Profile (自有服务器演示)".
This test guards the PRD + report from regressing back to the lying claim.

It also verifies:
  - PRD §8 cut-045 row mentions "Demo Deployment Profile" OR "自有演示服务器部署包"
    (NOT 私有化一键包)
  - PRD §11 has a cut-045 trail row
  - reports/cut-045-report.md has the cut-045R1 R3-B4 fix notes
  - reports/cut-045-report.md View C section reflects "config-as-code ✅ / real 🔨"
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT.parent / "docs" / "demo-platform"
PRD_PATH = DOCS_DIR / "DEMO_PLATFORM_PRD.md"
REPORT_PATH = REPO_ROOT / "reports" / "cut-045-report.md"


@pytest.fixture(scope="module")
def prd_text() -> str:
    if not PRD_PATH.exists():
        pytest.fail(f"PRD missing at {PRD_PATH}")
    return PRD_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def report_text() -> str:
    if not REPORT_PATH.exists():
        pytest.fail(f"cut-045 report missing at {REPORT_PATH}")
    return REPORT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# PRD §8 cut-045 row — must say Demo Deployment Profile, NOT 私有化一键包
# ---------------------------------------------------------------------------


def test_prd_cut_045_row_mentions_demo_deployment_profile(prd_text: str) -> None:
    """PRD §8 cut-045 row must mention 'Demo Deployment Profile' or '自有演示服务器部署包'.

    Codex R3-B4: the cut-045 row previously claimed '私有化一键包' while
    the actual delivery was 'Demo Deployment Profile (自有服务器演示)'.
    This binding test guards against regression.
    """
    # Find the cut-045 row by splitting on table rows. The §8 row starts
    # with "| **cut-045** |" and ends at the next newline.
    row_match = re.search(
        r"^\|\s*\*\*cut-045\*\*\s*\|[^\n]*",
        prd_text,
        re.MULTILINE,
    )
    assert row_match, "PRD §8 cut-045 row missing entirely"
    row = row_match.group(0)
    assert "私有化一键包" not in row, (
        "PRD §8 cut-045 row still claims '私有化一键包' — but actual delivery "
        "is Demo Deployment Profile (自有服务器演示). Codex R3-B4 fix requires "
        "this to be corrected."
    )
    assert (
        "Demo Deployment Profile" in row
        or "自有演示服务器部署包" in row
        or "自有服务器部署" in row
    ), (
        "PRD §8 cut-045 row must mention 'Demo Deployment Profile' or "
        "'自有演示服务器部署包' (per cut-045R1 R3-B4 fix)"
    )


def test_prd_has_cut_045_trail_row_in_section_11(prd_text: str) -> None:
    """PRD §11 must have a trail row for cut-045 (or cut-045R1).

    Codex R3-B4: §11 had no cut-045 row before cut-045R1.
    """
    # Trail rows in §11 follow the pattern: | YYYY-MM-DD | **cut-XXX** | ...
    trail_row_pattern = re.compile(r"\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*\*\*cut-045", re.IGNORECASE)
    assert trail_row_pattern.search(prd_text), (
        "PRD §11 missing cut-045 trail row — R3-B4 fix requires a trail row "
        "documenting cut-045 / cut-045R1 closure. Pattern: | YYYY-MM-DD | **cut-045** | ..."
    )


def test_prd_section_3_mentions_loopback_bind(prd_text: str) -> None:
    """PRD §3 硬约束 must mention loopback bind + reset/seed runbook.

    Codex R3-B1 + R3-B2 fixes added `127.0.0.1:8000:8000` loopback bind and
    `docker compose run --rm api` for alembic/seed. PRD §3 硬约束 must
    reflect these to prevent regression.
    """
    # §3 mentions loopback + reset/seed
    section_3_match = re.search(
        r"## 3\..*?(?=\n## )", prd_text, re.DOTALL
    )
    assert section_3_match, "PRD §3 missing entirely"
    section_3 = section_3_match.group(0)
    assert "127.0.0.1:8000" in section_3 or "loopback" in section_3.lower(), (
        "PRD §3 硬约束 must mention `127.0.0.1:8000` loopback bind "
        "(cut-045R1 R3-B1 fix)"
    )
    assert (
        "docker compose run --rm api" in section_3
        or "docker compose run --rm" in section_3
    ), (
        "PRD §3 硬约束 must mention `docker compose run --rm api` for "
        "alembic/seed (cut-045R1 R3-B2 fix)"
    )


# ---------------------------------------------------------------------------
# cut-045-report.md — View C deployment status
# ---------------------------------------------------------------------------


def test_report_view_c_section_distinguishes_real_deployment(report_text: str) -> None:
    """cut-045-report.md View C section must distinguish config-as-code vs real deployment.

    Codex R3-B4: cut-045 report wrongly marked 'Same-origin Deployment ✅'
    but only config-as-code was shipped. The report must now distinguish:
      - config-as-code: ✅
      - real deployment: 🔨
    """
    assert "config-as-code" in report_text, (
        "cut-045-report.md must explicitly mention 'config-as-code' status "
        "(R3-B4 fix — distinguishes config-as-code ✅ from real deployment 🔨)"
    )
    assert "real deployment" in report_text.lower() or "真实部署" in report_text, (
        "cut-045-report.md must explicitly mention real deployment status "
        "(R3-B4 fix — distinguishes config-as-code ✅ from real deployment 🔨)"
    )


def test_report_acknowledges_r1_hold_and_r1_fix(report_text: str) -> None:
    """cut-045-report.md must acknowledge Codex R1 HOLD + R3-B1..R3-B4 fix.

    Codex R3-B4: cut-045 report self-declared PASS without acknowledging
    the Codex R1 HOLD verdict. The report must now:
      - Acknowledge Codex R1 HOLD
      - List R3-B1..R3-B4 as the 4 blockers
      - Document what was actually fixed in cut-045R1
    """
    assert "HOLD" in report_text, (
        "cut-045-report.md must acknowledge Codex R1 HOLD (R3-B4 fix)"
    )
    for blocker in ("R3-B1", "R3-B2", "R3-B3", "R3-B4"):
        assert blocker in report_text, (
            f"cut-045-report.md must mention {blocker} (R3-B4 fix)"
        )


def test_report_mutation_command_uses_dedicated_runners(report_text: str) -> None:
    """cut-045-report.md §5 must list the actual mutation commands (3 runners).

    Codex R3-B4: cut-045 report cited `mutmut run --tests-dir ...` which is
    NOT the actual command set used. The repo uses 3 dedicated Python runners.
    The R3-B4 fix note itself mentions "mutmut run --tests-dir" only in
    describing what was WRONG — that's allowed. The actual command column
    must list the dedicated runners.
    """
    # Find the §5 mutation table — extract just that section
    section_5_match = re.search(
        r"## 5\..*?(?=\n## )", report_text, re.DOTALL
    )
    assert section_5_match, "PRD-style §5 mutation section missing entirely"
    section_5 = section_5_match.group(0)
    # The §5 mutation table must NOT use `mutmut run --tests-dir` as the actual command
    assert "mutmut run --tests-dir" not in section_5, (
        "cut-045-report.md §5 mutation table still cites `mutmut run --tests-dir` "
        "as the actual command. Per R3-B4 fix: the repo uses 3 dedicated Python "
        "mutation runners (`cut_042r3_mutation_runner.py` etc.), not the generic "
        "mutmut CLI. The R3-B4 fix note can describe what was wrong, but the "
        "actual command column must list the dedicated runners."
    )
    for runner in (
        "cut_042r3_mutation_runner.py",
        "cut_043_mutation_runner.py",
        "cut_044_mutation_runner.py",
    ):
        assert runner in section_5, (
            f"cut-045-report.md §5 must reference {runner} (R3-B4 fix)"
        )


def test_report_includes_local_origin_pass_10_evidence(report_text: str) -> None:
    """cut-045-report.md §6.4 must include the cut-045R1 local-origin PASS=10.

    Codex R3-B4: cut-045 report only listed PASS=8 SKIP=2 (API-only uvicorn).
    The cut-045R1 run against the local-origin reverse-proxy achieves
    PASS=10 SKIP=0 FAIL=0. This must be documented as the truth.
    """
    # The §6.4 R3-B3 fix section should show PASS=10 SKIP=0 FAIL=0
    assert "PASS=10 SKIP=0 FAIL=0" in report_text, (
        "cut-045-report.md §6.4 must show PASS=10 SKIP=0 FAIL=0 against "
        "the local-origin reverse-proxy (cut-045R1 R3-B3 fix)"
    )