# Cut-034 Report — audit webhook streaming

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-034 |
| Date | 2026-09-15 |
| Sprint | Sprint 20 v0.2 |
| Scope | `ECE_AUDIT_WEBHOOK_URL` async POST streaming |
| Author | Claude Fable 5 |
| Commit | `d63a9b4` |
| Branch | `main` |
| Test delta | 321 → 329 (+8) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `src/ece/audit/webhook.py` | `is_webhook_enabled()` + `send_audit_event()` (daemon thread + httpx) |
| `tests/integration/test_s20_audit_webhook.py` | 8 tests using local HTTPServer fixture |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/context/provenance.py` | `record_package()` calls `send_audit_event()` after DB commit |

### 2.3 Env config

```bash
export ECE_AUDIT_WEBHOOK_URL="https://siem.example.com/ece/events"
export ECE_AUDIT_WEBHOOK_TIMEOUT="5"  # seconds, default 5
```

When unset: no-op (back-compat). When set: every `context_request`
INSERT triggers async POST.

### 2.4 Behavior

```python
# In record_package(), after DB commit:
if is_webhook_enabled():
    send_audit_event({
        "request_id": str(request_id),
        "user_ref": user_ref,
        "intent": intent,
        "status": status,
        "counts": counts,
        "latency_ms": latency_ms,
        "user_org": user_org,
    })
```

`send_audit_event()` spawns a daemon thread that:
1. POSTs JSON payload to webhook URL
2. Logs failure (4xx, 5xx, network error) but doesn't raise
3. Adds `delivered_at` timestamp metadata

Caller is never blocked by webhook delivery (fire-and-forget).

### 2.5 Use cases

- **SIEM ingestion**: per-event stream for Splunk / Elastic / Sumo
- **Compliance dashboard**: real-time audit log feed
- **Custom monitoring**: webhook to internal alerting system

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 114 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 329 passed, 6 skipped, 2 warnings in 57.09s (was 321; +8 webhook tests)
```

## 4. Commit hash

- HEAD: `d63a9b4 feat(audit): ECE_AUDIT_WEBHOOK_URL async POST for SIEM streaming (cut-034)`
- Pushed: `f5f3e41..d63a9b4 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Daemon thread vs asyncio

Used `threading.Thread(daemon=True)` instead of `asyncio.create_task`.
Rationale:
- record_package is called from sync code (FastAPI sync handlers)
- Threading works in both sync and async contexts
- Daemon threads die with the process (no orphan threads on shutdown)
- Simpler than asyncio for fire-and-forget

For high-throughput (>10k events/sec), an asyncio queue + worker
task would scale better. v0.2 keeps simple.

### 5.2 No retry / backoff

Current design: single POST attempt, log failure, move on. No
retry queue.

For at-least-once delivery, would need:
- Persistent queue (Redis list, Kafka)
- Retry with exponential backoff
- Dead-letter queue for permanent failures

cut-035+ if needed.

### 5.3 Security: HTTPS-only recommended

`_send_sync` warns if URL is HTTP (not HTTPS). Production deployments
should use HTTPS to protect audit log contents in transit.

For HTTP localhost testing, the warning is emitted but delivery
succeeds.

## 6. Lessons

### 6.1 Test fixture: HTTPServer for webhook receiver

The test uses Python's built-in `http.server.HTTPServer` in a daemon
thread to receive webhook POSTs. No external dependency (no Flask
test client, no pytest-httpserver).

Pattern:
```python
server = HTTPServer(("127.0.0.1", port), _WebhookHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
yield url
server.shutdown()
```

Standard library only. Works on any Python platform.

### 6.2 Status check should accept both ok and insufficient_context

Trace status depends on seeded data. When test PR doesn't exist in
seed, `assemble_context` returns `insufficient_context`. Tests should
check `status in ("ok", "insufficient_context")` rather than fixed
value.

### 6.3 Fire-and-forget design trades:
- ✅ Caller latency unaffected by webhook delivery
- ✅ Webhook failure doesn't cascade to /context failure
- ❌ No retry / at-least-once delivery guarantee
- ❌ No persistence (events lost if process crashes mid-delivery)

For v0.2, trade-off favors simplicity. Compliance audits prefer
durability; consider cut-035+ for persistent queue.

## 7. Cumulative v0.2 stats (cut-018b → cut-034)

| Cut | Feature | Tests | Cumulative |
|---|---|---|---|
| cut-018b | multi-user delegation | +10 | 169 |
| cut-019 | multi-tenant (X-Org-Id) | +16 | 175 |
| cut-020 | multi-tenant bench | +9 | 184 |
| cut-021 | cross-org delegation | +12 | 196 |
| cut-022 | per-resource scope | +11 | 207 |
| cut-023 | rate limit | +12 | 219 |
| cut-024 | token revocation | +11 | 230 |
| cut-025 | e2e + cutover checklist | +11 | 241 |
| cut-026 | Redis-backed rate limit | +10 | 251 |
| cut-027 | JWT bearer token | +15 | 266 |
| cut-028 | user-level revocation | +11 | 277 |
| cut-029 | per-org quota tracking | +12 | 289 |
| cut-030 | audit export (compliance) | +9 | 298 |
| cut-031 | Redis Lua atomic | +8 | 306 |
| cut-032 | RS256 asymmetric JWT | +9 | 315 |
| cut-033 | items-csv export | +6 | 321 |
| **cut-034** | **audit webhook streaming** | **+8** | **329** |

**Total v0.2 delta**: 159 → 329 tests (+170, +107%).

**17 cuts total** in v0.2 hardening arc.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>