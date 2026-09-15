# Cut-024 Report — token revocation list

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-024 |
| Date | 2026-09-15 |
| Sprint | Sprint 11 v0.2 |
| Scope | `ECE_REVOKED_TOKENS` env-based token revocation |
| Author | Claude Fable 5 |
| Commit | `2f85fe4` |
| Branch | `main` |
| Test delta | 219 → 230 (+11) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s11_revoked_tokens.py` | 11 tests for token revocation |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/delegation.py` | Added `parse_revoked_tokens()` + `is_token_revoked()`; integrated into `resolve_user_refs` + `request_id_can_access` |
| `src/ece/api/org.py` | `check_org_access` rejects revoked tokens with `token_revoked` error code |
| `docs/API.md` | §8 audit header table notes X-User-Id owner check is irrevocable |
| `docs/v0.2-deploy.md` | §4 multi-tenant adds `ECE_REVOKED_TOKENS` section + recovery instructions |

### 2.3 Env config

```bash
ECE_REVOKED_TOKENS="compromised_tok_1,leaked_tok_2,expired_tok_3"
```

Format: comma-separated list. Whitespace tolerant. Empty entries skipped.

### 2.4 Behavior

| Caller state | Revocation effect |
|---|---|
| Owner (X-User-Id == trace.user_ref) | ✅ Always allowed (owner check bypasses revocation) |
| Per-USER delegation token (revoked) | ❌ 403 — token treated as no token |
| Per-ORG delegation token (revoked) | ❌ 403 with `token_revoked` — org check fails |
| Per-RESOURCE delegation token (revoked) | ❌ 403 — `request_id_can_access` returns False |
| No token | ✅ Allowed if other channels grant access (owner, X-Org-Id match) |

### 2.5 Recovery workflow

```bash
# 1. Operator detects compromised token via logs
# 2. Edit deployment config to add token to ECE_REVOKED_TOKENS
# 3. Roll out config change (k8s rollout, env reload, etc.)
# 4. Process picks up change on next request (env re-read per request)
# 5. Optionally rotate token (generate new value, update consumers)
```

For long-running processes, consider:
- Periodic reload via SIGHUP
- Admin endpoint to mutate `ECE_REVOKED_TOKENS` at runtime
- Cache invalidation hook

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 101 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 230 passed, 6 skipped, 1 warning in 23.26s (was 219; +11 revocation tests)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-024 adds 11):
- 2 unit tests for `parse_revoked_tokens` (basic / empty)
- 3 unit tests for `is_token_revoked` (match / not-in-list / no-token)
- 1 unit test: `resolve_user_refs` treats revoked token as no token
- 2 unit tests: `user_can_access` owner unaffected + revoked token blocks delegated
- 1 unit test: `check_org_access` blocks cross-org with `token_revoked` code
- 2 integration tests: /audit revoked token → 403; owner access unaffected

## 4. Commit hash

- HEAD: `2f85fe4 feat(revocation): ECE_REVOKED_TOKENS compromise mitigation (cut-024)`
- Pushed: `0ada1d3..2f85fe4 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Revocation silent vs explicit error

`check_org_access` returns `(False, "token_revoked")` with explicit
error code. Other functions (`resolve_user_refs`, `request_id_can_access`)
silently treat revoked tokens as no token.

**Rationale**: explicit error helps operators debug cross-org failures.
Silent revocation in per-user / per-resource paths prevents information
disclosure about which tokens are revoked (less useful to attackers).

### 5.2 Owner access is irrevocable

X-User-Id == trace.user_ref always grants access, even if the user_ref
itself appears in some revocation list. This is because owner access
bypasses all token-based checks.

**Future cut**: if user-level revocation is needed (e.g., "fire this
employee, revoke all their access"), add `ECE_REVOKED_USERS` env that
blocks owner check too. Out of scope for cut-024.

### 5.3 Per-request env re-read

`parse_revoked_tokens()` re-reads `os.environ` on every call. No
caching. This means env changes (via deployment rollout) take effect
immediately without process restart.

**Trade-off**: env reads are cheap, but for high-traffic deployments
consider caching with TTL.

### 5.4 Revocation is a global list

All delegation tokens (per-user, per-org, per-resource) share the same
revocation list. Cannot revoke "only for per-org" or "only for
per-resource" — token is either fully revoked or active.

**Trade-off**: simpler model, fewer env vars. If finer granularity
needed, split into per-scope revocation lists (cut-025+).

## 6. Lessons

### 6.1 Revocation check belongs in resolve_user_refs, not audit.py

If revocation was checked only at the audit/debug handler level, it
would be easy to forget when adding new endpoints. By placing
`is_token_revoked` at the top of `resolve_user_refs`, all token-based
delegation flows are uniformly protected.

**Pattern**: revocation = early return at the token resolution layer.

### 6.2 Owner access must NOT consult revocation

Common security antipattern: revocation also blocks owner. This breaks
operational scenarios where a user is temporarily locked out but still
needs to read their own audit history for compliance.

Current cut-024 design: owner bypasses revocation. If user-level
revocation is needed, add a separate `ECE_REVOKED_USERS` env that
explicitly checks owner status (cut-025+).

### 6.3 Test verifies both directions

`test_audit_owner_access_unaffected_by_revocation` proves that even
with a revoked token in env, the owner's `/audit` call still returns
200. Without this test, a refactor could accidentally break owner
access during revocation enforcement.

**Lesson**: revocation tests must verify both the deny path AND the
"owner still works" path. Don't just test that the bad thing fails.

### 6.4 Token format flexibility

`ECE_REVOKED_TOKENS` accepts comma-separated tokens. This matches the
most common format. Future cuts could add:
- Token expiry (`ECE_TOKEN_EXPIRY="tok1:2024-12-31,tok2:2025-01-15"`)
- Per-scope revocation (separate vars for per-user / per-org / per-resource)

For v0.2, single revocation list is sufficient.

## 7. Cut-025+ preview

Possible next cuts (in priority order):

1. **cut-025**: v0.2 cut-over — full RBAC doc + production rollout
   checklist consolidating cut-018b → cut-024 into one runbook.

2. **cut-026**: Redis-backed rate limit — replace in-memory `_buckets`
   with Redis INCR for multi-process correctness (extends cut-023).

4. **cut-027**: JWT migration — replace `X-User-Id` header with decoded
   JWT claim. SSO-friendly; eliminates user_ref spoofing.

5. **cut-028**: user-level revocation (`ECE_REVOKED_USERS`) — fires
   users by blocking owner access. Out of scope for cut-024.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>