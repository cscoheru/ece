"""MCP (Model Context Protocol) tool layer for ECE.

Per TASKS.md S4.5:
- 4 tools: search / get_record / create_task / send_message
- Last 2 are PREVIEW ONLY (per ADR-004: /actions/execute disabled in v0)
- Every tool call enforced through auth.check_user_permission (no bypass)

Claude Code integration:
    claude mcp add ece-context -- python -m ece.mcp.server
"""
