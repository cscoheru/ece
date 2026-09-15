"""Sprint 19 v0.2 — items-csv export format tests (cut-033).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: per-item
granularity CSV output for compliance / SIEM tools. 1 row per item
(denied or allowed), with request metadata as repeating columns.

Use cases:
- SIEM ingestion: per-item events for rule correlation
- Compliance: denied-item review (which resources were denied?)
- Audit trail: per-decision lineage
"""
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from ece.context.assembly import assemble_context
from ece.db import get_engine

USER_A = "demo-items-export-alice"
ORG_A = "org_items_a"


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECE_USER_ORGS", f"{USER_A}:{ORG_A}")


@pytest.fixture
def seed_traces() -> None:
    """Seed trace with multiple items."""
    engine = get_engine()
    assemble_context(
        engine=engine,
        user_ref=USER_A,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_ITEMS_1"}],
    )


def _run_export(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "scripts/export_audit.py", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    return result.returncode, result.stdout, result.stderr


def test_items_csv_basic(seed_traces: None, tmp_path: Path) -> None:
    """--format items-csv outputs valid CSV with 1 row per item."""
    exit_code, stdout, stderr = _run_export(
        ["--output", str(tmp_path / "items.csv"), "--format", "items-csv"]
    )
    assert exit_code == 0, stderr
    assert "items-csv" in stdout


def test_items_csv_columns(seed_traces: None, tmp_path: Path) -> None:
    """items-csv has expected columns including per-item fields."""
    exit_code, _, _ = _run_export(
        ["--output", str(tmp_path / "items.csv"), "--format", "items-csv"]
    )
    assert exit_code == 0
    with (tmp_path / "items.csv").open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        # Verify request + item columns present
        assert "request_id" in reader.fieldnames
        assert "item_seq" in reader.fieldnames
        assert "item_kind" in reader.fieldnames
        assert "item_ref" in reader.fieldnames
        assert "item_decision" in reader.fieldnames


def test_items_csv_per_item_rows(seed_traces: None, tmp_path: Path) -> None:
    """items-csv produces 1 row per item (not per request)."""
    exit_code, _, _ = _run_export(
        ["--output", str(tmp_path / "items.csv"), "--format", "items-csv"]
    )
    assert exit_code == 0
    with (tmp_path / "items.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # Each row has item_seq (not None/empty for valid items)
    assert len(rows) >= 1
    for row in rows:
        assert row["item_seq"] != ""
        assert row["request_id"] != ""


def test_items_csv_with_org_filter(seed_traces: None, tmp_path: Path) -> None:
    """items-csv + --org filters by org_id."""
    exit_code, _, _ = _run_export(
        [
            "--output",
            str(tmp_path / "items.csv"),
            "--format",
            "items-csv",
            "--org",
            ORG_A,
        ]
    )
    assert exit_code == 0
    with (tmp_path / "items.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        assert row["org_id"] == ORG_A


def test_items_csv_includes_request_metadata(
    seed_traces: None, tmp_path: Path
) -> None:
    """Each items-csv row includes request metadata (user_ref, intent, etc.)."""
    exit_code, _, _ = _run_export(
        [
            "--output",
            str(tmp_path / "items.csv"),
            "--format",
            "items-csv",
            "--user",
            USER_A,
        ]
    )
    assert exit_code == 0
    with (tmp_path / "items.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) >= 1
    row = rows[0]
    assert row["user_ref"] == USER_A
    assert row["intent"] == "evaluate_purchase_request"


def test_items_csv_vs_csv_different_row_count(
    seed_traces: None, tmp_path: Path
) -> None:
    """items-csv has >= rows than csv (1 per item vs 1 per request)."""
    exit_csv, _, _ = _run_export(
        ["--output", str(tmp_path / "audit.csv"), "--format", "csv"]
    )
    exit_items, _, _ = _run_export(
        ["--output", str(tmp_path / "items.csv"), "--format", "items-csv"]
    )
    assert exit_csv == 0
    assert exit_items == 0
    with (tmp_path / "audit.csv").open() as f:
        csv_rows = list(csv.DictReader(f))
    with (tmp_path / "items.csv").open() as f:
        items_rows = list(csv.DictReader(f))
    # items-csv has 1 row per item (≥1 row per request)
    assert len(items_rows) >= len(csv_rows)
