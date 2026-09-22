# Mutation Anchor M4 — evaluated_conditions_inject_nondeterministic_amount

**Target**: `src/ece/domain_packs/procurement/agent/v0_rules.py`
**Test**: `tests/integration/test_v0_specialized.py::test_determinism_under_loop_runs_byte_equal_decision_and_conditions`
**Date**: 2026-09-22

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_v0_specialized.py [31mF[0m[31m                               [100%][0m

=================================== FAILURES ===================================
[31m[1m_____ test_determinism_under_loop_runs_byte_equal_decision_and_conditions ______[0m
[1m[31mtests/integration/test_v0_specialized.py[0m:123: in test_determinism_under_loop_runs_byte_equal_decision_and_conditions
    [0m[94massert[39;49;00m [96mlen[39;49;00m([96mset[39;49;00m(conditions_dump)) == [94m1[39;49;00m, ([90m[39;49;00m
[1m[31mE   AssertionError: evaluated_conditions must be byte-equal across N=10 runs; got 10 distinct shape(s)[0m
[1m[31mE   assert 10 == 1[0m
[1m[31mE    +  where 10 = len({'[{"actual":1280012,"claim":"\\u91d1\\u989d 1,280,012 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...})[0m
[1m[31mE    +    where {'[{"actual":1280012,"claim":"\\u91d1\\u989d 1,280,012 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...} = set(['[{"actual":1280810,"claim":"\\u91d1\\u989d 1,280,810 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...])[0m
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_v0_specialized.py::[1mtest_determinism_under_loop_runs_byte_equal_decision_and_conditions[0m - AssertionError: evaluated_conditions must be byte-equal across N=10 runs; g...
[31m============================== [31m[1m1 failed[0m[31m in 0.93s[0m[31m ===============================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_v0_specialized.py [32m.[0m[32m                               [100%][0m

[32m============================== [32m[1m1 passed[0m[32m in 0.88s[0m[32m ===============================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`64ceae9e`)
