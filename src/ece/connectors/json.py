"""S1.1 — JSON Connector.

Reads JSON files (list of objects) from data/source/{connector_type}/.
Used by make seed for ingesting purchase_requests.
"""

from __future__ import annotations

import json
from pathlib import Path

from ece.connectors import Connector


class JsonConnector(Connector):
    """JSON file (list of dicts) → list of dicts."""

    connector_type = "json:generic"

    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"JSON connector: file not found: {self.path}")

    def discover_schema(self) -> dict[str, str]:
        self.connect()
        records = self._read_raw()
        if not records:
            return {}
        first = records[0]
        return {k: type(v).__name__ for k, v in first.items()}

    def fetch(self) -> list[dict[str, object]]:
        return self._read_raw()

    def normalize(self, raw: dict[str, object]) -> dict[str, object] | None:
        # JSON values already typed; just skip null-only records
        if raw is None or all(v in (None, "") for v in raw.values()):
            return None
        return raw

    def _read_raw(self) -> list[dict[str, object]]:
        with self.path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"JSON connector expects a list at top level, got {type(data)}")
        return data

    def close(self) -> None:
        return None
