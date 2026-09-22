# Mutation Anchor M3 — permission_acl_check_bypassed

**Target**: `src/ece/context/assembly.py`
**Test**: `tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db`
**Date**: 2026-09-22

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_params_land_in_db.py [31mF[0m[31m                            [100%][0m

=================================== FAILURES ===================================
[31m[1m____________________ test_denied_user_does_not_write_to_db _____________________[0m
[1m[31mtests/integration/test_params_land_in_db.py[0m:291: in test_denied_user_does_not_write_to_db
    [0m[94massert[39;49;00m body.get([33m"[39;49;00m[33mconclusion[39;49;00m[33m"[39;49;00m) == [33m"[39;49;00m[33mno_permission[39;49;00m[33m"[39;49;00m, ([90m[39;49;00m
[1m[31mE   AssertionError: R2-F1: denied user must get no_permission; got 'auto_approved'[0m
[1m[31mE   assert 'auto_approved' == 'no_permission'[0m
[1m[31mE     [0m
[1m[31mE     [0m[91m- no_permission[39;49;00m[90m[39;49;00m[0m
[1m[31mE     [92m+ auto_approved[39;49;00m[90m[39;49;00m[0m
[33m=============================== warnings summary ===============================[0m
tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_params_land_in_db.py::[1mtest_denied_user_does_not_write_to_db[0m - AssertionError: R2-F1: denied user must get no_permission; got 'auto_approved'
[31m========================= [31m[1m1 failed[0m, [33m1 warning[0m[31m in 0.60s[0m[31m =========================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_params_land_in_db.py [32m.[0m[33m                            [100%][0m

[33m=============================== warnings summary ===============================[0m
tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[33m========================= [32m1 passed[0m, [33m[1m1 warning[0m[33m in 0.48s[0m[33m =========================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`e37312e1`)
