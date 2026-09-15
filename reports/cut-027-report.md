# Cut-027 Report — JWT bearer token auth

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-027 |
| Date | 2026-09-15 |
| Sprint | Sprint 13 v0.2 |
| Scope | JWT bearer token replaces X-User-Id header |
| Author | Claude Fable 5 |
| Commit | `b1c8b61` |
| Branch | `main` |
| Test delta | 251 → 266 (+15) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `src/ece/auth/jwt.py` | JWT decode/extract helpers (HS256 symmetric) |
| `tests/integration/test_s13_jwt_auth.py` | 15 JWT unit tests |

### 2.2 Files modified

| File | Change |
|---|---|
| `pyproject.toml` | Added `pyjwt>=2.8` |
| `src/ece/api/audit.py` | Accept `Authorization` header, prefer JWT over X-User-Id |
| `src/ece/api/debug.py` | Same JWT integration |

### 2.3 Env config

```bash
export ECE_JWT_SECRET="<hmac-secret-min-32-bytes>"
export ECE_JWT_ALGORITHM="HS256"  # default
```

When `ECE_JWT_SECRET` is set, JWT mode is enabled:
- `Authorization: Bearer <token>` header takes precedence
- Token's `sub` claim = user_ref
- `X-User-Id` header still works as fallback

When unset: X-User-Id only (v0.1 back-compat).

### 2.4 Algorithm

```python
# HS256 symmetric JWT
claims = jwt.decode(token, secret, algorithms=[algorithm])
user_ref = claims["sub"]
```

PyJWT validates signature, expiration (exp), and (if configured)
audience/issuer. Returns claims dict or raises `PyJWTError`.

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 105 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 266 passed, 6 skipped, 2 warnings in 25.83s (was 251; +15 JWT tests)
make check-api-docs            → OK - 14 routes registered
```

## 4. Commit hash

- HEAD: `b1c8b61 feat(auth): JWT bearer token (Authorization header) replaces X-User-Id (cut-027)`
- Pushed: `fa6b3e1..b1c8b61 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 X-User-Id remains as fallback (not removed)

When JWT mode is enabled AND a valid JWT is in `Authorization` header,
JWT is used. But if JWT is invalid (e.g., expired), and X-User-Id is
present, X-User-Id is used as fallback. This is for graceful degradation.

**Security note**: in strict mode (cut-028+), invalid JWT + valid
X-User-Id should NOT fall back. Current behavior favors availability
over strict security. Operators in high-trust environments should
disable X-User-Id header (or remove from caller SDK).

### 5.2 HS256 only (symmetric)

v0.2 supports HS256 (HMAC-SHA256, symmetric). For multi-service
deployment where ECE doesn't share secret with identity provider,
asymmetric (RS256/ES256) is needed. cut-031+ for v0.3.

### 5.3 PyJWT minimum key length warning

PyJWT emits `InsecureKeyLengthWarning` for keys <32 bytes. Tests use
32-byte dummy key to suppress. Production should use >=32 bytes
(random secret from password manager / KMS).

## 6. Lessons

### 6.1 type: ignore[attr-defined] for optional modules

When using `try: import X except ImportError: X = None` pattern with
mypy strict, the `_x.attr` access needs `# type: ignore[attr-defined]`
because mypy narrows the type to `None | Module` and considers the
attribute access invalid.

`# type: ignore[union-attr]` (suggested by mypy) does NOT cover the
None case. Use `[attr-defined]` for explicit suppression.

### 6.2 Empty string vs None for header values

`resolve_caller_user_ref("", "")` originally returned `""` (because
both args were passed through unchanged). Test expected None.

**Fix**: treat empty strings as None at the resolver boundary:
```python
if x_user_id_header:
    return x_user_id_header
return None
```

This matches FastAPI's default `Header(None)` semantics where absent
headers are None, but empty strings (e.g., `X-User-Id: `) are kept
as empty strings. Resolver normalizes both to None.

### 6.3 mypy on PyJWT requires type ignore on decode() and PyJWTError

```python
claims = _jwt_lib.decode(...)  # type: ignore[attr-defined]
except _jwt_lib.PyJWTError:  # type: ignore[attr-defined]
```

Both attribute accesses need the ignore because mypy infers
`_jwt_lib` as `None | Module` and refuses to verify `.decode` /
`.PyJWTError` exist on None.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>