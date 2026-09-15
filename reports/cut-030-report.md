# Cut-030 Report — audit log export (compliance)

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-030 |
| Date | 2026-09-15 |
| Sprint | Sprint 16 v0.2 |
| Scope | enhanced `scripts/export_audit.py` for compliance |
| Author | Claude Fable 5 |
| Commit | `d4f0659` |
| Branch | `main` |
| Test delta | 289 → 298 (+9) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s16_export_audit.py` | 9 tests covering new flags |

### 2.2 Files modified

| File | Change |
|---|---|
| `scripts/export_audit.py` | Added `--org`, `--until`, `--format csv` flags; schema_version=2; filter metadata |

### 2.3 New flags

| Flag | Effect |
|---|---|
| `--org ORG_ID` | Filter by org_id (cut-019 multi-tenant) |
| `--until YYYY-MM-DD` | Date range upper bound (paired with --since) |
| `--format {json,csv}` | Output format (default json) |

### 2.4 Use cases

- **Internal audit**: filter by user + org + date range
- **External compliance**: --format csv for SIEM ingestion
- **Multi-tenant export**: --org org_a for single-org reports
- **Quarterly review**: --since YYYY-MM-01 --until YYYY-MM-30

### 2.5 Schema version

JSON output includes `schema_version: 2`. v1 (cut-017) didn't have
`org_id` field. v2 (cut-030) adds:
- `org_id` field on each request
- `filter` field with all applied filters
- CSV format option (separate file, same fields)

Forward-compat: future cuts bump schema_version, clients can detect
and adapt.

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 109 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 298 passed, 6 skipped, 2 warnings in 42.18s (was 289; +9 export tests)
make check-api-docs            → OK - 14 routes registered
```

## 4. Commit hash

- HEAD: `d4f0659 feat(audit-export): --org, --until, --format csv for compliance (cut-030)`
- Pushed: `1141fda..d4f0659 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 CSV items field is JSON-encoded string

CSV format flattens the nested `items` array into a single cell with
JSON-encoded value. This preserves structure while keeping CSV simple
(1 row per request).

Trade-off: spreadsheet users see JSON in cells; SIEM parsers need to
JSON-parse each cell. Both workflows supported.

Alternative: 1 row per item (request_id + item_seq + item fields).
Cleaner for item-level analysis but loses request-level metadata.
cut-031+ could add `--format items-csv` if needed.

### 5.2 Schema versioning for client compat

`schema_version: 2` in JSON output is a forward-compat signal.
Clients (audit dashboards, SIEM tools) check this version and adapt
parsing logic. Avoids silent breakage when fields are added.

### 5.3 Filter metadata recorded for compliance audit

`filter` field in JSON records all applied filters at export time.
For compliance reviews, this proves which subset was exported, when,
and by whom (when combined with audit logs of script invocation).

## 6. Lessons

### 6.1 Subprocess.run for testing CLI scripts

`_run_export` helper uses `subprocess.run([sys.executable, ...])` to
test the CLI as a real user would. Catches:
- argparse errors (unknown flag)
- Path issues (relative vs absolute)
- stdout/stderr separation
- Exit codes

Faster than mocking argparse; tests the actual user-facing behavior.

### 6.2 mypy: Sequence[str] | None from csv.DictReader.fieldnames

`DictReader.fieldnames` is typed as `Sequence[str] | None`. mypy
requires narrowing None before `in` check.

**Fix**: `assert reader.fieldnames is not None; assert "col" in reader.fieldnames`

### 6.3 W0612 (unused variable) from copy-paste

`test_export_json_with_since_and_until` had `yesterday` defined but
unused. ruff --fix can't remove unused variables (unsafe). Manual fix.

**Lesson**: review copy-pasted test code carefully; unused locals
trip ruff B007/W0612.

### 6.4 sub-second test execution via tmp_path

`tmp_path` fixture (pytest built-in) creates per-test tempdir.
Combined with subprocess.run, tests are isolated and parallel-safe.

## 7. Cumulative v0.2 stats

| Cut | Feature | Tests | Cumulative |
|---|---|---|---|
| cut-018b | multi-user delegation | +10 | 169 |
| cut-019 | multi-tenant (X-Org-Id) | +16 | 175 |
| cut-020 | multi-tenant bench | +9 | 184 |
| cut-021 | cross-org delegation | +12 | 196 |
| cut-022 | per-resource scope | +11 | 207 |
| cut-023 | rate limit | +12 | 219 |
| cut-024 | token revocation | +11 | 230 |
| cut-025 | e2e + cutover checklist | +11 | 241 |
| cut-026 | Redis-backed rate limit | +10 | 251 |
| cut-027 | JWT bearer token | +15 | 266 |
| cut-028 | user-level revocation | +11 | 277 |
| cut-029 | per-org quota tracking | +12 | 289 |
| **cut-030** | **audit export (compliance)** | **+9** | **298** |

**Total v0.2 delta**: 159 → 298 tests (+139, +87%).

**Total ECE**: 79 commits, 298 tests, all 5/5 discipline green.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>