# Cut-022 Report — per-resource delegation

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-022 |
| Date | 2026-09-15 |
| Sprint | Sprint 9 v0.2 |
| Scope | per-resource delegation via `ECE_AUDIT_TOKEN_REQUEST_IDS` |
| Author | Claude Fable 5 |
| Commit | `80a4622` |
| Branch | `main` |
| Test delta | 196 → 207 (+11) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s9_per_resource_scope.py` | 11 tests for per-resource delegation |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/delegation.py` | Added `parse_request_id_delegation_tokens()` and `request_id_can_access()` |
| `src/ece/api/audit.py` | Per-resource check moved BEFORE `user_can_access` + `check_org_access`; if granted, skip both |
| `src/ece/api/debug.py` | Same per-resource check ordering as /audit |
| `docs/API.md` | §8 audit header table adds per-resource row |
| `docs/v0.2-deploy.md` | §4 multi-tenant adds per-resource section |

### 2.3 Env config

```bash
ECE_AUDIT_TOKEN_REQUEST_IDS="audit_tok:req_abc,req_xyz;external:req_def"
```

Format: `token:request_id1,request_id2;token2:request_id3`. Token grants
access to SPECIFIC request_ids only, regardless of who owns them or what
org they're in.

### 2.4 Use cases

- **External auditor** given specific case ID for incident review
- **Customer support** looking up specific trace for a ticket
- **Compliance** single-trace inspection (no broader read access)

### 2.5 Permission check order (5 steps in /audit + /debug)

```
1. Owner check (X-User-Id == trace.user_ref) — always allow
2. Per-USER delegation (ECE_DELEGATION_TOKENS) — cut-018b
3. Per-ORG delegation (ECE_DELEGATION_ORG_TOKENS) — cut-021
4. Per-RESOURCE delegation (ECE_AUDIT_TOKEN_REQUEST_IDS) — cut-022
5. X-Org-Id match (X-Org-Id == trace.org_id) — cut-019
```

Step 4 grants access regardless of steps 1-3 outcome (orthogonal grant
channel — independent of ownership, user delegation, org delegation).
Steps 2-4 bypass step 5 for cross-USER / cross-ORG / per-resource access
respectively.

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 98 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 207 passed, 6 skipped, 1 warning in 23.02s (was 196; +11 per-resource)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-022 adds 11):
- 2 unit tests for `parse_request_id_delegation_tokens` (basic / empty)
- 5 unit tests for `request_id_can_access` (match / no-match / no-token / no-request_id / not-in-env)
- 4 integration tests for /audit + /debug (granted / denied other / falls through / debug granted)

## 4. Commit hash

- HEAD: `80a4622 feat(delegation): ECE_AUDIT_TOKEN_REQUEST_IDS per-resource scope (cut-022)`
- Pushed: `5bac946..80a4622 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Per-resource check runs BEFORE owner check

`request_id_can_access()` is evaluated before `user_can_access()` in
both /audit and /debug handlers. This means a per-resource token grants
access REGARDLESS of who owns the trace.

Rationale: per-resource scope is an orthogonal grant channel. It
should not depend on owner / per-user / per-org logic. If the token
matches, the request is granted.

If placed AFTER owner check, a per-resource token would never trigger
when the requester is not the owner — defeating its purpose.

### 5.2 Per-resource bypasses X-Org-Id check entirely

When `request_id_can_access()` returns True, the X-Org-Id check is
NOT executed. This means an external auditor (no X-Org-Id) can read
a trace in any org, as long as the token grants that specific request_id.

Trade-off: external auditors don't need org membership. Security
relies entirely on token confidentiality and rotation discipline.

### 5.3 Permission check redundancy is intentional

Steps 1-4 all check different grant channels. They can all pass for
the same request (e.g., owner + per-user delegation + per-resource).
The OR semantics mean we accept if ANY channel grants access.

The order is intentional: per-resource first (most specific grant),
then broader grants (owner / per-user / per-org), then fallback
(X-Org-Id match).

### 5.4 No new dependency, pure env config

Per-resource delegation uses the same env-var pattern as cut-018b /
cut-021. No new database schema, no new API endpoints, no new LLM
dependencies. Operators familiar with the prior delegation envs can
configure `ECE_AUDIT_TOKEN_REQUEST_IDS` immediately.

## 6. Lessons

### 6.1 Test design: per-resource token for non-owner

The test that initially failed (`test_audit_per_resource_grants_specific_request`)
set `X-User-Id: USER_OTHER` (not the trace owner) with per-resource
token. This is intentional — it exercises the case where per-resource
grants access despite non-owner status.

Initial implementation had per-resource check AFTER `user_can_access`,
which fired the owner check first and returned 403 before per-resource
could grant. **Fix**: move per-resource check BEFORE owner check.

**Lesson**: when adding a new grant channel, place it BEFORE existing
checks if it should bypass them. Per-resource scope is orthogonal and
should not depend on ownership semantics.

### 6.2 Five-step permission model is now stable

After cut-022, the /audit + /debug permission model has 5 distinct
steps. This is the maximum expected for v0.2. Future additions should
consider whether they fit one of the existing 5 channels or warrant a
new step.

```
1. Owner                 — single-user, no token
2. Per-USER delegation   — multi-user within same org
3. Per-ORG delegation    — multi-user across orgs (manager)
4. Per-RESOURCE          — single specific trace (external auditor)
5. X-Org-Id match        — same-org fallback when no token
```

### 6.3 Env-var delegation pattern is repeatable

`ECE_DELEGATION_TOKENS` (per-user), `ECE_DELEGATION_ORG_TOKENS` (per-org),
`ECE_AUDIT_TOKEN_REQUEST_IDS` (per-resource) — all follow the same
`token:value1,value2;...` syntax. Adding a new scope (e.g.,
per-intent in cut-024+) would mechanically follow this pattern.

**Pattern**: `ECE_<SCOPE>_<GRANT>_TOKENS = "token:val1,val2;..."`.

### 6.4 Token-specific endpoints not yet implemented

Currently, per-resource tokens work via `ECE_AUDIT_TOKEN_REQUEST_IDS`
env. There's no admin endpoint to rotate or revoke a single token.
For production, consider adding:
- `POST /admin/tokens` to mint tokens with specific grants
- `DELETE /admin/tokens/{token}` to revoke
- Token audit log (which token accessed which trace when)

These would extend the API surface but are out of scope for cut-022.

## 7. Cut-023+ preview

Possible next cuts (in priority order):

1. **cut-023**: org-level rate limiting — `ECE_ORG_RATE_LIMITS="org_a:100/m"`.
   Token bucket per org for /context + /audit + /debug. Protects
   against runaway scripts.

2. **cut-024**: v0.2 cut-over — full RBAC doc + production rollout
   checklist (multi-tenant + cross-org delegation + per-resource +
   audit token rotation).

3. **cut-025**: JWT migration — replace `X-User-Id` header with decoded
   JWT claim. Eliminates user_ref spoofing; SSO-friendly.

4. **cut-026**: token revocation list (`ECE_REVOKED_TOKENS`) — quick
   way to invalidate compromised tokens without env restart.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>