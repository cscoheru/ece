"""cut-045R2 — SERVER_DEPLOYMENT_CHECKLIST.md binding tests.

Codex R3-B3 expansion: cut-045R1 closed the 4 R3-B1..R3-B4 engineering
fixes, but the cut-045R1 prompt also requires a 12-phase deployment
companion for the founder to actually execute the deployment on a real
server. This file guards that checklist:

  - File exists at the canonical path
  - All 12 phases (Phase 0..Phase 12) are present and labeled
  - Each phase has a Goal, Commands, Expected output, Common errors,
    and STOP gate (the strict 12-phase structure per Codex directive)
  - Key commands from deploy/* files appear (cross-reference integrity)
  - Security discipline: secrets must NEVER be pasted (no real password
    examples that look like real credentials)
  - Phase 9 completion gate: `PASS=10 SKIP=0 FAIL=0` against
    `https://corln.rana.asia`
  - State model discipline: NO CUT-046 — only `cut-045R*` rework cycles

If this file regresses, the founder-facing deployment story regresses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"
CHECKLIST_PATH = DEPLOY_DIR / "SERVER_DEPLOYMENT_CHECKLIST.md"


@pytest.fixture(scope="module")
def checklist_text() -> str:
    if not CHECKLIST_PATH.exists():
        pytest.fail(
            f"SERVER_DEPLOYMENT_CHECKLIST.md missing at {CHECKLIST_PATH}. "
            "Per cut-045R2 Codex directive §1.R3-B3: the 12-phase deployment "
            "checklist is the founder-facing deploy companion."
        )
    return CHECKLIST_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File existence + 12-phase structure (Codex directive §1.R3-B3)
# ---------------------------------------------------------------------------


REQUIRED_PHASES = tuple(f"Phase {i}" for i in range(13))  # Phase 0..Phase 12


def test_checklist_lists_all_12_phases_oh(checklist_text: str) -> None:
    """All 12 phases (Phase 0..Phase 12) must be present and labeled.

    Codex directive §1.R3-B3 mandates a strict 12-phase structure:
    Phase 0 Preflight, 1 DNS, 2 Server prep, 3 Clone repo, 4 Environment,
    5 Start API+Postgres, 6 Migration+Seed, 7 Nginx, 8 HTTPS,
    9 Real URL smoke (completion gate), 10 Manual validation,
    11 Demo reset, 12 Rollback/troubleshooting.
    """
    missing = [p for p in REQUIRED_PHASES if p not in checklist_text]
    assert not missing, (
        f"SERVER_DEPLOYMENT_CHECKLIST.md missing phases: {missing}. "
        f"Per Codex directive §1.R3-B3, all 12 phases must be labeled. "
        f"Found: {[p for p in REQUIRED_PHASES if p in checklist_text]}"
    )


# ---------------------------------------------------------------------------
# Per-phase structure — Goal / Commands / Expected / Errors / STOP gate
# ---------------------------------------------------------------------------


# Required section headers inside each phase (Codex directive §1.R3-B3 template).
# Phases use **bold** labels in the checklist markdown (not ## subheaders).
REQUIRED_PHASE_SECTIONS = (
    "**Goal**",
    "**Commands**",
    "**Expected output**",
    "**Common errors**",
)


def test_each_phase_has_required_sections(checklist_text: str) -> None:
    """Each deployable phase (0..11) must contain Goal + Commands + Expected output + Common errors.

    Codex directive §1.R3-B3 template mandates these four sub-sections
    in every phase so the founder has a deterministic deploy script.

    Note: Phase 0..Phase 11 are deploy phases (12 phases). Phase 12 is
    reference-only (troubleshooting scenarios, organized by 12.1..12.10
    subsections) and is exempt from this strict structure.

    Note: Phase 0..Phase 12 = 13 phases total (per Codex directive), so
    split-on-phase-delimiter yields 14 chunks (1 preamble + 13 phases).
    """
    # Split into per-phase chunks by Phase N marker.
    phase_pattern = re.compile(
        r"(?=^## Phase \d+ — )", re.MULTILINE
    )
    chunks = phase_pattern.split(checklist_text)
    # chunks[0] is preamble; chunks[1..13] are the 13 phases (Phase 0..12).
    assert len(chunks) == 14, (
        f"Expected 13 phase chunks + 1 preamble = 14 total, got {len(chunks)}. "
        "Phase delimiter `## Phase N — ...` may have drifted."
    )
    failures: list[str] = []
    for idx, chunk in enumerate(chunks[1:], start=0):
        phase_num = idx  # Phase 0..Phase 12
        phase_name = f"Phase {phase_num}"
        # Phase 12 is reference-only (troubleshooting) — exempt from strict structure.
        if phase_num == 12:
            continue
        missing: list[str] = []
        for section in REQUIRED_PHASE_SECTIONS:
            # Accept "**Expected output**" OR "**Expected output (xxx)**" forms.
            # The parenthetical variant is allowed for emphasis on completion gates
            # (Phase 9 uses "**Expected output (mandatory for cut-045R2 closure)**:"
            # to mark the completion gate explicitly).
            section_prefix = section.rstrip("*")  # "**Expected output**" → "**Expected output"
            if section_prefix not in chunk:
                missing.append(section)
        if missing:
            failures.append(f"{phase_name} missing: {missing}")
    assert not failures, (
        "SERVER_DEPLOYMENT_CHECKLIST.md phases missing required sub-sections. "
        "Per Codex §1.R3-B3 template each phase must contain "
        "Goal / Commands / Expected output / Common errors.\n"
        + "\n".join(failures)
    )


def test_each_phase_has_stop_gate(checklist_text: str) -> None:
    """Each phase must have a STOP gate that requires the founder to paste output.

    Codex §1.R3-B3 mandates a STOP gate per phase so Claude/Codex can verify
    real progress instead of trusting self-reporting. STOP gates are
    marked by the 🛑 emoji + the literal phrase "STOP gate".

    Note: Phase 0..Phase 12 = 13 phases, so split yields 14 chunks.
    """
    phase_pattern = re.compile(r"(?=^## Phase \d+ — )", re.MULTILINE)
    chunks = phase_pattern.split(checklist_text)
    assert len(chunks) == 14, "Phase delimiter drift (expected 14 chunks)"
    failures: list[str] = []
    for idx, chunk in enumerate(chunks[1:], start=0):
        phase_name = f"Phase {idx}"
        # Phase 12 is reference-only (no STOP gate per Codex directive).
        if idx == 12:
            continue
        if "🛑 STOP gate" not in chunk and "STOP gate" not in chunk:
            failures.append(phase_name)
    assert not failures, (
        "Phases missing STOP gate (require founder to paste output for "
        "verification before proceeding):\n" + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Key commands from deploy/* files must appear (cross-reference integrity)
# ---------------------------------------------------------------------------


REQUIRED_KEY_COMMANDS = (
    # Phase 1 — DNS check
    ("dig +short corln.rana.asia", "Phase 1"),
    # Phase 5 — Start API + Postgres
    ("docker compose -f deploy/docker-compose.demo.yml", "Phase 5"),
    # Phase 5 — pgvector image (R3-B2 fix)
    ("pgvector/pgvector:pg16", "Phase 5"),
    # Phase 6 — alembic in-container (R3-B2 fix — either `exec -T` or `run --rm` form)
    ("alembic upgrade head", "Phase 6"),
    ("exec -T api", "Phase 6"),
    # Phase 7 — nginx
    ("nginx -t", "Phase 7"),
    ("systemctl reload nginx", "Phase 7"),
    # Phase 8 — certbot
    ("certbot --nginx -d corln.rana.asia", "Phase 8"),
    # Phase 9 — Real URL smoke (completion gate)
    ("cut_045_demo_deployment_smoke.py", "Phase 9"),
    # Phase 11 — Reset script
    ("reset-demo-fixtures.sh", "Phase 11"),
)


def test_checklist_references_canonical_commands(checklist_text: str) -> None:
    """The checklist must reference the actual deploy/* file commands verbatim.

    Cross-reference integrity: if `deploy/docker-compose.demo.yml` changes
    its filename, this test fails — forcing a checklist update.
    """
    failures: list[str] = []
    for cmd, expected_phase in REQUIRED_KEY_COMMANDS:
        if cmd not in checklist_text:
            failures.append(f"{cmd} (expected in {expected_phase})")
    assert not failures, (
        "SERVER_DEPLOYMENT_CHECKLIST.md missing canonical commands:\n"
        + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Phase 9 — completion gate
# ---------------------------------------------------------------------------


def test_phase_9_completion_gate_mandates_pass_10(checklist_text: str) -> None:
    """Phase 9 (Real URL smoke) must show `PASS=10 SKIP=0 FAIL=0` as the gate.

    Codex directive §5 completion definition: cut-045R2 cannot close unless
    real `https://corln.rana.asia` smoke achieves `PASS=10 SKIP=0 FAIL=0`.
    The checklist Phase 9 must reflect this as the mandatory completion gate.
    """
    # Locate Phase 9 chunk
    phase9_match = re.search(
        r"## Phase 9 — .*?(?=\n## Phase 1[0-9])",
        checklist_text,
        re.DOTALL,
    )
    assert phase9_match, "Phase 9 section missing"
    phase9 = phase9_match.group(0)
    assert "PASS=10 SKIP=0 FAIL=0" in phase9, (
        "Phase 9 must show `PASS=10 SKIP=0 FAIL=0` as the cut-045R2 "
        "completion gate (Codex directive §5)"
    )
    assert "https://corln.rana.asia" in phase9, (
        "Phase 9 must reference the real `https://corln.rana.asia` URL "
        "(NOT a localhost placeholder — Codex directive §5 mandates a "
        "real-URL smoke for cut-045R2 closure)"
    )
    # Phase 9 must explicitly say the gate is MANDATORY
    assert "MANDATORY" in phase9 or "mandatory" in phase9.lower(), (
        "Phase 9 must mark the smoke gate as MANDATORY (Codex §5)"
    )


# ---------------------------------------------------------------------------
# Security discipline — secrets must NEVER appear
# ---------------------------------------------------------------------------


def test_checklist_has_no_pasted_secrets(checklist_text: str) -> None:
    """No real-looking passwords / API keys / private keys may appear.

    The checklist is committed to the public repo. Even examples that
    LOOK like real credentials are forbidden. Only:
      - `CHANGE_ME_LOCAL_ONLY` (deliberate placeholder)
      - `<placeholder>` strings
      - `openssl rand` invocations (the OUTPUT is the secret; not pasted)
    may appear.
    """
    forbidden_patterns = [
        # Looks like AWS / GCP / GitHub tokens
        (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
        (r"\bghp_[A-Za-z0-9]{36}\b", "GitHub personal access token"),
        (r"\bsk-[A-Za-z0-9]{20,}\b", "OpenAI-style secret key"),
        (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "Slack token"),
        # Looks like a real-looking password (≥16 chars, mix of classes)
        # We're permissive: only flag if it's in a `<key>=value` context
        # and the value is suspiciously long + mixed case + digits
        (
            r"(?i)(?:password|passwd|pwd|secret|token|api_key)\s*[=:]\s*"
            r"['\"]?[A-Za-z0-9!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]{16,}['\"]?",
            "real-looking password / secret / token",
        ),
    ]
    failures: list[str] = []
    for pattern, label in forbidden_patterns:
        for m in re.finditer(pattern, checklist_text):
            failures.append(f"{label}: {m.group(0)!r}")
    assert not failures, (
        "SERVER_DEPLOYMENT_CHECKLIST.md must NOT contain real-looking secrets:\n"
        + "\n".join(failures)
    )


def test_checklist_explicitly_warns_about_secret_discipline(
    checklist_text: str,
) -> None:
    """The checklist must include an explicit secrets warning near the top.

    Codex directive §1 Phase 0 mandates that the founder be told NEVER to
    commit / paste / log secrets. The warning text appears in the preamble.
    """
    # Find preamble (everything before the first Phase header)
    preamble_end = checklist_text.find("## Phase 0")
    preamble = checklist_text[:preamble_end] if preamble_end > 0 else checklist_text
    # Required warning phrases
    required_phrases = (
        "NEVER",
        "deploy/.env",  # mentions the secret env file
        "git",  # warns against committing it
    )
    missing = [p for p in required_phrases if p not in preamble]
    assert not missing, (
        f"SERVER_DEPLOYMENT_CHECKLIST.md preamble missing secrets "
        f"discipline warning phrases: {missing}. Codex §1 Phase 0 mandates "
        "an explicit warning that the founder must NOT paste / commit secrets."
    )


# ---------------------------------------------------------------------------
# State model discipline — NO CUT-046
# ---------------------------------------------------------------------------


def test_checklist_acknowledges_no_cut_046(checklist_text: str) -> None:
    """The checklist must explicitly state NO CUT-046 (terminal cut-045).

    Codex directive §0: cut-045 is the terminal cut. Only `cut-045R*`
    rework cycles are allowed. The checklist must surface this discipline
    so the founder / future maintainers see it.
    """
    # Required state model phrases
    required_phrases = (
        "cut-045",
        "NO CUT-046",
        "cut-045R*",
    )
    missing = [p for p in required_phrases if p not in checklist_text]
    assert not missing, (
        f"SERVER_DEPLOYMENT_CHECKLIST.md missing state model discipline "
        f"phrases: {missing}. Per Codex §0: `cut-045` is the terminal cut; "
        "there is NO cut-046. Only `cut-045R*` rework cycles are allowed."
    )


# ---------------------------------------------------------------------------
# Cross-reference to deploy/* files
# ---------------------------------------------------------------------------


def test_checklist_references_deploy_readme(checklist_text: str) -> None:
    """The checklist must cross-reference deploy/README.md.

    The 11-section README is the narrative companion; the 12-phase
    CHECKLIST is the strict deploy script. They must reference each other.
    """
    assert "deploy/README.md" in checklist_text, (
        "SERVER_DEPLOYMENT_CHECKLIST.md must cross-reference deploy/README.md "
        "(CHECKLIST = strict 12-phase script; README = 11-section narrative "
        "companion — both must coexist)"
    )
