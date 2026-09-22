# cut-043 Mutation Anchor M1 — km_validity_invert

**Target**: `src/ece/domain_packs/knowledge/agent/v0_rules.py`
**Test**: `tests/integration/test_knowledge_boundary.py::test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable]`
**Date**: 2026-09-22

## Rationale

Flipping in_window inverts the validity condition. The answerable case (KM-POL-001 + alice + today=2026-09-22) must then fail because validity now reports passed=False.

## RED (mutation applied)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_knowledge_boundary.py F                           [100%]

=================================== FAILURES ===================================
___ test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable] ____
tests/integration/test_knowledge_boundary.py:255: in test_knowledge_boundary_truth_table
    assert decision_value == expected_value, (
E   AssertionError: policy_id=KM-POL-001 user_id=km-alice: decision_value='needs_valid_policy' != expected='answerable'
E   assert 'needs_valid_policy' == 'answerable'
E     
E     - answerable
E     + needs_valid_policy
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/integration/test_knowledge_boundary.py::test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable]
========================= 1 failed, 1 warning in 0.63s =========================

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
============================= test session starts ==============================
collected 1 item

tests/integration/test_knowledge_boundary.py .                           [100%]

=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
========================= 1 passed, 1 warning in 0.47s =========================

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`427791ad`)
