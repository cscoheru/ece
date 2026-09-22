"""cut-045 — Nginx SPA reverse-proxy config binding tests.

Per `codex给cut-045的指令.md §4.2`:
  - SPA root → `demos/spa/`
  - `/api/` reverse-proxy → API upstream
  - `/healthz` reverse-proxy → API
  - gzip on
  - 安全头 (X-Frame-Options / X-Content-Type-Options / Referrer-Policy)
  - 不引外部 CDN
  - HTTPS 说明 + certbot 步骤注释

RED on cut-044R2 baseline: `deploy/nginx/corln.rana.asia.conf` missing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_NGINX_DIR = REPO_ROOT / "deploy" / "nginx"
NGINX_CONF_PATH = DEPLOY_NGINX_DIR / "corln.rana.asia.conf"


@pytest.fixture
def nginx_conf_text() -> str:
    if not NGINX_CONF_PATH.exists():
        pytest.fail(
            f"cut-045 deliverable missing: {NGINX_CONF_PATH} "
            f"(Codex directive §4.2 requires this nginx config for demo deployment)"
        )
    return NGINX_CONF_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Required directives — every assertion below corresponds to directive §4.2
# ---------------------------------------------------------------------------


def test_nginx_conf_exists() -> None:
    """deploy/nginx/corln.rana.asia.conf must exist."""
    assert NGINX_CONF_PATH.exists(), f"nginx config missing at {NGINX_CONF_PATH}"


def test_nginx_root_points_to_spa(nginx_conf_text: str) -> None:
    """nginx must serve SPA static files from demos/spa/."""
    assert "demos/spa" in nginx_conf_text, (
        "nginx config must reference demos/spa/ as SPA root (directive §4.2.1)"
    )
    # Common root directive patterns
    assert "root " in nginx_conf_text, "nginx config missing root directive"


def test_nginx_proxies_api_path(nginx_conf_text: str) -> None:
    """`/api/` location must reverse-proxy to FastAPI upstream."""
    assert "/api/" in nginx_conf_text, (
        "nginx must declare a /api/ location block (directive §4.2.2)"
    )
    # Proxy directive is required
    assert "proxy_pass" in nginx_conf_text, (
        "nginx /api/ location must use proxy_pass to upstream"
    )


def test_nginx_proxies_healthz(nginx_conf_text: str) -> None:
    """`/healthz` location must reverse-proxy to API."""
    assert "/healthz" in nginx_conf_text, (
        "nginx must declare /healthz reverse-proxy (directive §4.2.3)"
    )


def test_nginx_gzip_enabled(nginx_conf_text: str) -> None:
    """gzip on must be configured (directive §4.2.4)."""
    # Case-insensitive; nginx allows gzip on; in any whitespace
    assert "gzip on" in nginx_conf_text.lower() or "gzip  on" in nginx_conf_text.lower(), (
        "nginx must enable gzip (directive §4.2.4)"
    )


def test_nginx_security_headers(nginx_conf_text: str) -> None:
    """Security headers must be set (directive §4.2.5).

    Required: X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
    """
    required_headers = ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy")
    for header in required_headers:
        assert header in nginx_conf_text, (
            f"nginx must set security header {header!r} (directive §4.2.5)"
        )


def test_nginx_no_external_cdn(nginx_conf_text: str) -> None:
    """No external CDN proxy_pass targets (directive §4.2.6).

    An `upstream` block reference (e.g. `proxy_pass http://ece_api_upstream;`)
    is ALLOWED — only literal URLs to non-localhost hosts are blocked.
    Distinguish by presence of `.` (FQDN) or `:port` (real URL).
    """
    import re

    matches = re.findall(
        r"proxy_pass\s+https?://([a-zA-Z0-9_.-]+(?::\d+)?(?:/[^\s;]+)?)",
        nginx_conf_text,
    )
    for host_port in matches:
        # Strip port if present
        host = host_port.split(":")[0]
        # Strip path if present (e.g. "host/api/")
        host = host.split("/")[0]
        # Skip upstream-name references (no dot, no colon-port) — those are
        # nginx upstream block names like `ece_api_upstream`.
        if "." not in host and ":" not in host_port:
            continue
        # Allow loopback / localhost
        assert host in ("localhost", "127.0.0.1"), (
            f"nginx proxy_pass targets external host {host!r} — "
            f"no external CDN allowed (directive §4.2.6). Allowed: localhost, 127.0.0.1"
        )
    # Also assert no https:// proxy_pass to anything other than localhost
    https_matches = re.findall(r"proxy_pass\s+https://([^/\s;]+)", nginx_conf_text)
    for host in https_matches:
        assert host in ("localhost", "127.0.0.1"), (
            f"nginx proxy_pass https:// targets external host {host!r}"
        )


def test_nginx_has_https_or_certbot_notes(nginx_conf_text: str) -> None:
    """Config must reference HTTPS and/or certbot for TLS setup (directive §4.2.7)."""
    lower = nginx_conf_text.lower()
    assert "https" in lower or "certbot" in lower or "ssl" in lower, (
        "nginx config must reference HTTPS / certbot / ssl for TLS setup"
    )