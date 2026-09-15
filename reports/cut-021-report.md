# Cut-021 Report — cross-org delegation

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-021 |
| Date | 2026-09-15 |
| Sprint | Sprint 8 v0.2 |
| Scope | cross-org delegation via `ECE_DELEGATION_ORG_TOKENS` |
| Author | Claude Fable 5 |
| Commit | `5afc549` |
| Branch | `main` |
| Test delta | 184 → 196 (+12) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s8_cross_org_delegation.py` | 12 tests for cross-org delegation |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/delegation.py` | Added `parse_org_delegation_tokens()` and `_user_refs_in_orgs()`; extended `resolve_user_refs()` to include per-org token expansion |
| `src/ece/api/org.py` | `check_org_access()` accepts `x_delegation_token`; token grants cross-org access if `trace_org_id` in token's org list |
| `src/ece/api/audit.py` | Passes `x_delegation_token` to `check_org_access()` |
| `src/ece/api/debug.py` | Passes `x_delegation_token` to `check_org_access()` |
| `docs/API.md` | §8 audit header table adds cross-org delegation row |
| `docs/v0.2-deploy.md` | §4 multi-tenant: replaced "not yet wired" with full docs |

### 2.3 Env config

```bash
ECE_DELEGATION_ORG_TOKENS="manager_tok:org_a,org_b;audit_tok:*"
```

Format: `token:org_id1,org_id2;token2:org_id3`. Wildcard `*` grants
cross-ALL-orgs access (audit role).

### 2.4 Header contract

| Endpoint | Header combination | Behavior |
|---|---|---|
| `/audit/context/{id}` + `/debug/context/{id}` | X-Delegation-Token in `ECE_DELEGATION_ORG_TOKENS` + token's orgs include trace's org_id | 200 (cross-org allowed via token) |
| Same endpoints + no token | X-Org-Id matches trace.org_id | 200 (same-org allowed) |
| Same endpoints + no token | X-Org-Id != trace.org_id | 403 (cross-org blocked) |

### 2.5 Order of permission checks

```
1. ADR-004 owner check (X-User-Id match) → always allow
2. Per-USER delegation (X-Delegation-Token in ECE_DELEGATION_TOKENS)
3. Per-ORG delegation (X-Delegation-Token in ECE_DELEGATION_ORG_TOKENS)
4. X-Org-Id match (X-Org-Id == trace.org_id)
```

Steps 2 and 3 grant cross-USER and cross-ORG access respectively, bypassing
step 4. Step 1 always grants access. Step 4 is the fallback when no token
overrides are present.

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 97 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 196 passed, 6 skipped, 1 warning in 22.74s (was 184; +12 cross-org tests)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-021 adds 12):
- 3 unit tests for `parse_org_delegation_tokens` (basic / wildcard / empty)
- 2 unit tests for `resolve_user_refs` with org token (specific / wildcard)
- 3 unit tests for `check_org_access` (delegated / unlisted / invalid falls through)
- 4 integration tests for /audit + /debug (token 200 / no token 403 / wildcard 200 / debug 200)

## 4. Commit hash

- HEAD: `5afc549 feat(delegation): ECE_DELEGATION_ORG_TOKENS cross-org delegation (cut-021)`
- Pushed: `0883fd5..5afc549 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Circular import avoided via function-local import

`delegation.py` imports `parse_user_orgs` from `ece.api.org` (used by
`_user_refs_in_orgs`). `org.py`'s `check_org_access` calls
`parse_org_delegation_tokens` from `ece.api.delegation`. This creates a
circular import at module-load time.

**Resolution**: `parse_user_orgs` is imported at module level in
`delegation.py` (no cycle, since `org.py` doesn't import `delegation.py`
at module level). The reverse direction (`parse_org_delegation_tokens`
in `org.py`) is imported inside the function body of `check_org_access`
(deferred import). Module load completes; the deferred import fires
only at call time, by which point both modules are fully loaded.

### 5.2 Wildcard `*` is a literal, not a regex

The `*` wildcard is checked as a literal string in the org list:
`if "*" in org_ids`. It is NOT a regex pattern. This avoids confusion
with potential org_ids that contain `*` (none expected in practice,
but defensive choice).

Future cuts that add pattern-based org scoping (e.g., `org_*`) would
need explicit regex parsing; current implementation treats `*` only.

### 5.3 Token bypasses X-Org-Id entirely

When a token grants cross-org access, `check_org_access` returns
`(True, "ok")` immediately, skipping the X-Org-Id check. This means a
bearer with valid token does NOT need to send a matching X-Org-Id
header (and indeed can omit it entirely). Documented in API.md
header table.

Trade-off: token bearer becomes responsible for proving their identity
via the token alone (no X-User-Id verification). For production
deployments, consider token rotation + audit logging of token usage.

### 5.4 `_user_refs_in_orgs` is snapshot at call time

The function re-parses `ECE_USER_ORGS` env on every call. If env
changes mid-process (rare but possible during config reload), the
token's resolved user_refs reflect the new state on the next call.
No caching is used.

For high-throughput deployments, consider caching
`parse_user_orgs()` for N seconds. v0.2 cut-021 keeps it simple
(env-driven only, no cache).

## 6. Lessons

### 6.1 Test env mutation hygiene applies to multi-env tests

`test_check_org_access_*` tests mutate BOTH `ECE_USER_ORGS` AND
`ECE_DELEGATION_ORG_TOKENS`. Both must be saved+restored in the
finally block. Forgetting to save/restore the second env causes
test pollution — earlier failures showed tests passing when
`ECE_USER_ORGS` was unset (single-tenant mode), which masked the
real assertion.

**Pattern**: `saved_X = os.environ.get(KEY); ... finally: if saved_X is None: pop else: set`.

### 6.2 Order of org check matters: token FIRST, then X-Org-Id

Placing the token check BEFORE the standard X-Org-Id check in
`check_org_access` ensures tokens override org restrictions. If
reversed, valid token would be ignored when X-Org-Id is wrong,
causing 403 even with delegation authority.

Current order: token → X-Org-Id → result.

### 6.3 Wildcard org token is the "super-admin" pattern

`ECE_DELEGATION_ORG_TOKENS="audit:*"` is equivalent to a super-admin
role. It bypasses ALL org checks for any trace with non-NULL org_id.

**Security consideration**: production deployments should restrict
`*` to specific named tokens (e.g., `audit_tok`) and limit those
tokens to specific callers (e.g., dedicated audit service account
with rotating credentials).

Do NOT use `*` for shared or low-trust tokens.

### 6.4 Test names should reflect the actual condition tested

Original test `test_check_org_access_token_does_not_grant_unlisted_org`
had `x_org_id=None` expecting `org_mismatch`. But the code returns
`org_id_required` first (when X-Org-Id is missing entirely). The fix:
set `x_org_id=ORG_X` (caller's own org) so the code path goes through
to the org comparison and returns `org_mismatch` correctly.

**Lesson**: trace through the function's branches in the test setup
to ensure the assertion matches the actual control flow, not the
intended semantic meaning.

## 7. Cut-022+ preview

Possible next cuts (in priority order):

1. **cut-022**: per-resource scope — auditor views specific request_id
   only (e.g., `ECE_AUDIT_TOKEN_REQUEST_IDS="audit_tok:req_abc,req_xyz"`).
   Extends delegation from "all traces by user X" to "specific traces
   by ID".

2. **cut-023**: org-level rate limiting — `ECE_ORG_RATE_LIMITS="org_a:100/m"`.
   Token bucket per org for /context + /audit + /debug.

3. **cut-024**: v0.2 cut-over — full RBAC doc + production rollout
   checklist (multi-tenant + cross-org delegation + audit token
   rotation).

4. **cut-025**: JWT migration — replace `X-User-Id` header with decoded
   JWT claim (eliminate user_ref guessing; SSOfriendly).

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>