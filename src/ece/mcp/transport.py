"""MCP transport entry point for ECE (per TASKS.md S4.5 DoD).

Default transport is stdio (matches `claude mcp add ece-context` integration).
For SSE/streamable-http transport, extend this entry point (not yet implemented
in v0 per ADR-004 + ECE/CLAUDE.md iron rule 3).
"""
from __future__ import annotations

from ece.mcp.server import mcp


def main() -> None:
    """Explicit stdio entry; same effect as `python -m ece.mcp.server`."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
