# cut-044 Mutation Anchor M2 — comp_coverage_issubset_to_isdisjoint

**Target**: `src/ece/domain_packs/compliance/agent/v0_rules.py`
**Test**: `tests/integration/test_compliance_boundary.py::test_compliance_boundary_truth_table[ctl001_alice_full_coverage_sufficient]`
**Date**: 2026-09-22

## Rationale

Replacing issubset with isdisjoint inverts the coverage gate: an empty intersection now passes, and any overlap fails. For COMP-CTL-001 (required={erp,hr,finance} all covered) the intersection is the full required set, so coverage now fails. Combined with count=3 passing, decision_value flips to gap_list.

## RED (mutation applied)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_compliance_boundary.py [31mF[0m[31m                          [100%][0m

=================================== FAILURES ===================================
[31m[1m_ test_compliance_boundary_truth_table[ctl001_alice_full_coverage_sufficient] __[0m
[1m[31mtests/integration/test_compliance_boundary.py[0m:249: in test_compliance_boundary_truth_table
    [0m[94massert[39;49;00m decision_value == expected_value, ([90m[39;49;00m
[1m[31mE   AssertionError: control_id=COMP-CTL-001 user_id=comp-alice period=(2026-07-01..2026-09-30): decision_value='gap_list' != expected='evidence_package_sufficient'[0m
[1m[31mE   assert 'gap_list' == 'evidence_package_sufficient'[0m
[1m[31mE     [0m
[1m[31mE     [0m[91m- evidence_package_sufficient[39;49;00m[90m[39;49;00m[0m
[1m[31mE     [92m+ gap_list[39;49;00m[90m[39;49;00m[0m
[33m=============================== warnings summary ===============================[0m
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[36m[1m=========================== short test summary info ============================[0m
[31mFAILED[0m tests/integration/test_compliance_boundary.py::[1mtest_compliance_boundary_truth_table[ctl001_alice_full_coverage_sufficient][0m - AssertionError: control_id=COMP-CTL-001 user_id=comp-alice period=(2026-07-...
[31m========================= [31m[1m1 failed[0m, [33m1 warning[0m[31m in 0.51s[0m[31m =========================[0m

```

Exit code: 1
Marker `AssertionError` present: **True**

## GREEN (mutation reverted)

```
[1m============================= test session starts ==============================[0m
collected 1 item

tests/integration/test_compliance_boundary.py [32m.[0m[33m                          [100%][0m

[33m=============================== warnings summary ===============================[0m
.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /Users/kjonekong/projects/domainAgentECE/ece/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
[33m========================= [32m1 passed[0m, [33m[1m1 warning[0m[33m in 0.45s[0m[33m =========================[0m

```

Exit code: 0
Test passes: **True**

## Verification

- [x] RED captured: `AssertionError` in stdout = True
- [x] GREEN restored: test passes = True
- [x] File restored: pre/post md5 match = True (`ecf6eb84`)
