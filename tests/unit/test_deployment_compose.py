"""cut-045 — Demo deployment docker-compose config binding tests.

Per `plans/cut-045 §2.子刀 B`: Demo Deployment Profile ships
`deploy/docker-compose.demo.yml` + `deploy/.env.example`. This binding test
asserts the file is well-formed, includes api healthcheck, postgres service
does NOT expose 5432 to the public, and required env keys exist.

RED on cut-044R2 baseline: `deploy/` directory does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = REPO_ROOT / "deploy"
COMPOSE_PATH = DEPLOY_DIR / "docker-compose.demo.yml"
ENV_EXAMPLE_PATH = DEPLOY_DIR / ".env.example"

# Required env keys per `codex给cut-045的指令.md §4.1.3`
REQUIRED_ENV_KEYS = (
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "ECE_SERVER_TODAY_ANCHOR",
    "DEMO_DOMAIN",
)


def _load_yaml_or_skip(path: Path) -> dict:
    """Load YAML safely; return parsed dict.

    PyYAML is already a project dependency (used by api.py to read
    ScenarioSpec YAMLs).
    """
    import yaml

    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    assert isinstance(loaded, dict), f"{path} root must be a mapping"
    return loaded


# ---------------------------------------------------------------------------
# File presence — RED on cut-044R2 baseline (deploy/ missing)
# ---------------------------------------------------------------------------


def test_docker_compose_file_exists() -> None:
    """deploy/docker-compose.demo.yml must exist."""
    assert COMPOSE_PATH.exists(), (
        f"cut-045 deliverable missing: {COMPOSE_PATH}. "
        f"Per Codex directive §4.1, deploy/ is the demo deployment profile root."
    )


def test_env_example_file_exists() -> None:
    """deploy/.env.example must exist with all required keys documented."""
    assert ENV_EXAMPLE_PATH.exists(), (
        f"cut-045 deliverable missing: {ENV_EXAMPLE_PATH}."
    )


# ---------------------------------------------------------------------------
# Compose config shape — RED until deploy/docker-compose.demo.yml is shipped
# ---------------------------------------------------------------------------


def test_compose_has_two_services() -> None:
    """docker-compose.demo.yml must define api + postgres services."""
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    services = compose.get("services", {})
    assert "api" in services, f"missing 'api' service in compose: {list(services)}"
    assert "postgres" in services, f"missing 'postgres' service: {list(services)}"


def test_api_service_healthcheck_healthz() -> None:
    """API service must declare healthcheck against /healthz endpoint."""
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    api = compose["services"]["api"]
    healthcheck = api.get("healthcheck")
    assert healthcheck is not None, "api service missing healthcheck"
    test_cmd = healthcheck.get("test")
    # healthcheck.test may be a string or list
    test_str = " ".join(test_cmd) if isinstance(test_cmd, list) else str(test_cmd)
    assert "/healthz" in test_str, (
        f"api healthcheck must probe /healthz; got: {test_str!r}"
    )


def test_api_service_restart_unless_stopped() -> None:
    """API service must restart: unless-stopped (per directive §4.1.1)."""
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    api = compose["services"]["api"]
    restart = api.get("restart", "")
    assert restart == "unless-stopped", (
        f"api restart must be 'unless-stopped' (directive §4.1.1); got {restart!r}"
    )


def test_postgres_does_not_expose_5432_publicly() -> None:
    """Postgres service must NOT bind 5432 to 0.0.0.0 (security / directive §4.1.2).

    Either `ports:` is absent (postgres only on internal docker network)
    or `ports:` only binds 127.0.0.1:5432.
    """
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    postgres = compose["services"]["postgres"]
    ports = postgres.get("ports")
    if ports is None:
        return  # No public bind — only internal docker network
    # If `ports` is declared, ensure 5432 is not bound to 0.0.0.0
    for entry in ports:
        # entry may be a string like "5432:5432" or "127.0.0.1:55440:5432"
        if isinstance(entry, str):
            # Public bind formats: "5432:5432", "0.0.0.0:5432:5432", "<host_ip>:5432:5432" with non-loopback
            if ":" in entry:
                host_part = entry.split(":")[0]
                if host_part in ("0.0.0.0", "") or not host_part.startswith("127."):
                    # '5432:5432' has empty host_part
                    pytest.fail(
                        f"postgres port {entry!r} may be publicly accessible; "
                        f"bind to 127.0.0.1:<port>:5432 only or omit ports entirely."
                    )


def test_postgres_has_healthcheck() -> None:
    """Postgres must declare a healthcheck so API waits for DB readiness."""
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    postgres = compose["services"]["postgres"]
    healthcheck = postgres.get("healthcheck")
    assert healthcheck is not None, "postgres service missing healthcheck"


def test_postgres_volume_persists() -> None:
    """Postgres must persist data via volumes (directive §4.1.2)."""
    compose = _load_yaml_or_skip(COMPOSE_PATH)
    postgres = compose["services"]["postgres"]
    volumes = postgres.get("volumes", [])
    assert any("postgres" in str(v).lower() for v in volumes), (
        f"postgres must have a named volume for data persistence; got {volumes}"
    )


# ---------------------------------------------------------------------------
# Env example shape — RED until deploy/.env.example is shipped
# ---------------------------------------------------------------------------


def test_env_example_contains_all_required_keys() -> None:
    """All env keys in Codex directive §4.1.3 must appear in .env.example."""
    content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    for key in REQUIRED_ENV_KEYS:
        assert key in content, (
            f".env.example missing required key {key!r} (directive §4.1.3)."
        )


def test_env_example_has_no_hardcoded_secrets() -> None:
    """`.env.example` must NOT contain real passwords; only placeholders."""
    content = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    forbidden_substrings = ("CHANGE_ME_NOT_LITERAL", "password=password")
    for bad in forbidden_substrings:
        assert bad not in content, (
            f".env.example contains hardcoded secret pattern {bad!r}"
        )