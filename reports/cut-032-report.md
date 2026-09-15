# Cut-032 Report — RS256 asymmetric JWT

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-032 |
| Date | 2026-09-15 |
| Sprint | Sprint 18 v0.2 |
| Scope | RS256 asymmetric JWT support |
| Author | Claude Fable 5 |
| Commit | `40925e7` |
| Branch | `main` |
| Test delta | 306 → 315 (+9) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s18_rs256_jwt.py` | 9 tests with RSA keypair generation |

### 2.2 Files modified

| File | Change |
|---|---|
| `src/ece/auth/jwt.py` | Added `ECE_JWT_PUBLIC_KEY` env; `_get_verification_key()` picks public_key over secret |

### 2.3 Env config

```bash
# RS256 mode (cut-032) — IdP keeps private key
export ECE_JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----...-----END PUBLIC KEY-----"
export ECE_JWT_ALGORITHM="RS256"

# HS256 mode (cut-027) — symmetric secret, single-service
export ECE_JWT_SECRET="<shared-secret-min-32-bytes>"
export ECE_JWT_ALGORITHM="HS256"
```

When both `ECE_JWT_PUBLIC_KEY` and `ECE_JWT_SECRET` are set, public
key takes precedence (cut-032 design — assumes deployment upgrade
to RS256).

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 111 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 315 passed, 6 skipped, 2 warnings in 32.79s (was 306; +9 RS256 tests)
```

## 4. Commit hash

- HEAD: `40925e7 feat(auth): RS256 asymmetric JWT via ECE_JWT_PUBLIC_KEY (cut-032)`
- Pushed: `88fac59..40925e7 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 PyJWT auto-detects algorithm from key type

PyJWT's `decode(token, key, algorithms=[alg])` accepts either a
secret (for HMAC) or a public key PEM (for RSA/EC). The library
detects key type and applies the right verification.

We just pass the key string; PyJWT handles the rest.

### 5.2 Multi-service deployment pattern

With RS256, ECE only needs the IdP's public key. IdP keeps private
key. Multiple services (ECE + other apps) can verify tokens without
sharing secrets. Reduces key rotation surface area.

### 5.3 Key rotation

RS256 keys can be rotated without service restart:
1. IdP starts signing with new key
2. ECE admin adds new public key to `ECE_JWT_PUBLIC_KEY` (multi-key
   support in cut-035+)
3. Tokens during transition period verify against either old or new key
4. Once all tokens use new key, remove old from env

For v0.2 simplicity, single key only. Multi-key rotation in cut-035+.

## 6. Lessons

### 6.1 RSA keypair generation in test fixture

`cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key` +
`private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())` —
standard pattern for generating test keys. ~50ms per keypair.

For test suite speed, use `scope="module"` so keypair is generated
once per file (not per test).

### 6.2 cryptography library as test-time dep

`cryptography` is a heavyweight library (libssl binding). Required
for test RSA keypair generation. For production ECE, the dep is only
needed if RSA key generation is done at runtime (it's not — public
key is supplied via env).

For v0.2 simplicity, keep cryptography as dev dep only. PyJWT's RSA
support is built-in.

### 6.3 Test naming: signed_with_X vs verified_with_Y

`test_decode_rs256_wrong_public_key` originally tried to verify a
token signed with one key against a different key. But env setup
makes the verification key = signing key (otherwise test fails on
unrelated reason). Refactored to use 3 keys: token signed with
"third" key, env uses "other" key — clearly mismatch.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>