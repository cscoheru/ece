"""Sprint 6 — Debugger UI (server-rendered HTML, no SPA per ECE/CLAUDE.md).

/debug/context/{request_id} renders the audit trace as HTML.

Private deployment mode: ECE_DEPLOYMENT_MODE=local enables /debug/*.
In production (ECE_DEPLOYMENT_MODE=production), /debug/* returns 404.

Per ECE/CLAUDE.md: server-rendered HTML, no SPA framework. Use simple
inline HTML strings (no Jinja2 template engine needed for V0).
"""
from __future__ import annotations

import html
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse

from ece.audit.trace import get_context_trace
from ece.db import get_engine

router = APIRouter(prefix="/debug", tags=["debug"])


def _is_private_deployment() -> bool:
    """True if running in local/private mode (per ECE/CLAUDE.md 私有化验收).

    ECE_DEPLOYMENT_MODE=local (default for development) enables Debugger UI.
    ECE_DEPLOYMENT_MODE=production hides Debugger UI (returns 404).
    """
    return os.environ.get("ECE_DEPLOYMENT_MODE", "local") == "local"


def _render_trace_html(trace: dict[str, Any]) -> str:
    """Render context trace as server-side HTML (no SPA framework)."""
    rows: list[str] = []
    for item in trace.get("items", []):
        seq = html.escape(str(item.get("seq", "")))
        kind = html.escape(str(item.get("item_kind", "")))
        ref = html.escape(str(item.get("ref", "")))
        decision = html.escape(str(item.get("decision", "")))
        reason = html.escape(str(item.get("reason", "") or ""))
        rows.append(
            f"<tr><td>{seq}</td><td>{kind}</td>"
            f"<td>{ref}</td><td>{decision}</td><td>{reason}</td></tr>"
        )

    counts_html = "".join(
        f'<span class="count">{html.escape(str(k))}: {v}</span>'
        for k, v in (trace.get("counts") or {}).items()
    )
    rows_html = (
        "".join(rows)
        if rows
        else '<tr><td colspan="5" style="text-align:center;color:#999">No items</td></tr>'
    )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        f"  <title>Context Trace {html.escape(trace['request_id'])}</title>\n"
        "  <style>\n"
        "    body { font-family: -apple-system, sans-serif; margin: 20px; }\n"
        "    table { border-collapse: collapse; width: 100%; }\n"
        "    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }\n"
        "    th { background: #f5f5f5; }\n"
        "    .meta { background: #f9f9f9; padding: 10px; margin-bottom: 20px; }\n"
        "    .counts { display: flex; gap: 16px; flex-wrap: wrap; }\n"
        "    .count { padding: 8px 16px; background: #e8f0fe; border-radius: 4px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>Context Trace</h1>\n"
        '  <div class="meta">\n'
        f"    <p><b>Request ID:</b> <code>{html.escape(trace['request_id'])}</code></p>\n"
        f"    <p><b>User:</b> {html.escape(trace['user_ref'])} | "
        f"<b>Intent:</b> {html.escape(trace['intent'])} | "
        f"<b>Status:</b> {html.escape(trace['status'])}</p>\n"
        f"    <p><b>Created:</b> {html.escape(trace['created_at'])} | "
        f"<b>Latency:</b> {trace.get('latency_ms', 'N/A')} ms</p>\n"
        f"    <div class='counts'>{counts_html}</div>\n"
        "  </div>\n"
        f"  <h2>Items ({len(trace.get('items', []))})</h2>\n"
        "  <table>\n"
        "    <thead>\n"
        "      <tr><th>Seq</th><th>Kind</th><th>Ref</th><th>Decision</th><th>Reason</th></tr>\n"
        "    </thead>\n"
        f"    <tbody>{rows_html}</tbody>\n"
        "  </table>\n"
        "</body>\n"
        "</html>"
    )


@router.get("/context/{request_id}", response_class=HTMLResponse)
def get_debug_context(
    request_id: str,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> str:
    """Debugger UI: server-rendered HTML trace page.

    Private deployment only (ECE_DEPLOYMENT_MODE=local). In production,
    returns 404 (UI hidden, per 私有化 acceptance).

    Per ADR-004: same permission check as /audit/context — only owner.
    """
    if not _is_private_deployment():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "debug UI not available in production",
            },
        )

    if not x_user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "bad_request",
                "message": "X-User-Id header required",
            },
        )

    trace = get_context_trace(get_engine(), request_id)
    if trace is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": f"context request {request_id} not found",
            },
        )

    if trace["user_ref"] != x_user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": "can only view own context traces",
            },
        )

    return _render_trace_html(trace)
