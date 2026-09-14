"""S1.1 -- CSV Connector.

Reads CSV files from data/source/{connector_type}/.
Used by make seed for ingesting suppliers / products / contracts.

Per ece/TASKS.md S1.1 + DATA_MODEL.md 1: csv connector produces raw records
that map to entities (entity_type=supplier/product/etc).
"""

from __future__ import annotations

import csv
from pathlib import Path

from ece.connectors import Connector


class CsvConnector(Connector):
    """CSV file -> list of dicts (header row is field names)."""

    connector_type = "csv:generic"

    def __init__(self, path: Path, delimiter: str = ","):
        self.path = Path(path)
        self.delimiter = delimiter

    def connect(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"CSV connector: file not found: {self.path}")

    def discover_schema(self) -> dict[str, str]:
        self.connect()
        with self.path.open(encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        return {col: "string" for col in header}

    def fetch(self) -> list[dict[str, str]]:
        self.connect()
        with self.path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=self.delimiter)
            return list(reader)

    def normalize(self, raw: dict[str, str]) -> dict[str, str] | None:
        # Strip whitespace; skip rows that are entirely empty after stripping
        cleaned = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        if not any(cleaned.values()):
            return None  # empty row -> skip
        return cleaned

    def close(self) -> None:
        return None  # file already closed by context manager
