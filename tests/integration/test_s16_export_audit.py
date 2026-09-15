"""Sprint 16 v0.2 — enhanced audit export tests (cut-030).

Per ECE/CLAUDE.md 私有化 acceptance + v0.2 hardening: compliance-
friendly audit log export with --org, --until, --format csv options.

Builds on cut-017 export_audit.py script:
- --org: filter by org_id (cut-019 multi-tenant)
- --until: date range upper bound (paired with --since)
- --format csv: CSV output for spreadsheet / SIEM ingestion
- schema_version=2 in JSON output
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ece.context.assembly import assemble_context
from ece.db import get_engine

USER_A = "demo-export-alice"
USER_B = "demo-export-bob"
ORG_A = "org_export_a"
ORG_B = "org_export_b"


@pytest.fixture(autouse=True)
def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ECE_USER_ORGS", f"{USER_A}:{ORG_A};{USER_B}:{ORG_B}")


@pytest.fixture
def seed_traces() -> None:
    """Seed 2 traces: USER_A (org_a) + USER_B (org_b)."""
    engine = get_engine()
    assemble_context(
        engine=engine,
        user_ref=USER_A,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_EXPORT_A"}],
    )
    assemble_context(
        engine=engine,
        user_ref=USER_B,
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_EXPORT_B"}],
    )


def _run_export(args: list[str]) -> tuple[int, str, str]:
    """Run export_audit.py with given args, return (exit, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "scripts/export_audit.py", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent,
    )
    return result.returncode, result.stdout, result.stderr


def test_export_json_basic(seed_traces: None, tmp_path: Path) -> None:
    """export_audit.py outputs valid JSON with metadata."""
    out = tmp_path / "audit.json"
    exit_code, stdout, stderr = _run_export(["--output", str(out)])
    assert exit_code == 0, stderr
    assert "Exported" in stdout
    data = json.loads(out.read_text())
    assert data["schema_version"] == 3  # cut-033 bumped to 3
    assert "exported_at" in data
    assert "requests" in data


def test_export_json_with_user_filter(seed_traces: None, tmp_path: Path) -> None:
    """--user filters requests by user_ref."""
    out = tmp_path / "audit.json"
    exit_code, _, _ = _run_export(["--output", str(out), "--user", USER_A])
    assert exit_code == 0
    data = json.loads(out.read_text())
    for r in data["requests"]:
        assert r["user_ref"] == USER_A


def test_export_json_with_org_filter(seed_traces: None, tmp_path: Path) -> None:
    """--org filters requests by org_id (cut-019 multi-tenant)."""
    out = tmp_path / "audit.json"
    exit_code, _, _ = _run_export(["--output", str(out), "--org", ORG_A])
    assert exit_code == 0
    data = json.loads(out.read_text())
    for r in data["requests"]:
        assert r["org_id"] == ORG_A


def test_export_json_org_filter_includes_org_id_field(
    seed_traces: None, tmp_path: Path
) -> None:
    """JSON output includes org_id column (cut-019 schema)."""
    out = tmp_path / "audit.json"
    exit_code, _, _ = _run_export(["--output", str(out), "--user", USER_A])
    assert exit_code == 0
    data = json.loads(out.read_text())
    assert len(data["requests"]) >= 1
    r = data["requests"][0]
    assert "org_id" in r
    assert r["org_id"] == ORG_A


def test_export_json_with_since_and_until(seed_traces: None, tmp_path: Path) -> None:
    """--since and --until define date range filter."""
    out = tmp_path / "audit.json"
    today = "2026-09-15"
    tomorrow = "2026-09-16"
    # Since=today → only today's records
    exit_code, _, _ = _run_export(
        ["--output", str(out), "--since", today, "--until", tomorrow]
    )
    assert exit_code == 0
    data = json.loads(out.read_text())
    # All returned records should be within [today, tomorrow]
    for r in data["requests"]:
        assert today <= r["created_at"][:10] <= tomorrow


def test_export_csv_format(seed_traces: None, tmp_path: Path) -> None:
    """--format csv outputs valid CSV file."""
    exit_code, _, _ = _run_export(
        ["--output", str(tmp_path / "audit.csv"), "--format", "csv"]
    )
    assert exit_code == 0
    with (tmp_path / "audit.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) >= 2
    # Verify CSV columns include org_id
    assert reader.fieldnames is not None
    assert "org_id" in reader.fieldnames
    assert "request_id" in reader.fieldnames


def test_export_csv_with_org_filter(seed_traces: None, tmp_path: Path) -> None:
    """--format csv + --org works for compliance export."""
    exit_code, _, _ = _run_export(
        [
            "--output",
            str(tmp_path / "audit.csv"),
            "--format",
            "csv",
            "--org",
            ORG_A,
        ]
    )
    assert exit_code == 0
    with (tmp_path / "audit.csv").open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for r in rows:
        assert r["org_id"] == ORG_A


def test_export_combined_filters(seed_traces: None, tmp_path: Path) -> None:
    """Combined --user + --org + --since filters compose with AND."""
    out = tmp_path / "audit.json"
    exit_code, _, _ = _run_export(
        [
            "--output",
            str(out),
            "--user",
            USER_A,
            "--org",
            ORG_A,
        ]
    )
    assert exit_code == 0
    data = json.loads(out.read_text())
    for r in data["requests"]:
        assert r["user_ref"] == USER_A
        assert r["org_id"] == ORG_A


def test_export_filter_metadata_recorded(seed_traces: None, tmp_path: Path) -> None:
    """JSON output records applied filters in 'filter' field for compliance."""
    out = tmp_path / "audit.json"
    exit_code, _, _ = _run_export(
        ["--output", str(out), "--user", USER_A, "--org", ORG_A]
    )
    assert exit_code == 0
    data = json.loads(out.read_text())
    assert data["filter"]["user"] == USER_A
    assert data["filter"]["org"] == ORG_A
