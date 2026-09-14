"""S1.1 — CsvConnector unit tests (no docker needed)."""
from __future__ import annotations

import csv
from pathlib import Path

from ece.connectors.csv import CsvConnector


def test_csv_connector_happy_path(tmp_path: Path) -> None:
    f = tmp_path / "suppliers.csv"
    with f.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({"id": "SUP001", "name": "无限极"})
    c = CsvConnector(path=f)
    c.connect()
    schema = c.discover_schema()
    assert schema == {"id": "string", "name": "string"}
    rows = c.fetch()
    assert len(rows) == 1
    assert rows[0]["id"] == "SUP001"
    assert c.normalize(rows[0]) == {"id": "SUP001", "name": "无限极"}


def test_csv_connector_empty_row_skipped(tmp_path: Path) -> None:
    f = tmp_path / "with_blank.csv"
    with f.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["id", "name"])
        writer.writeheader()
        writer.writerow({"id": "SUP001", "name": "X"})
        writer.writerow({"id": "", "name": ""})  # entirely blank
    c = CsvConnector(path=f)
    rows = c.fetch()
    assert c.normalize(rows[0]) is not None
    assert c.normalize(rows[1]) is None  # blank row → skip


def test_csv_connector_missing_file_raises() -> None:
    c = CsvConnector(path=Path("/nonexistent/file.csv"))
    try:
        c.connect()
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
