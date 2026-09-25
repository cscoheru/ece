#!/usr/bin/env python3
"""S0.4: scripts/check_api_docs.py

API.md 文档 vs FastAPI openapi.json 双向 diff:
- 文档有而路由无 → WARNING(planned Sprint 1+),仍 exit 0
- 路由有而文档无 → ERROR + exit 1(实现超出文档 = 必须先更新文档)

API.md 格式:每节 `### <METHOD> <path>` 标题(如 `### POST /api/v1/context`)。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi import FastAPI

# 过滤 FastAPI 自动生成的路由(模块级常量 — N806 修复)
_AUTO_PREFIXES = ("/docs", "/openapi.json", "/redoc", "/healthz")
_SKIP_METHODS = {"HEAD", "OPTIONS"}


def parse_api_md_endpoints(path: Path) -> set[tuple[str, str]]:
    """Parse `### <METHOD> <path>` headers from docs/API.md.

    Accepts both plain (`### POST /path`) and numbered (`### 12.1 POST /path`)
    titles — the numbered form is the OEI-008 §11/§12 / §13 convention and the
    previous parser only matched the plain form, which is why the script
    flagged 4 consulting routes as "implemented but not documented" (false
    positive). OEI-009 §0 step 2.
    """
    # Accept an optional `N.M ` (or `N. `) section-number prefix before the method.
    # Format is `### 12.1 POST /path` — no trailing dot after the number.
    pattern = re.compile(
        r"^###\s+(?:\d+(?:\.\d+)*\.?\s+)?"
        r"(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)"
    )
    endpoints: set[tuple[str, str]] = set()
    if not path.exists():
        print(f"WARN: {path} not found", file=sys.stderr)
        return endpoints
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if m:
            endpoints.add((m.group(1), m.group(2)))
    return endpoints


def get_app_endpoints(app: FastAPI) -> set[tuple[str, str]]:
    """Extract (method, path) tuples from FastAPI app routes (recurses into included routers).

    过滤 FastAPI 自动生成的路由:
    - /docs, /redoc, /openapi.json (Swagger UI)
    - /docs/oauth2-redirect
    - /healthz (S0.2 已存在, API.md §9 仅提及无 ### 标题)
    - HEAD 方法(GET 自动衍生)
    - OPTIONS 方法
    """
    endpoints: set[tuple[str, str]] = set()

    def _walk(routes):
        for route in routes:
            # _IncludedRouter wrapper: recurse into original_router.routes
            inner = getattr(route, "original_router", None)
            if inner is not None and not getattr(route, "methods", None):
                inner_routes = getattr(inner, "routes", None)
                if inner_routes:
                    _walk(inner_routes)
                continue

            methods = getattr(route, "methods", None) or set()
            path = getattr(route, "path", None)
            if not path or not methods:
                continue
            if path.startswith(_AUTO_PREFIXES):
                continue
            for method in methods:
                if method in _SKIP_METHODS:
                    continue
                endpoints.add((method, path))

    _walk(app.routes)
    return endpoints


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    api_md = repo_root / "docs" / "API.md"
    docs_endpoints = parse_api_md_endpoints(api_md)
    print(f"API.md endpoints ({len(docs_endpoints)}):")
    for m, p in sorted(docs_endpoints):
        print(f"  {m:6s} {p}")

    # Import FastAPI app
    sys.path.insert(0, str(repo_root / "src"))
    from ece.main import app  # noqa: E402

    app_endpoints = get_app_endpoints(app)
    print(f"\nApp routes ({len(app_endpoints)}):")
    for m, p in sorted(app_endpoints):
        print(f"  {m:6s} {p}")

    # Diff: docs-only = warning (planned); app-only = ERROR
    docs_only = docs_endpoints - app_endpoints
    app_only = app_endpoints - docs_endpoints
    common = docs_endpoints & app_endpoints

    print(f"\nCommon: {len(common)} | Docs-only (planned): {len(docs_only)} | App-only: {len(app_only)}")

    if docs_only:
        print("\nWARN — planned but not yet implemented (exit 0, Sprint 1+ scope):")
        for m, p in sorted(docs_only):
            print(f"  {m:6s} {p}  (planned)")
    if app_only:
        print("\nERROR — implemented but not documented (S0.4 violation: must update API.md):")
        for m, p in sorted(app_only):
            print(f"  {m:6s} {p}")
        return 1
    print("\nOK — no app-only routes; docs-only are planned Sprint 1+ scope")
    return 0


if __name__ == "__main__":
    sys.exit(main())
