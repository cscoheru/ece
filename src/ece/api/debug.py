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

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from ece.api.delegation import request_id_can_access, user_can_access
from ece.api.org import check_org_access
from ece.api.quota import check_org_quota
from ece.api.rate_limit import check_rate_limit
from ece.audit.trace import get_context_trace
from ece.auth.jwt import (
    is_header_auth_fallback_allowed,
    is_jwt_mode_enabled,
    resolve_caller_user_ref,
)
from ece.db import get_engine

router = APIRouter(prefix="/debug", tags=["debug"])


def _is_private_deployment() -> bool:
    """True if running in local/private mode (per ECE/CLAUDE.md 私有化验收).

    ECE_DEPLOYMENT_MODE=local (default for development) enables Debugger UI.
    ECE_DEPLOYMENT_MODE=production hides Debugger UI (returns 404).
    """
    return os.environ.get("ECE_DEPLOYMENT_MODE", "local") == "local"


def _is_localhost(request: Request) -> bool:
    """True if request.client.host is in DEBUG_ALLOWED_HOSTS allowlist.

    Per v0.1 deployment (cut-018a): /debug/* is restricted to localhost
    only (127.0.0.1, ::1). Override via env DEBUG_ALLOWED_HOSTS
    (comma-separated). TestClient uses 'testclient' as default host (also
    allowed by default for test compatibility).

    Wildcard "*" allows all hosts (e.g., for internal proxy / load
    balancer in front of /debug/* endpoint).
    """
    client_host = request.client.host if request.client else ""
    allowed_str = os.environ.get(
        "DEBUG_ALLOWED_HOSTS",
        "127.0.0.1,::1,localhost,testclient",
    )
    allowed = set(allowed_str.split(","))
    # Wildcard "*" allows all hosts
    if "*" in allowed:
        return True
    return client_host in allowed


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
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    x_delegation_token: str | None = Header(None, alias="X-Delegation-Token"),
    x_org_id: str | None = Header(None, alias="X-Org-Id"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Debugger UI: server-rendered HTML trace page.

    Private deployment + localhost-only (per v0.1 deployment cut-018a):
    - ECE_DEPLOYMENT_MODE=production → 404 (UI hidden)
    - Non-localhost request → 403 (anti-exposure: prevent audit trace leak)
    - Override allowlist via env DEBUG_ALLOWED_HOSTS="host1,host2,..."

    Per ADR-004 (extended cut-018b): owner OR delegated user (X-Delegation-Token).
    Per cut-019 (multi-tenant): X-Org-Id must match trace.org_id.
    Per cut-022 (per-resource): token grants specific request_id access.
    Per cut-027 (JWT): Authorization: Bearer <jwt> preferred over X-User-Id.
    Per cut-036 (R36.1): JWT mode + missing/invalid Authorization → 401.

    Raises:
        401: JWT mode ON + missing/invalid Authorization (cut-036 R36.1)
        400: missing X-User-Id (legacy / JWT-disabled)
        403: caller is not the owner / non-localhost access
        404: request_id not found or production deployment mode
    """
    # cut-027: prefer JWT over X-User-Id
    resolved_user_id = resolve_caller_user_ref(authorization, x_user_id)

    if not _is_private_deployment():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "debug UI not available in production",
            },
        )

    if not _is_localhost(request):
        client_host = request.client.host if request.client else "unknown"
        raise HTTPException(
            status_code=403,
            detail={
                "code": "forbidden",
                "message": (
                    f"debug UI only available from localhost; "
                    f"got {client_host}. "
                    f"Override via env DEBUG_ALLOWED_HOSTS."
                ),
            },
        )

    if not resolved_user_id and not x_delegation_token:
        # cut-036 R36.3: JWT mode + missing/invalid Authorization → 401
        # (R36.1 mandate). Legacy / JWT-disabled still 400 for bad_request.
        if is_jwt_mode_enabled() and not is_header_auth_fallback_allowed():
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "unauthorized",
                    "message": "JWT Bearer token required (cut-036 R36.1)",
                },
                headers={"WWW-Authenticate": 'Bearer realm="ece"'},
            )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "bad_request",
                "message": "X-User-Id header or X-Delegation-Token required",
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

    # Per cut-022 (per-resource scope): token grants specific request_id access
    # independently of ownership / org checks.
    if not request_id_can_access(x_delegation_token, request_id):
        # Per ADR-004 (extended cut-018b): owner OR delegated user
        if not user_can_access(resolved_user_id, x_delegation_token, trace["user_ref"]):
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "can only view own context traces",
                },
            )

        # Per cut-019 (multi-tenant): X-Org-Id must match trace.org_id
        # cut-021: token may grant cross-org access via ECE_DELEGATION_ORG_TOKENS
        org_allowed, org_error = check_org_access(
            x_org_id, trace["org_id"], x_delegation_token
        )
        if not org_allowed:
            if org_error == "org_id_required":
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "bad_request",
                        "message": "X-Org-Id header required (multi-tenant mode)",
                    },
                )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "cross-org access denied",
                },
            )

    # Per cut-023 (org rate limit): check ECE_ORG_RATE_LIMITS for caller's org
    rate_allowed, rate_error, retry_after = check_rate_limit(x_org_id)
    if not rate_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": "debug org rate limit exceeded",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    # Per cut-029 (org quota): check ECE_ORG_QUOTAS for caller's org
    quota_allowed, quota_code, quota_retry = check_org_quota(x_org_id)
    if not quota_allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exceeded",
                "message": "debug org quota exceeded",
                "retry_after_seconds": quota_retry,
            },
            headers={"Retry-After": str(int(quota_retry) + 1)},
        )

    return _render_trace_html(trace)
