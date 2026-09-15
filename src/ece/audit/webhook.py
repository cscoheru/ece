"""Audit log webhook streaming (cut-034 — v0.2 hardening).

Sends each context_request to a configured webhook URL for downstream
consumption (SIEM, compliance dashboard, monitoring). Fire-and-forget
(async via threading.Thread) to avoid blocking the request path.

Env:
    ECE_AUDIT_WEBHOOK_URL  # POST target URL (e.g. https://siem.example.com/ece)
    ECE_AUDIT_WEBHOOK_TIMEOUT  # optional, default 5 seconds

Behavior:
- When ECE_AUDIT_WEBHOOK_URL unset: no-op (back-compat)
- When set: after record_package commits to DB, fire POST to webhook
- Failures are logged but don't block the request

Security:
- Webhook URL must be HTTPS in production (warning logged if HTTP)
- No auth header by default (operator can configure reverse proxy for auth)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 5.0


def is_webhook_enabled() -> bool:
    """True if ECE_AUDIT_WEBHOOK_URL is configured."""
    return bool(os.environ.get("ECE_AUDIT_WEBHOOK_URL"))


def _send_sync(
    url: str, payload: dict[str, Any], timeout: float
) -> None:
    """Synchronous POST to webhook (runs in thread)."""
    if not _HTTPX_AVAILABLE:
        logger.warning("httpx not installed; webhook delivery disabled")
        return
    try:
        # Use httpx if available, else fall back to stdlib
        response = httpx.post(  # type: ignore[union-attr]
            url,
            json=payload,
            timeout=timeout,
        )
        if response.status_code >= 400:
            logger.warning(
                "Audit webhook returned %d for request_id=%s",
                response.status_code,
                payload.get("request_id", "unknown"),
            )
    except Exception as e:
        logger.warning(
            "Audit webhook delivery failed for request_id=%s: %s",
            payload.get("request_id", "unknown"),
            e,
        )


def send_audit_event(payload: dict[str, Any]) -> None:
    """Send audit event to webhook (fire-and-forget).

    Spawns a daemon thread to make the HTTP request. If the thread
    fails, the original request is not affected (request was already
    committed to DB by record_package).

    Args:
        payload: dict with audit event details (request_id, user_ref,
                 intent, status, counts, latency_ms, created_at, org_id)
    """
    url = os.environ.get("ECE_AUDIT_WEBHOOK_URL")
    if not url:
        return

    # Warn for insecure HTTP (production should use HTTPS)
    if url.startswith("http://") and not url.startswith("http://localhost"):
        logger.warning(
            "ECE_AUDIT_WEBHOOK_URL uses insecure HTTP: %s", url
        )

    timeout = float(
        os.environ.get("ECE_AUDIT_WEBHOOK_TIMEOUT", DEFAULT_TIMEOUT_SEC)
    )

    # Add delivery metadata
    payload_with_meta = {
        **payload,
        "delivered_at": time.time(),
    }

    thread = threading.Thread(
        target=_send_sync,
        args=(url, payload_with_meta, timeout),
        daemon=True,
    )
    thread.start()
