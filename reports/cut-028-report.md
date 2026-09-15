# Cut-028 Report — user-level revocation

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-028 |
| Date | 2026-09-15 |
| Sprint | Sprint 14 v0.2 |
| Scope | `ECE_REVOKED_USERS` user-level denial |
| Author | Claude Fable 5 |
| Commit | `e112fea` |
| Branch | `main` |
| Test delta | 266 → 277 (+11) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s14_revoked_users.py` | 11 tests |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/api/delegation.py` | Added `parse_revoked_users()`, `is_user_revoked()`; `user_can_access()` blocks ALL access when caller OR trace owner is revoked |

### 2.3 Env config

```bash
ECE_REVOKED_USERS="fired_employee,banned_user,terminated_contractor"
```

Format: comma-separated list. Whitespace tolerant. Empty entries skipped.

## 3. cut-024 vs cut-028 comparison

| Aspect | cut-024 (ECE_REVOKED_TOKENS) | cut-028 (ECE_REVOKED_USERS) |
|---|---|---|
| Effect on owner access | Preserved (owner still works) | Blocked (owner denied) |
| Effect on delegation tokens | Token grants disabled | All grants disabled |
| Effect on user's own traces | Still readable | Not readable |
| Use case | Compromised token | Fired employee / banned user |
| Strength | Soft | Strong (full lockout) |

Both envs can be active simultaneously. Revocation precedence:
1. cut-028 (user revoked) → block all access
2. cut-024 (token revoked) → disable token grants only

## 4. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 106 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 277 passed, 6 skipped, 2 warnings in 29.05s (was 266; +11)
```

## 5. Commit hash

- HEAD: `e112fea feat(revocation): ECE_REVOKED_USERS user-level revocation (cut-028)`
- Pushed: `b1c8b61..e112fea main -> main` (via Clash proxy)

## 6. Non-typical items

### 6.1 Owner revocation is intentionally strict

If `alice` is in `ECE_REVOKED_USERS`, alice cannot read her OWN traces.
This is intentionally strong — for true lockout scenarios (employee
fired), they shouldn't have any access at all.

For soft deactivation (e.g., temporary suspension), use cut-024
(token revocation) instead, which preserves owner access for compliance
review.

### 6.2 Trace owner revocation blocks delegated access

If alice's user_ref is revoked, AND bob has a delegation token
granting access to alice's traces, bob's access is blocked too.
Revocation is at the user level, not the user×token level.

This means: revoking alice instantly protects her entire audit history
from all access paths.

### 6.3 No new env var dependency

Same env pattern as cut-024 (`ECE_REVOKED_USERS`). Operators familiar
with `ECE_REVOKED_TOKENS` immediately understand the new env.

## 7. Lessons

### 7.1 Two-tier revocation model

| Tier | Env | Strength | Use case |
|---|---|---|---|
| 1 (soft) | ECE_REVOKED_TOKENS | Token grants disabled | Compromised token |
| 2 (hard) | ECE_REVOKED_USERS | All access denied | Fired employee |

Operators choose tier based on severity. Both can be active.

### 7.2 Revocation precedence: user first

`user_can_access()` checks `is_user_revoked(x_user_id) or
is_user_revoked(trace_user_ref)` BEFORE owner / delegation. This
ensures revocation is the strongest control — no token can override.

### 7.3 Reversibility

Revocation is instant via env edit. To restore access:
- Remove user_ref from `ECE_REVOKED_USERS`
- No process restart needed (env re-read per request)

Unlike cut-024 (token revocation), cut-028 affects user history too
(trace.owner == revoked_user). After re-add, the user can read their
own history again, but other users with delegation tokens still need
to re-establish access.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>