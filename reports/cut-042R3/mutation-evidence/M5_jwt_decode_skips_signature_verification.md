# Mutation Anchor M5 — jwt_decode_skips_signature_verification

**Target**: `src/ece/auth/jwt.py`
**Test**: `tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature`
**Date**: 2026-09-22

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_s13_jwt_auth.py F                                 [100%]

=================================== FAILURES ===================================
___________________ test_decode_jwt_token_invalid_signature ____________________
tests/integration/test_s13_jwt_auth.py:75: in test_decode_jwt_token_invalid_signature
    assert claims is None
E   AssertionError: assert {'sub': 'alice', 'iat': 1790062163, 'exp': 1790065763} is None
=============================== warnings summary ===============================
tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/jwt/api_jwt.py:149: InsecureKeyLengthWarning: The HMAC key is 12 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    return self._jws.encode(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature
========================= 1 failed, 1 warning in 0.07s =========================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_s13_jwt_auth.py .                                 [100%]

=============================== warnings summary ===============================
tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/jwt/api_jwt.py:149: InsecureKeyLengthWarning: The HMAC key is 12 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    return self._jws.encode(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 1 passed, 1 warning in 0.05s =========================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`3c633ed8`)
