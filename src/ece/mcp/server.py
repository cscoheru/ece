"""MCP server entry point for ECE.

Exposes 4 tools (per TASKS.md S4.5):
- search: FTS keyword search
- get_record: entity by display_id
- create_task: preview only (per ADR-004)
- send_message: preview only (per ADR-004)

Run with stdio transport (default for Claude Code integration):
    claude mcp add ece-context -- python -m ece.mcp.server

Per ADR-004: every tool call goes through auth.check_user_permission.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ece.mcp.tools import (
    create_task_tool,
    get_record_tool,
    search_tool,
    send_message_tool,
)

mcp = MCPServer("ECE Context Engine")


@mcp.tool()
def search(query: str, top_k: int = 10) -> dict:
    """FTS keyword search across ECE documents.

    Args:
        query: search query text (English/Chinese partial; zhparser may improve Chinese)
        top_k: max results (default 10)

    Returns:
        dict with items[] (ranked hits) + meta (kinds_used, total).
    """
    return search_tool(query=query, top_k=top_k)


@mcp.tool()
def get_record(user_ref: str, display_id: str) -> dict:
    """Get a single entity by display_id with PermissionScope check.

    Args:
        user_ref: X-User-Id value (e.g. "demo-user-procurement")
        display_id: entity display_id (e.g. "PR0001")

    Returns:
        dict with ref/type/name/attrs/src, OR {error: "forbidden"|"not_found"} envelope
        (per ADR-004 anti-probing).
    """
    return get_record_tool(user_ref=user_ref, display_id=display_id)


@mcp.tool()
def create_task(title: str, description: str) -> dict:
    """Preview only — no actual task creation per ADR-004.

    v0: /actions/execute is disabled; this is a preview endpoint only.

    Args:
        title: task title
        description: task description

    Returns:
        dict with preview=True and status='would_create'.
    """
    return create_task_tool(title=title, description=description)


@mcp.tool()
def send_message(to: str, body: str) -> dict:
    """Preview only — no actual message sent per ADR-004.

    v0: /actions/execute is disabled; this is a preview endpoint only.

    Args:
        to: recipient identifier
        body: message body text

    Returns:
        dict with preview=True and status='would_send'.
    """
    return send_message_tool(to=to, body=body)


if __name__ == "__main__":
    mcp.run()
