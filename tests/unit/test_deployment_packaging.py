"""cut-045R3 — Deployment packaging binding tests (R13-B1 fix).

Codex R2 HOLD verdict R13-B1: ece/Dockerfile only copied `pyproject.toml`,
`uv.lock`, and `src/`. The Phase 6 in-container commands would fail:

  - `alembic upgrade head`  — no `alembic.ini` in /app
  - `python scripts/seed_v0_spike_fixture.py`    — scripts/ not in image
  - `python scripts/seed_knowledge_fixture.py`   — scripts/ not in image
  - `python scripts/seed_compliance_fixture.py`  — scripts/ not in image

This file guards the packaging invariants so a Dockerfile regression
cannot silently re-introduce the Phase 6 deployment defect.

  - Dockerfile COPY statements cover the required paths
  - alembic.ini exists at the path the checklist uses (or at /app)
  - All three seed scripts exist at scripts/
  - docker-compose.demo.yml does NOT mount scripts/ as a volume
    (scripts/ must be baked into the image, not bind-mounted, so the
    founder's deploy can't accidentally rely on a host path that
    won't exist on a fresh clone)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"
COMPOSE_PATH = REPO_ROOT / "deploy" / "docker-compose.demo.yml"
SCRIPTS_DIR = REPO_ROOT / "scripts"
ALEMBIC_INI_CANONICAL = REPO_ROOT / "src" / "ece" / "migrations" / "alembic.ini"

REQUIRED_SEED_SCRIPTS = (
    "seed_v0_spike_fixture.py",
    "seed_knowledge_fixture.py",
    "seed_compliance_fixture.py",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    if not DOCKERFILE_PATH.exists():
        pytest.fail(f"Dockerfile missing at {DOCKERFILE_PATH}")
    return DOCKERFILE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text() -> str:
    if not COMPOSE_PATH.exists():
        pytest.fail(f"docker-compose.demo.yml missing at {COMPOSE_PATH}")
    return COMPOSE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Dockerfile COPY coverage — scripts/ + alembic config must be baked in
# ---------------------------------------------------------------------------


def test_dockerfile_copies_scripts_directory(dockerfile_text: str) -> None:
    """Dockerfile must `COPY scripts/ ./scripts/` so Phase 6 seed commands work.

    R13-B1: without this, `python scripts/seed_*_fixture.py` inside the
    container fails with `No such file or directory: 'scripts/seed_*.py'`.
    """
    # Accept either "COPY scripts/ ./scripts/" or "COPY scripts ./scripts" etc.
    pattern = re.compile(
        r"^\s*COPY\s+scripts/\s+\./scripts/?\s*$", re.MULTILINE
    )
    assert pattern.search(dockerfile_text), (
        "Dockerfile must include `COPY scripts/ ./scripts/` so Phase 6 "
        "in-container seed commands work. R13-B1 fix: previous Dockerfile "
        "only copied pyproject.toml + uv.lock + src/, leaving scripts/ "
        "absent from the image."
    )


def test_dockerfile_copies_alembic_ini_to_app_root(dockerfile_text: str) -> None:
    """Dockerfile must expose alembic.ini at WORKDIR (/app) so `alembic upgrade head` works.

    R13-B1: alembic reads alembic.ini from cwd by default. The canonical
    config lives at src/ece/migrations/alembic.ini; the Dockerfile must
    copy it to /app/alembic.ini (or symlink, but COPY is simpler). Without
    this, `alembic upgrade head` exits with "Can't locate config file".

    Accepted forms (any of these):
      - COPY src/ece/migrations/alembic.ini ./alembic.ini
      - COPY src/ece/migrations/alembic.ini /app/alembic.ini
      - COPY alembic.ini ./alembic.ini   (if a flat alembic.ini also exists)
    """
    # Look for COPY ... alembic.ini
    pattern = re.compile(
        r"^\s*COPY\s+(?:src/ece/migrations/)?alembic\.ini\s+(?:\./alembic\.ini|/app/alembic\.ini)\s*$",
        re.MULTILINE,
    )
    assert pattern.search(dockerfile_text), (
        "Dockerfile must copy alembic.ini to the WORKDIR root (/app/alembic.ini). "
        "R13-B1 fix: alembic reads alembic.ini from cwd by default; the "
        "canonical config at src/ece/migrations/alembic.ini is invisible "
        "to `alembic upgrade head` unless copied to /app. Accepted forms: "
        "`COPY src/ece/migrations/alembic.ini ./alembic.ini` or "
        "`COPY src/ece/migrations/alembic.ini /app/alembic.ini`."
    )


def test_dockerfile_still_copies_src(dockerfile_text: str) -> None:
    """Sanity: Dockerfile must still COPY src/ (so ece package is importable).

    R13-B1: do NOT regress this. PYTHONPATH=/app/src relies on src/ being
    present so `from ece.X import Y` works for migrations + seed scripts.
    """
    assert re.search(r"^\s*COPY\s+src/\s+\./src/?\s*$", dockerfile_text, re.MULTILINE), (
        "Dockerfile must still COPY src/ — the ece package source. "
        "R13-B1 fix added COPY scripts/ + COPY alembic.ini, but src/ is "
        "still required for migrations + seed scripts to import ece.*"
    )


# ---------------------------------------------------------------------------
# Seed scripts exist at canonical paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script_name", REQUIRED_SEED_SCRIPTS)
def test_seed_script_exists(script_name: str) -> None:
    """All three seed scripts must exist at scripts/ (R13-B1 Phase 6 commands).

    The checklist Phase 6 + reset-demo-fixtures.sh call these by name.
    """
    script_path = SCRIPTS_DIR / script_name
    assert script_path.exists(), (
        f"Required seed script missing: {script_path}. "
        "R13-B1 fix requires scripts/{v0_spike,knowledge,compliance}_fixture.py "
        "to exist (Phase 6 in-container seed commands)."
    )


# ---------------------------------------------------------------------------
# Canonical alembic config exists at expected path
# ---------------------------------------------------------------------------


def test_alembic_ini_canonical_path_exists() -> None:
    """src/ece/migrations/alembic.ini must exist (Dockerfile COPY source).

    The Dockerfile copies this file to /app/alembic.ini in the image.
    If the source path changes, the Dockerfile's COPY line must update too.
    """
    assert ALEMBIC_INI_CANONICAL.exists(), (
        f"Canonical alembic config missing at {ALEMBIC_INI_CANONICAL}. "
        "R13-B1 fix requires this file (Dockerfile copies it to /app/alembic.ini)."
    )


def test_alembic_ini_script_location_points_to_existing_dir() -> None:
    """The migrations directory referenced by alembic.ini must exist in the repo.

    Sanity: if someone moves src/ece/migrations, alembic upgrade head will
    fail at runtime. This binding test catches it at unit-test time.

    Resolution semantics: alembic resolves `script_location` relative to
    the alembic.ini file's directory. In the deployed image, alembic.ini
    lives at /app/alembic.ini (per Dockerfile COPY), so script_location=
    `src/ece/migrations` resolves to /app/src/ece/migrations. Since
    `COPY src/ ./src/` mirrors the repo's src/ tree 1:1, the deployed path
    exists iff <repo>/src/ece/migrations exists.

    This test verifies the repo-side precondition that makes the deployed
    resolution valid.
    """
    text = ALEMBIC_INI_CANONICAL.read_text(encoding="utf-8")
    m = re.search(r"^script_location\s*=\s*(.+?)\s*$", text, re.MULTILINE)
    assert m, "alembic.ini missing script_location"
    script_location = m.group(1).strip()
    # After Dockerfile COPY src/ ./src/, the deployed /app/src/ tree mirrors
    # <repo>/src/. So <repo>/src/<script_location_tail> must exist.
    # script_location is relative to /app in the image, but relative to
    # /app/src/ (i.e. the same as <repo>/src/) in our 1:1 mirror.
    # Specifically: script_location="src/ece/migrations" means /app/src/ece/migrations
    # in the image, which corresponds to <repo>/src/ece/migrations on the host.
    # Strip a leading "src/" if present so we resolve against <repo>/src/.
    tail = script_location
    if tail.startswith("src/"):
        tail = tail[len("src/"):]
    repo_src = REPO_ROOT / "src"
    resolved = (repo_src / tail).resolve()
    assert resolved.is_dir(), (
        f"alembic.ini script_location={script_location!r} implies the "
        f"deployed path /app/{script_location} which mirrors <repo>/{resolved.relative_to(REPO_ROOT)}. "
        f"That directory does not exist on the host. R13-B1 fix requires "
        f"src/ece/migrations/ to be present alongside alembic.ini. "
        f"Current repo src/ layout: "
        f"{sorted(p.name for p in (REPO_ROOT / 'src').iterdir()) if (REPO_ROOT / 'src').exists() else 'MISSING'}"
    )


# ---------------------------------------------------------------------------
# docker-compose.demo.yml — scripts/ must NOT be bind-mounted
# ---------------------------------------------------------------------------


def test_compose_does_not_bind_mount_scripts(compose_text: str) -> None:
    """scripts/ must NOT be in compose volumes (must be baked into image).

    R13-B1: if scripts/ were a bind-mount from the host, the founder's
    fresh clone + fresh server would have no host path to mount, breaking
    Phase 6. The Dockerfile fix (COPY scripts/) is the durable answer.
    """
    # Look for ../scripts or ./scripts or /path/to/scripts in api service volumes
    # We accept other mounts (../demos/spa, ../data) — only scripts/ is forbidden.
    pattern = re.compile(
        r"(?:^|\s)(?:\.{2}/scripts|\./scripts|scripts/)(?::|\s|$)",
        re.MULTILINE,
    )
    assert not pattern.search(compose_text), (
        "deploy/docker-compose.demo.yml must NOT bind-mount scripts/. "
        "R13-B1 fix: scripts/ must be baked into the image via Dockerfile "
        "COPY so a fresh clone + fresh server can run Phase 6 without "
        "relying on a host path that doesn't exist."
    )


# ---------------------------------------------------------------------------
# Phase 6 commands — verify the exact strings exist in the reset script
# ---------------------------------------------------------------------------


def test_reset_script_invokes_four_phase6_commands() -> None:
    """deploy/scripts/reset-demo-fixtures.sh must invoke all 4 Phase 6 commands.

    These are the commands the founder runs in-container. If any are
    renamed/moved, the checklist becomes a lie.
    """
    reset_script = REPO_ROOT / "deploy" / "scripts" / "reset-demo-fixtures.sh"
    assert reset_script.exists(), f"reset script missing at {reset_script}"
    text = reset_script.read_text(encoding="utf-8")
    required = (
        "alembic upgrade head",
        "seed_v0_spike_fixture.py",
        "seed_knowledge_fixture.py",
        "seed_compliance_fixture.py",
    )
    missing = [r for r in required if r not in text]
    assert not missing, (
        f"reset-demo-fixtures.sh missing required Phase 6 command tokens: {missing}. "
        "R13-B1 fix: these are the 4 in-container commands that depend on the "
        "Dockerfile packaging (scripts/ + alembic.ini)."
    )
