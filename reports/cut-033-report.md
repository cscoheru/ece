# Cut-033 Report — items-csv export (per-resource)

## 1. Metadata

| 字段 | 值 |
|---|---|
| Cut ID | cut-033 |
| Date | 2026-09-15 |
| Sprint | Sprint 19 v0.2 |
| Scope | `--format items-csv` (1 row per item) |
| Author | Claude Fable 5 |
| Commit | `f5f3e41` |
| Branch | `main` |
| Test delta | 315 → 321 (+6) |

## 2. Changes

### 2.1 Files added

| File | Purpose |
|---|---|
| `tests/integration/test_s19_items_csv.py` | 6 tests for items-csv format |

### 2.2 Files modified

| File | Change |
|---|---|
| `scripts/export_audit.py` | Added `_write_items_csv()`; `--format items-csv` option; schema_version=3 |

### 2.3 Format spec

```
--format items-csv  → 1 row per context_item (denied or allowed)

Columns:
  request_id, user_ref, org_id, intent, status, latency_ms, created_at,
  item_seq, item_kind, item_ref, item_decision, item_reason, item_source

Per-request metadata repeated across item rows (denormalized for
spreadsheet/SIEM ingestion).
```

Schema version: 3 (cut-033 adds items-csv; cut-030 was 2).

## 3. Verification (5 项 discipline)

```
uv run ruff check .           → All checks passed
uv run mypy src tests          → Success: no issues found in 112 source files
uv run lint-imports            → Domain pack isolation KEPT + Engine core isolation KEPT (2 contracts)
make test                      → 321 passed, 6 skipped, 2 warnings in 50.21s (was 315; +6 items-csv tests)
```

## 4. Commit hash

- HEAD: `f5f3e41 feat(audit-export): --format items-csv for per-item granularity (cut-033)`
- Pushed: `40925e7..f5f3e41 main -> main` (via Clash proxy)

## 5. Non-typical items

### 5.1 items-csv vs csv trade-off

| Format | Rows | Per-row content |
|---|---|---|
| csv | 1 per request | request metadata + JSON-encoded `items` field |
| items-csv | 1 per item | request metadata + item fields (denormalized) |

SIEM tools usually want per-item granularity (one event per decision).
Spreadsheets prefer 1 row per request (easier filtering). Both formats
supported.

### 5.2 Schema version semantics

`schema_version: 3` indicates forward-compat signal. Future cuts
bump the version when adding fields. Clients can check version and
adapt parsing.

v1 (cut-017): basic JSON
v2 (cut-030): org_id field + csv format
v3 (cut-033): items-csv format

### 5.3 Test isolation requires user filter

The DB is shared across tests. When items-csv exports ALL traces
(no filter), it picks up old test traces too. Tests that check
specific user_ref must use `--user USER_A` to filter.

Originally `test_items_csv_includes_request_metadata` failed
because it found old `demo-user-procurement` trace from another test.
Fix: add `--user` filter to scope to current test's trace.

## 6. Lessons

### 6.1 Denormalize for export formats

Items-csv repeats request metadata (user_ref, intent, status) on
every row. This is denormalized but enables:
- Spreadsheet sorting/filtering without JOINs
- SIEM ingestion as flat events
- Per-row independent processing

Trade-off: larger file size. For 1000 requests with 10 items each:
csv = 1000 rows, items-csv = 10000 rows. Acceptable for compliance
exports.

### 6.2 Schema versioning: when to bump

Bump schema_version when:
- New field added (forward-compat signal)
- New format option (cut-030 csv, cut-033 items-csv)
- Breaking change to existing fields

Don't bump for internal changes (refactor without API change).

### 6.3 tests/integration/test_s16 needed update

When cut-033 bumped schema_version from 2 → 3, test_s16's
`test_export_json_basic` (asserting schema_version == 2) failed.
This is expected — tests must track current schema_version.

**Lesson**: any cut that bumps schema_version needs to update all
existing tests asserting on the version.

---

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>