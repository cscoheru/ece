# Mutation Anchor M6 — materialize_fn_disabled_in_loop

**Target**: `src/ece/v0/loop.py`
**Test**: `tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop`
**Date**: 2026-09-22

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_params_land_in_db.py F                            [100%]

=================================== FAILURES ===================================
________________ test_params_quote_count_lands_in_db_after_loop ________________
tests/integration/test_params_land_in_db.py:176: in test_params_quote_count_lands_in_db_after_loop
    assert db_count == target_quote_count, (
E   AssertionError: R2-F2: DB SELECTS relation count must equal params.quote_count (2); got 1. This is the R2-F2 finding: quote_count must rebuild SELECTS relations, not just be a rule parameter.
E   assert 1 == 2
=============================== warnings summary ===============================
tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop
========================= 1 failed, 1 warning in 0.66s =========================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_params_land_in_db.py .                            [100%]

=============================== warnings summary ===============================
tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 1 passed, 1 warning in 0.65s =========================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`ad4f13ea`)
