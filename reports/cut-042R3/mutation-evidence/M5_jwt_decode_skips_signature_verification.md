# Mutation Anchor M5 — jwt_decode_skips_signature_verification

**Target**: `src/ece/auth/jwt.py`
**Test**: `tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature`
**Date**: 2026-09-22

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_s13_jwt_auth.py [31mF[0m[31m                                 [100%][0m

=================================== FAILURES ===================================
[31m[1m___________________ test_decode_jwt_token_invalid_signature ____________________[0m
[1m[31mtests/integration/test_s13_jwt_auth.py[0m:75: in test_decode_jwt_token_invalid_signature
    [0m[94massert[39;49;00m claims [95mis[39;49;00m [94mNone[39;49;00m[90m[39;49;00m
[1m[31mE   AssertionError: assert {'sub': 'alice', 'iat': 1790116630, 'exp': 1790120230} is None[0m
[33m=============================== warnings summary ===============================[0m
tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/jwt/api_jwt.py:149: InsecureKeyLengthWarning: The HMAC key is 12 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    return self._jws.encode(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_s13_jwt_auth.py::[1mtest_decode_jwt_token_invalid_signature[0m - AssertionError: assert {'sub': 'alice', 'iat': 1790116630, 'exp': 179012023...
[31m========================= [31m[1m1 failed[0m, [33m1 warning[0m[31m in 0.07s[0m[31m =========================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_s13_jwt_auth.py [32m.[0m[33m                                 [100%][0m

[33m=============================== warnings summary ===============================[0m
tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/jwt/api_jwt.py:149: InsecureKeyLengthWarning: The HMAC key is 12 bytes long, which is below the minimum recommended length of 32 bytes for SHA256. See RFC 7518 Section 3.2.
    return self._jws.encode(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[33m========================= [32m1 passed[0m, [33m[1m1 warning[0m[33m in 0.04s[0m[33m =========================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`3c633ed8`)
