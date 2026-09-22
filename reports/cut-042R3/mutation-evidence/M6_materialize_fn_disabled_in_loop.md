# Mutation Anchor M6 — materialize_fn_disabled_in_loop

**Target**: `src/ece/v0/loop.py`
**Test**: `tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop`
**Date**: 2026-09-22

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_params_land_in_db.py [31mF[0m[31m                            [100%][0m

=================================== FAILURES ===================================
[31m[1m________________ test_params_quote_count_lands_in_db_after_loop ________________[0m
[1m[31mtests/integration/test_params_land_in_db.py[0m:176: in test_params_quote_count_lands_in_db_after_loop
    [0m[94massert[39;49;00m db_count == target_quote_count, ([90m[39;49;00m
[1m[31mE   AssertionError: R2-F2: DB SELECTS relation count must equal params.quote_count (2); got 1. This is the R2-F2 finding: quote_count must rebuild SELECTS relations, not just be a rule parameter.[0m
[1m[31mE   assert 1 == 2[0m
[33m=============================== warnings summary ===============================[0m
tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_params_land_in_db.py::[1mtest_params_quote_count_lands_in_db_after_loop[0m - AssertionError: R2-F2: DB SELECTS relation count must equal params.quote_co...
[31m========================= [31m[1m1 failed[0m, [33m1 warning[0m[31m in 0.49s[0m[31m =========================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_params_land_in_db.py [32m.[0m[33m                            [100%][0m

[33m=============================== warnings summary ===============================[0m
tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[33m========================= [32m1 passed[0m, [33m[1m1 warning[0m[33m in 0.46s[0m[33m =========================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`64bc20bc`)
