# Mutation Anchor M4 — evaluated_conditions_inject_nondeterministic_amount

**Target**: `src/ece/domain_packs/procurement/agent/v0_rules.py`
**Test**: `tests/integration/test_v0_specialized.py::test_determinism_under_loop_runs_byte_equal_decision_and_conditions`
**Date**: 2026-09-22

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_v0_specialized.py F                               [100%]

=================================== FAILURES ===================================
_____ test_determinism_under_loop_runs_byte_equal_decision_and_conditions ______
tests/integration/test_v0_specialized.py:123: in test_determinism_under_loop_runs_byte_equal_decision_and_conditions
    assert len(set(conditions_dump)) == 1, (
E   AssertionError: evaluated_conditions must be byte-equal across N=10 runs; got 10 distinct shape(s)
E   assert 10 == 1
E    +  where 10 = len({'[{"actual":1280420,"claim":"\\u91d1\\u989d 1,280,420 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...})
E    +    where {'[{"actual":1280420,"claim":"\\u91d1\\u989d 1,280,420 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...} = set(['[{"actual":1280420,"claim":"\\u91d1\\u989d 1,280,420 \\u2265 1,000,000","expr":"amount >= 1000000","name":"amount_gt...ef7\\u5bb6\\u6570 1 < 3","expr":"quote_count < 3","name":"quote_count_lt_required","passed":true,"threshold":3}]', ...])
=========================== short test summary info ============================
FAILED tests/integration/test_v0_specialized.py::test_determinism_under_loop_runs_byte_equal_decision_and_conditions
============================== 1 failed in 1.28s ===============================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_v0_specialized.py .                               [100%]

============================== 1 passed in 1.17s ===============================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`64ceae9e`)
