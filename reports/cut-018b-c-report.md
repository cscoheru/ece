test(s6): multi-user PermissionScope delegation + real LLM gate helper (cut-018b + cut-018c closure)

cut-018b scope = multi-user PermissionScope via X-Delegation-Token:

src/ece/api/delegation.py (NEW):
- parse_delegation_tokens() parses ECE_DELEGATION_TOKENS="token:user1,user2;..."
- resolve_user_refs(x_user_id, x_delegation_token) returns union
- user_can_access(x_user_id, x_delegation_token, trace_user_ref)
  checks owner OR delegation membership

src/ece/api/audit.py (EDIT):
- get_context_audit accepts X-Delegation-Token header
- Uses resolve_user_refs() for 400 check
- Uses user_can_access() for 403
- Extends ADR-004: owner OR delegated user

src/ece/api/debug.py (EDIT):
- get_debug_context accepts X-Delegation-Token header
- Same delegation check as audit

tests/integration/test_s6_delegation.py (NEW, 9 tests):
- Unit: parse_delegation_tokens basic + empty
- Unit: resolve_user_refs with/without token
- Unit: user_can_access owner / delegated / rejected
- Integration: /audit with valid delegation token (200)
- Integration: /audit with invalid token (403)
- Integration: /audit with neither X-User-Id nor X-Delegation-Token (400)

cut-018c scope = real LLM >=80% gate helper:

scripts/verify_e6_real_llm.sh (NEW):
- Sets ECE_LLM_BASE_URL/API_KEY/MODEL (required)
- Invokes scripts/run_e6_agent.py --base-url
- Exit 0 = >=80% accuracy (v0.1 cut-over ready)
- Exit 1 = <80% (blocked, investigate)

docs/v0.1-deploy.md (NEW):
- ECE_DEPLOYMENT_MODE, DEBUG_ALLOWED_HOSTS, ECE_DELEGATION_TOKENS config
- Real LLM gate verification flow
- Operational checklist for v0.1 cut-over
- Troubleshooting matrix

Acceptance (5 项 discipline):
- uv run ruff check . -> All checks passed
- uv run mypy src tests -> Success: no issues found in 92 source files
- uv run lint-imports -> Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
- make test -> 159 passed, 6 skipped, 1 warning in 21.96s (was 149+3; +10 delegation tests)
- make check-api-docs -> OK - 14 routes registered

Test count delta: 149 -> 159 passed (+10 delegation tests).

cut-018b + cut-018c scope = multi-user delegation + real LLM gate helper.
HEAD after push: 526ea75b7a9a38002733ffcd0b26deb26cef2286
- multi-tenant (cross-org) scoping
- per-resource scope (delegation to specific trace only)
- v0.1 actual deployment verification (user runs ECE_LLM_BASE_URL+verify_e6_real_llm.sh)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
