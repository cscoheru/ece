"""Engine status page — OEI-003 §4 步骤 4 (visible deliverable).

GET /engine/status       → engine snapshot (HTML)
GET /engine/status?q=... → engine snapshot + recalled docs (HTML, ECE-rendered citations)

This page is the visible deliverable for OEI-003 and the direct response to
OEI-002 VERDICT §8.4: Onyx CE's built-in UI does not render citations, so ECE
must render the recall results itself (query → recalled docs → snippet → source).
"""
from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import HTMLResponse

from ece.connectors.onyx.port import EngineError
from ece.connectors.onyx.selector import get_content_engine


router = APIRouter(prefix="/engine", tags=["engine"])


def _render_status_page(
    request: Request,
    status_dict: dict[str, Any] | None,
    degraded_reason: str | None,
    query: str | None,
    docs: list[dict[str, Any]] | None,
) -> HTMLResponse:
    """Render the engine status HTML page (with optional query + citations)."""
    title = "ECE · Engine Status"
    css = """
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem auto; max-width: 920px; color: #1a1a1a; }
    h1 { border-bottom: 2px solid #333; padding-bottom: 0.3rem; }
    h2 { margin-top: 2rem; color: #444; }
    .kv { display: grid; grid-template-columns: 200px 1fr; row-gap: 0.4rem; column-gap: 1rem; padding: 1rem; background: #f7f7f7; border-radius: 6px; }
    .kv .k { color: #666; font-weight: 600; }
    .doc { padding: 1rem; border: 1px solid #e0e0e0; border-left: 4px solid #4a90e2; border-radius: 4px; margin-bottom: 0.8rem; background: #fafbfc; }
    .doc h3 { margin: 0 0 0.4rem 0; font-size: 1.05rem; }
    .doc .meta { color: #777; font-size: 0.85rem; margin-bottom: 0.6rem; }
    .doc pre { white-space: pre-wrap; font-family: ui-monospace, "JetBrains Mono", Menlo, monospace; font-size: 0.85rem; background: #fff; padding: 0.6rem; border: 1px solid #eee; border-radius: 4px; }
    .degraded { background: #fff3cd; border: 1px solid #ffe69c; padding: 0.8rem 1rem; border-radius: 6px; color: #664d03; margin: 1rem 0; }
    form { margin: 1rem 0; padding: 1rem; background: #eef4fb; border-radius: 6px; }
    input[type=text] { padding: 0.5rem; width: 60%; font-size: 1rem; border: 1px solid #ccc; border-radius: 4px; }
    button { padding: 0.5rem 1rem; font-size: 1rem; background: #4a90e2; color: white; border: none; border-radius: 4px; cursor: pointer; }
    .footer { margin-top: 3rem; color: #888; font-size: 0.8rem; border-top: 1px solid #eee; padding-top: 1rem; }
    """

    parts: list[str] = []
    parts.append(f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{css}</style></head><body>")
    parts.append("<h1>ECE · Engine Status</h1>")
    parts.append("<p>This page renders engine state and (when given a query) ECE-rendered citations. ")
    parts.append("Built per OEI-003 §4 step 4 — the visible deliverable that addresses Onyx UI's no-citation gap.</p>")

    # Search form
    parts.append("<form method='get' action='/engine/status'>")
    parts.append("<label for='q'>Query (renders ECE citations):</label><br>")
    parts.append("<input type='text' id='q' name='q' placeholder='问题树怎么用' ")
    if query:
        parts.append(f"value='{html.escape(query)}' ")
    parts.append("/>")
    parts.append("<button type='submit'>Search</button>")
    parts.append("</form>")

    if degraded_reason:
        parts.append(f"<div class='degraded'><strong>Engine degraded:</strong> {html.escape(degraded_reason)}</div>")

    if status_dict is not None:
        parts.append("<h2>Engine Snapshot</h2>")
        parts.append("<div class='kv'>")
        for k, v in status_dict.items():
            parts.append(f"<div class='k'>{html.escape(str(k))}</div><div>{html.escape(str(v))}</div>")
        parts.append("</div>")
    else:
        parts.append("<h2>Engine Snapshot</h2>")
        parts.append("<div class='degraded'>engine_status() returned no data.</div>")

    if query is not None:
        parts.append(f"<h2>Citations for query: {html.escape(query)}</h2>")
        if docs is None:
            parts.append("<div class='degraded'>Recall failed (see degraded banner above).</div>")
        elif not docs:
            parts.append("<p>No documents recalled.</p>")
        else:
            parts.append(f"<p>{len(docs)} document(s) recalled.</p>")
            for d in docs:
                parts.append("<div class='doc'>")
                parts.append(
                    f"<h3>{html.escape(d.get('title', '(no title)'))}</h3>"
                )
                meta_bits = []
                if d.get("source_type"):
                    meta_bits.append(f"source: {d['source_type']}")
                if d.get("engine_doc_id"):
                    meta_bits.append(f"id: {d['engine_doc_id']}")
                if d.get("updated_at"):
                    meta_bits.append(f"updated: {d['updated_at']}")
                if meta_bits:
                    parts.append(f"<div class='meta'>{html.escape(' · '.join(meta_bits))}</div>")
                parts.append(f"<pre>{html.escape(d.get('snippet', ''))}</pre>")
                parts.append("</div>")

    parts.append("<div class='footer'>OEI-003 · ECE engine status page · ECE-rendered citations</div>")
    parts.append("</body></html>")
    return HTMLResponse(content="".join(parts), status_code=200)


@router.get("/status", response_class=HTMLResponse)
async def engine_status(
    request: Request,
    q: str | None = Query(default=None, description="optional search query"),
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> HTMLResponse:
    """Render engine status HTML; with `q` param, also recall + render citations.

    Degraded path: any EngineError → degraded banner + no 500.

    OEI-008 — identity threading:
      This is a read-only anonymous surface: we resolve the caller via
      `caller_from_request_headers` and forward it to the engine for audit
      (the onyx adapter appends one row per call to `audit_log`). If no
      auth headers are present, we pass `EngineCallerContext.anonymous()` —
      the engine still works, the audit row simply says `<anonymous>`.
    """
    from ece.connectors.onyx.caller import caller_from_request_headers
    caller = caller_from_request_headers(authorization, x_user_id)

    engine = get_content_engine()
    status_dict: dict[str, Any] | None = None
    docs: list[dict[str, Any]] | None = None
    degraded_reason: str | None = None

    try:
        status = await engine.engine_status(caller=caller)
        status_dict = status.model_dump()
    except EngineError as e:
        degraded_reason = f"engine_status failed: {e}"

    if q:
        try:
            recalled = await engine.search(q, caller=caller)
            docs = [
                {
                    "engine_doc_id": d.engine_doc_id,
                    "title": d.title,
                    "snippet": d.snippet,
                    "source_type": d.source_type,
                    "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                    "raw": d.raw,
                }
                for d in recalled
            ]
        except EngineError as e:
            if degraded_reason is None:
                degraded_reason = f"search failed: {e}"
            else:
                degraded_reason += f"; search also failed: {e}"
            docs = None

    return _render_status_page(
        request=request,
        status_dict=status_dict,
        degraded_reason=degraded_reason,
        query=q,
        docs=docs,
    )
