"""Sprint 20 v0.2 — audit webhook streaming tests (cut-034).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: stream each
context_request to a configured webhook URL for downstream SIEM /
compliance consumption. Fire-and-forget via threading.

Env:
    ECE_AUDIT_WEBHOOK_URL  # POST target (e.g. https://siem.example.com/ece)
    ECE_AUDIT_WEBHOOK_TIMEOUT  # optional, default 5s

Behavior:
- When unset: no-op (back-compat)
- When set: after record_package commits, async POST fires
- Failures logged but don't block the request
"""
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ece.audit.webhook import (
    is_webhook_enabled,
    send_audit_event,
)
from ece.context.assembly import assemble_context
from ece.db import get_engine


class _WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler that records received POSTs."""

    received_events: list[dict] = []
    received_lock = threading.Lock()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        import json

        try:
            payload = json.loads(body)
        except Exception:
            payload = {"raw": body}
        with _WebhookHandler.received_lock:
            _WebhookHandler.received_events.append(payload)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress noisy logs


def _free_port() -> int:
    """Find an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_events(
    predicate,
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
) -> list[dict]:
    """Poll `_WebhookHandler.received_events` until `predicate(events)` is truthy.

    OEI-009 step 0.1 — replaces the previous fixed `time.sleep(0.5)` (and
    `time.sleep(1.5)` for the failure path). The previous version slept a
    constant amount and depended on the background thread being faster than
    that — when the box was warm (LLM cold start, Onyx container under load,
    many integration tests already running), the thread could miss the window
    and the next assertion saw an empty list. Now we wait *up to* `timeout`
    seconds, polling every `interval`. The default 5s × 0.05s is ~40× the
    old fixed sleep, so even a fully loaded box stays well inside the budget;
    a fast box still returns within the first interval (~50ms).

    The lock is taken on every poll so the background thread can append
    safely between iterations. The final returned snapshot is also taken
    under the lock for the same reason.

    Assertion semantics are unchanged: callers do
        events = _wait_for_events(lambda e: len(e) >= 1)
        assert len(events) >= 1
    — the variable name, the assertion shape, and the `received_lock`
    discipline are all preserved.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _WebhookHandler.received_lock:
            events = list(_WebhookHandler.received_events)
        if predicate(events):
            return events
        time.sleep(interval)
    with _WebhookHandler.received_lock:
        return list(_WebhookHandler.received_events)


@pytest.fixture
def webhook_server():
    """Start a local HTTP server to receive webhook POSTs."""
    _WebhookHandler.received_events.clear()
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), _WebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECE_AUDIT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("ECE_AUDIT_WEBHOOK_TIMEOUT", raising=False)


def test_webhook_disabled_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_webhook_enabled False when ECE_AUDIT_WEBHOOK_URL unset."""
    monkeypatch.delenv("ECE_AUDIT_WEBHOOK_URL", raising=False)
    assert is_webhook_enabled() is False
    # send_audit_event should be no-op (no exception)
    send_audit_event({"request_id": "test", "user_ref": "alice"})


def test_webhook_enabled_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """is_webhook_enabled True when ECE_AUDIT_WEBHOOK_URL configured."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", "http://localhost:9999")
    assert is_webhook_enabled() is True


def test_webhook_receives_event(
    monkeypatch: pytest.MonkeyPatch, webhook_server: str
) -> None:
    """send_audit_event POSTs to webhook and server receives it."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", webhook_server)
    send_audit_event({
        "request_id": "req_abc",
        "user_ref": "alice",
        "intent": "evaluate_purchase_request",
        "status": "ok",
    })
    # Wait briefly for thread to complete
    events = _wait_for_events(lambda e: len(e) >= 1)
    assert len(events) >= 1
    event = events[0]
    assert event["request_id"] == "req_abc"
    assert event["user_ref"] == "alice"
    assert event["intent"] == "evaluate_purchase_request"
    assert event["status"] == "ok"
    assert "delivered_at" in event


def test_assemble_context_triggers_webhook(
    monkeypatch: pytest.MonkeyPatch, webhook_server: str
) -> None:
    """assemble_context fires webhook after record_package commits."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", webhook_server)
    engine = get_engine()
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-webhook-user",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_WEBHOOK_1"}],
    )
    # Wait for the webhook for THIS request_id to arrive (event arrives out of
    # order; OEI-008 R1 audit rows share the queue with other tests in the file)
    events = _wait_for_events(lambda e: any(ev.get("request_id") == pkg.request_id for ev in e))
    # Find event matching this request_id
    matching = [e for e in events if e.get("request_id") == pkg.request_id]
    assert len(matching) == 1
    event = matching[0]
    assert event["user_ref"] == "demo-webhook-user"
    assert event["intent"] == "evaluate_purchase_request"
    # status may be 'ok' or 'insufficient_context' depending on seeded data
    assert event["status"] in ("ok", "insufficient_context")
    assert "counts" in event
    assert "latency_ms" in event


def test_webhook_does_not_block_request(
    monkeypatch: pytest.MonkeyPatch, webhook_server: str
) -> None:
    """Webhook delivery does not block assemble_context (fire-and-forget)."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", webhook_server)
    engine = get_engine()
    t0 = time.monotonic()
    assemble_context(
        engine=engine,
        user_ref="demo-webhook-fast",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_WEBHOOK_FAST"}],
    )
    elapsed = time.monotonic() - t0
    # Should be fast (< 1s) even though webhook thread may take longer
    assert elapsed < 1.0


def test_webhook_multiple_events(
    monkeypatch: pytest.MonkeyPatch, webhook_server: str
) -> None:
    """Multiple send_audit_event calls deliver all events."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", webhook_server)
    for i in range(3):
        send_audit_event({"request_id": f"req_{i}", "user_ref": "alice"})
    events = _wait_for_events(lambda e: len(e) >= 3)
    assert len(events) >= 3
    request_ids = {e["request_id"] for e in events}
    assert "req_0" in request_ids
    assert "req_1" in request_ids
    assert "req_2" in request_ids


def test_webhook_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook pointing to invalid URL → no exception in caller."""
    # Use a port that's not listening
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", "http://127.0.0.1:1")  # port 1 = unlikely listening
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_TIMEOUT", "1")  # 1s timeout
    # Should not raise — failure is logged + daemon thread dies silently
    send_audit_event({"request_id": "req_fail", "user_ref": "alice"})
    time.sleep(1.5)  # wait for thread timeout


def test_webhook_includes_delivery_metadata(
    monkeypatch: pytest.MonkeyPatch, webhook_server: str
) -> None:
    """Webhook payload includes delivered_at metadata."""
    monkeypatch.setenv("ECE_AUDIT_WEBHOOK_URL", webhook_server)
    t0 = time.time()
    send_audit_event({"request_id": "req_meta", "user_ref": "alice"})
    events = _wait_for_events(lambda e: len(e) >= 1)
    assert events[0]["delivered_at"] >= t0
