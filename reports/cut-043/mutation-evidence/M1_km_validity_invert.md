# cut-043 Mutation Anchor M1 — km_validity_invert

**Target**: `src/ece/domain_packs/knowledge/agent/v0_rules.py`
**Test**: `tests/integration/test_knowledge_boundary.py::test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable]`
**Date**: 2026-09-22

## Rationale

Flipping in_window inverts the validity condition. The answerable case (KM-POL-001 + alice + today=2026-09-22) must then fail because validity now reports passed=False.

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_knowledge_boundary.py [31mF[0m[31m                           [100%][0m

=================================== FAILURES ===================================
[31m[1m___ test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable] ____[0m
[1m[31mtests/integration/test_knowledge_boundary.py[0m:255: in test_knowledge_boundary_truth_table
    [0m[94massert[39;49;00m decision_value == expected_value, ([90m[39;49;00m
[1m[31mE   AssertionError: policy_id=KM-POL-001 user_id=km-alice: decision_value='needs_valid_policy' != expected='answerable'[0m
[1m[31mE   assert 'needs_valid_policy' == 'answerable'[0m
[1m[31mE     [0m
[1m[31mE     [0m[91m- answerable[39;49;00m[90m[39;49;00m[0m
[1m[31mE     [92m+ needs_valid_policy[39;49;00m[90m[39;49;00m[0m
[33m=============================== warnings summary ===============================[0m
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_knowledge_boundary.py::[1mtest_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable][0m - AssertionError: policy_id=KM-POL-001 user_id=km-alice: decision_value='need...
[31m========================= [31m[1m1 failed[0m, [33m1 warning[0m[31m in 0.69s[0m[31m =========================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_knowledge_boundary.py [32m.[0m[33m                           [100%][0m

[33m=============================== warnings summary ===============================[0m
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[33m========================= [32m1 passed[0m, [33m[1m1 warning[0m[33m in 0.47s[0m[33m =========================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`427791ad`)
