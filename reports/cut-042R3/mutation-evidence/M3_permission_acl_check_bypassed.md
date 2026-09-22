# Mutation Anchor M3 — permission_acl_check_bypassed

**Target**: `src/ece/context/assembly.py`
**Test**: `tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db`
**Date**: 2026-09-22

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_params_land_in_db.py F                            [100%]

=================================== FAILURES ===================================
____________________ test_denied_user_does_not_write_to_db _____________________
tests/integration/test_params_land_in_db.py:291: in test_denied_user_does_not_write_to_db
    assert body.get("conclusion") == "no_permission", (
E   AssertionError: R2-F1: denied user must get no_permission; got 'auto_approved'
E   assert 'auto_approved' == 'no_permission'
E     
E     - no_permission
E     + auto_approved
=============================== warnings summary ===============================
tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db
========================= 1 failed, 1 warning in 0.74s =========================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_params_land_in_db.py .                            [100%]

=============================== warnings summary ===============================
tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 1 passed, 1 warning in 0.59s =========================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`e37312e1`)
