"""Pytest session-level configuration.

cut-043R2 R6-B2 — pin ECE_SERVER_TODAY_ANCHOR so test results do not drift
with calendar time. The server-side anchor governs policy validity windows
(KM-POL-001 valid_to=2026-12-31, KM-POL-002 valid_to=2024-12-31,
KM-POL-003 valid_to=2026-12-31). Without pinning, KM-POL-001 / KM-POL-003
would naturally transition to "expired" once wall-clock crosses 2027-01-01
and Codex reproducible verification (e.g. `date.today() == 2027-01-01`) would
turn R5-B2 happy-path tests red.

cut-043R3 R7-B1 — the anchor is now FORCE-set, not setdefault. Codex R7
reproduced that `ECE_SERVER_TODAY_ANCHOR=2027-01-01 pytest` overrode the
conftest pin (because setdefault respects existing values), allowing answerable
tests to fail. The fix: unconditional assignment so the conftest always wins,
regardless of how pytest was invoked. Tests that genuinely need a different
anchor must use `monkeypatch.setenv(...)` inside the test (which restores on
teardown and does not leak to sibling tests).

Anchor choice: 2026-09-22 matches `cut-043` closure date + KM fixture TODAY,
so all current truth-table expectations stay valid AND there is meaningful
headroom on either side of policy valid_to (KM-POL-002 expired 2024-12-31;
KM-POL-001/003 still valid until 2026-12-31).

The anchor is set as a module-level `os.environ` mutation BEFORE any test
collection imports `ece.main` / `ece.demo.api` (where the env var is read at
request time, not at module load — so fixture-time mutation is safe).
"""
from __future__ import annotations

import os

# R7-B1 — FORCE the anchor (NOT setdefault). External `ECE_SERVER_TODAY_ANCHOR`
# is overwritten by the conftest so tests are immune to caller-side drift.
# Module-level os.environ mutation is intentional and documented; pytest
# auto-discovers conftest.py at session start and runs this assignment before
# importing any test module.
os.environ["ECE_SERVER_TODAY_ANCHOR"] = "2026-09-22"