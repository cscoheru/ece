# Mutation Anchor M2 — apply_context_update_skip_sql

**Target**: `src/ece/context/update.py`
**Test**: `tests/integration/test_v0_loop.py::test_loop_result_carries_every_step_product`
**Date**: 2026-09-22

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_v0_loop.py [31mF[0m[31m                                      [100%][0m

=================================== FAILURES ===================================
[31m[1m_________________ test_loop_result_carries_every_step_product __________________[0m
[1m[31mtests/integration/test_v0_loop.py[0m:281: in test_loop_result_carries_every_step_product
    [0mresult = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)[90m[39;49;00m
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^[90m[39;49;00m
[1m[31msrc/ece/v0/loop.py[0m:163: in run_v0_loop
    [0m[94mreturn[39;49;00m _run_demo_loop_impl([90m[39;49;00m
[1m[31msrc/ece/v0/loop.py[0m:550: in _run_demo_loop_impl
    [0m_assert_loop_closed([90m[39;49;00m
[1m[31msrc/ece/v0/loop.py[0m:214: in _assert_loop_closed
    [0m[94mraise[39;49;00m [96mRuntimeError[39;49;00m([90m[39;49;00m
[1m[31mE   RuntimeError: loop did not close: re-read review_status='pending' != decision_value='review_required'[0m
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_v0_loop.py::[1mtest_loop_result_carries_every_step_product[0m - RuntimeError: loop did not close: re-read review_status='pending' != decisi...
[31m============================== [31m[1m1 failed[0m[31m in 0.65s[0m[31m ===============================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_v0_loop.py [32m.[0m[32m                                      [100%][0m

[32m============================== [32m[1m1 passed[0m[32m in 0.61s[0m[32m ===============================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`62390b0d`)
