"""S1.1 — Docs Connector.

Reads a folder of plain text/markdown files into Document records.
Used for ingesting policy / contract / report documents.

Per DATA_MODEL.md §3: documents has title / doc_type / file_path / classification.
Per ece/CLAUDE.md §3 "Connector 正常处理脏数据: 跳过并计数,不中断整批".
"""

from __future__ import annotations

from pathlib import Path

from ece.connectors import Connector

# 文件扩展名 → doc_type 映射
_EXT_TO_DOCTYPE = {
    ".md": "policy",
    ".txt": "report",
    ".pdf": "contract",
}


class DocsConnector(Connector):
    """Folder of files → list of {title, file_path, doc_type, classification}."""

    connector_type = "docs:folder"

    def __init__(self, folder: Path, classification: str = "department"):
        self.folder = Path(folder)
        self.classification = classification

    def connect(self) -> None:
        if not self.folder.exists():
            raise FileNotFoundError(f"Docs connector: folder not found: {self.folder}")
        if not self.folder.is_dir():
            raise NotADirectoryError(f"Docs connector: not a folder: {self.folder}")

    def discover_schema(self) -> dict[str, str]:
        return {
            "title": "string",
            "doc_type": "string",
            "file_path": "string",
            "classification": "string",
        }

    def fetch(self) -> list[dict[str, str]]:
        if not self.folder.exists():
            return []
        return [self._file_to_record(p) for p in sorted(self.folder.iterdir()) if p.is_file()]

    def normalize(self, raw: dict[str, str]) -> dict[str, str] | None:
        # Filename must have recognized extension
        if "_ext_to_doctype_placeholder" in raw:
            return None  # template guard (never triggered)
        return raw if raw.get("doc_type") != "unknown" else None  # skip unknown types

    def _file_to_record(self, path: Path) -> dict[str, str]:
        ext = path.suffix.lower()
        doc_type = _EXT_TO_DOCTYPE.get(ext, "unknown")
        return {
            "title": path.stem,  # e.g. "POL-2026-03" from "POL-2026-03.md"
            "file_path": str(path.relative_to(self.folder)) if path.is_relative_to(self.folder) else str(path),
            "doc_type": doc_type,
            "classification": self.classification,
        }

    def close(self) -> None:
        return None
