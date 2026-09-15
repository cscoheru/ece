# Cut-020 Report — real perf bench + multi-tenant verification

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-020 |
| Date | 2026-09-15 |
| Sprint | Sprint 7 v0.2 |
| Scope | real perf bench + E6 scale 200 + multi-tenant verification |
| Author | Claude Fable 5 |
| Commit | `22c2149` |
| Branch | `main` |
| Test delta | 175 → 184 (+9) |
| Pushed | `4c6544a..22c2149 main -> main` |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `scripts/bench_multi_tenant.py` | 200-query multi-tenant perf bench + cross-org denial verification |
| `scripts/bench_e6_real_llm_multi_tenant.sh` | v0.2 cut-over gate (E6 ≥80% + multi-tenant bench) |
| `docs/v0.2-deploy.md` | v0.2 deployment guide (multi-tenant + perf bench) |
| `tests/integration/test_s7_multi_tenant_bench.py` | 9 tests for bench pure logic + cross-org denial |

### 2.2 Key script signatures

**bench_multi_tenant.py**:
- `bench_assembly(n=200) → (metrics, bool)`: per-org p50/p95/p99 latency, SLA p95<1500ms
- `bench_cross_org_denial() → (metrics, bool)`: 100% denial rate required
- `_percentile(sorted_values, pct)`: linear interpolation helper (testable)
- CLI: `--n 200 --base-url URL --skip-cross-org`

**bench_e6_real_llm_multi_tenant.sh**:
- Combined gate: `run_e6_agent.py` (≥80%) + `bench_multi_tenant.py` (perf + denial)
- Required env: `ECE_LLM_BASE_URL`, `ECE_LLM_API_KEY`, `ECE_LLM_MODEL`, `ECE_USER_ORGS`
- Exit codes: `0` = all gates pass, `1` = blocked

### 2.3 Per-org SLA acceptance

| Metric | Org A target | Org B target |
|---|---|---|
| p50 latency | < 750ms | < 750ms |
| p95 latency | **< 1500ms** | **< 1500ms** (ADR-009 SLA) |
| p99 latency | < 2200ms | < 2200ms |
| Cross-org denial | 100% | 100% |

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 96 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 184 passed, 6 skipped, 1 warning in 22.71s (was 175; +9 bench tests)
make check-api-docs            → OK - 14 routes registered
```

Test breakdown (cut-020 adds 9):
- 4 unit tests for `_percentile` (median / p95 / empty / single)
- 3 unit tests for `check_org_access` (cross-org / required / disabled)
- 1 integration test: `bench_cross_org_denial` reports 100% denial
- 1 integration test: distinct org_ids recorded per user

## 4. Commit hash

- HEAD: `22c2149 feat(multi-tenant): perf bench + cross-org denial verification (cut-020)`
- Pushed: `4c6544a..22c2149 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 Perf bench uses real PR lookups (no synthetic data)

Unlike many benchmarks that use synthetic data, `bench_multi_tenant.py`
queries the seeded `entities` table for `purchase_request` rows. This
ensures the bench exercises real Postgres indexes (including the new
`idx_ctx_req_org` from migration 0007).

For `N=200`, requires ≥50 seeded PRs (`make seed` provides 100+).

### 5.2 mypy excludes scripts/ directory

`scripts/bench_multi_tenant.py` is not in mypy's check path
(`uv run mypy src tests` only). Reason: the script uses
`scripts.bench_multi_tenant` module-style import in tests, which
conflicts with mypy's default module resolution. This pattern matches
the convention for scripts in `scripts/` (other scripts like
`run_e6_agent.py` are also not in mypy path).

If full mypy coverage is needed, refactor bench helpers into
`src/ece/perf/bench.py` and re-export from the script.

### 5.3 Cross-org denial uses 3-attempt pattern per trace

For each assembled trace, the bench script attempts 3 access patterns:
1. No X-Org-Id (should be blocked: `org_id_required`)
2. Wrong X-Org-Id (should be blocked: `org_mismatch`)
3. Correct X-Org-Id (control case, allowed)

The first 2 count toward denial rate; the third is a control to verify
the bench isn't trivially passing (e.g., a bug that blocks ALL access
would still pass if we only counted cross-org attempts).

### 5.4 E6 scale up to 200 cases is a separate concern

The bench script does NOT regenerate the E6 dataset. The existing
`data/eval/e6_agent.json` (cut-014 had 20 cases, cut-015b may have
scaled) is used as-is. To scale E6 to 200 cases, run
`scripts/gen_eval_datasets.py` separately (out of cut-020 scope).

## 6. Lessons

### 6.1 Linear interpolation vs statistics.quantiles for percentile

`statistics.quantiles(values, n=20)[18]` returns the 95th percentile but
uses a different algorithm than numpy.percentile. The custom
`_percentile` function (linear interpolation on the sorted array) matches
numpy behavior, which the test `test_percentile_p95` validates (94 ≤ p95
≤ 96 for N=100). Stick with one approach across the codebase for
consistency.

### 6.2 ruff B007 (unused loop variable)

`for tid in traces:` where `tid` isn't used in the loop body triggers
B007. Two fixes: (a) rename to `_tid` (underscore prefix tells ruff
it's intentionally unused), or (b) actually use `tid`. We chose (a)
since the iteration is for index/range semantics, not the value.

### 6.3 mypy + script imports in tests cause module name collisions

When a test does `from scripts.bench_multi_tenant import X` and the
script lives at `scripts/bench_multi_tenant.py`, mypy sees the file as
both `scripts.bench_multi_tenant` (package-style) and `bench_multi_tenant`
(root-style), causing "Source file found twice under different module
names" errors. Two resolutions:
- Exclude `scripts/` from mypy (current approach, simplest)
- Add `scripts/__init__.py` and use `--explicit-package-bases`

Existing scripts like `run_e6_agent.py` aren't imported by tests, so
they avoid the issue. Our new bench script DOES need to be imported
(tests use its helpers), hence the scripts/ exclusion.

### 6.4 ECE_USER_ORGS env mutation hygiene in tests

The bench script mutates `os.environ["ECE_USER_ORGS"]` and restores it
in a finally block. Tests must follow the same `saved = os.environ.get(KEY)`
pattern to avoid leaking state between tests. Two consecutive tests
both setting `ECE_USER_ORGS` could leak if one panics before finally.

## 7. Cut-021+ preview

cut-021 scope (next likely cut): **cross-org delegation** — extend
`X-Delegation-Token` to grant cross-ORG access for managers / auditors.

Possible design:
- `ECE_DELEGATION_TOKENS="manager:org_a,org_b;auditor:*"` — token
  bearer can access any user in listed orgs
- Per-resource scope: token bearer can access specific trace by ID
  (requires per-trace ACL or token-trace mapping)

Acceptance:
- Cross-org delegation tests (manager views org_a + org_b traces)
- Per-resource scope tests (auditor can view only specific request_id)
- All 5/5 discipline green

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>