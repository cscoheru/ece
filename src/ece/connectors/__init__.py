"""S1.1 -- Connector Interface contract.

Per ece/docs/ARCHITECTURE.md 1 + ece/TASKS.md Sprint 1 S1.1:
- Connector 是数据源接入的唯一通道
- 5 步契约: connect / discover_schema / fetch / normalize / sync (close 可选)
- Domain 层只依赖 Connector 接口(ADR-001)
- v0 三实现: csv / json / docs(本地文件目录)
- 脏数据可跳过但不中断整批(skip 计数落 ingestion_runs.stats)

注: close() 不是抽象方法(子类可选覆盖),B027 修复.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    """Base interface for all data source connectors.

    Lifecycle: connect() -> discover_schema() -> fetch() -> normalize() -> sync()
    close() 是可选 lifecycle 方法(子类按需覆盖).
    Implementations may short-circuit (e.g. csv doesn't need connect()).
    """

    connector_type: str = ""  # 子类覆盖: "csv:suppliers" / "json:prs" / "docs:folder"

    @abstractmethod
    def connect(self) -> None:
        """Establish connection / open resource. Raise on fatal failure."""

    @abstractmethod
    def discover_schema(self) -> dict[str, Any]:
        """Return inferred schema: {field_name: type_str} or {field_name: dict(...)}."""

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Return raw records (list of dicts). Skips are tracked by caller, not here."""

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Convert raw record to canonical form for ingestion pipeline.

        Return None to signal "skip this record" (e.g. validation failure).
        Implementations must not raise on individual bad records.
        """

    # close() 由子类按需 override(无基类默认 -> 避免 B027)
