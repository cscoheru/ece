# Mutation Anchor M1 — re_read_through_assembly_skipped

**Target**: `src/ece/v0/loop.py`
**Test**: `tests/integration/test_v0_loop.py::test_re_read_asks_the_assembly_path_again`
**Date**: 2026-09-22

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_v0_loop.py F                                      [100%]

=================================== FAILURES ===================================
__________________ test_re_read_asks_the_assembly_path_again ___________________
tests/integration/test_v0_loop.py:261: in test_re_read_asks_the_assembly_path_again
    result = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
src/ece/v0/loop.py:163: in run_v0_loop
    return _run_demo_loop_impl(
src/ece/v0/loop.py:540: in _run_demo_loop_impl
    _assert_loop_closed(
src/ece/v0/loop.py:214: in _assert_loop_closed
    raise RuntimeError(
E   RuntimeError: loop did not close: re-read review_status='pending' != decision_value='review_required'
=========================== short test summary info ============================
FAILED tests/integration/test_v0_loop.py::test_re_read_asks_the_assembly_path_again
============================== 1 failed in 1.01s ===============================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_v0_loop.py .                                      [100%]

============================== 1 passed in 0.81s ===============================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`ad4f13ea`)
