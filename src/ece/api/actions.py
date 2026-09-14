"""S4.5+ — POST /actions/preview endpoint.

Per ADR-004 + ECE/CLAUDE.md: /actions/execute v0 disabled; this endpoint
returns the same preview as MCP create_task/send_message tools.

Sprint 5+ 真实部署可启用 /actions/execute（env kill-switch off），本 endpoint
会变成实际执行入口。当前 v0 一致返回 preview only（per cut-011 §4.5
side-effecting tool preview 设计）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.mcp.tools import create_task_tool, send_message_tool

router = APIRouter(prefix="/api/v1", tags=["actions"])


class ActionsPreviewRequest(BaseModel):
    """POST /actions/preview request body (per docs/API.md §6)."""

    user_id: str = Field(
        "",
        description="X-User-Id value (header preferred; body fallback)",
    )
    action: str = Field(
        ...,
        description="action name: create_task | send_message",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="action params (title/description for create_task; to/body for send_message)",
    )


@router.post("/actions/execute")
def post_actions_execute(
    req: ActionsPreviewRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Real action execution — DISABLED in v0 (per ADR-004 + ECE/CLAUDE.md).

    Per ADR-004: /actions/execute v0 disabled (env kill-switch + route-level
    double safety). Use /actions/preview to see what would happen.

    Sprint 5+ 真实部署 can enable via env ECE_ACTIONS_EXECUTE_ENABLED=true
    (when implemented).
    """
    raise HTTPException(
        status_code=403,
        detail={
            "code": "disabled_feature",
            "message": (
                "v0: /actions/execute disabled per ADR-004; use /actions/preview "
                "for what would happen. Enable via env ECE_ACTIONS_EXECUTE_ENABLED=true "
                "in Sprint 5+ deployment."
            ),
        },
    )


@router.post("/actions/preview")
def post_actions_preview(
    req: ActionsPreviewRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Preview an action (no actual execution per ADR-004 v0).

    Per cut-011 §4.5: side-effecting actions must have preview path. This
    endpoint mirrors the MCP tools' preview response shape.
    """
    user_ref = x_user_id or req.user_id
    if not user_ref or not user_ref.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "bad_request",
                "message": "X-User-Id header or user_id body required",
            },
        )

    if req.action == "create_task":
        title = str(req.params.get("title", ""))
        description = str(req.params.get("description", ""))
        return create_task_tool(title=title, description=description)

    if req.action == "send_message":
        to = str(req.params.get("to", ""))
        body = str(req.params.get("body", ""))
        return send_message_tool(to=to, body=body)

    raise HTTPException(
        status_code=400,
        detail={
            "code": "bad_request",
            "message": f"unknown action: {req.action}; supported: create_task, send_message",
        },
    )
