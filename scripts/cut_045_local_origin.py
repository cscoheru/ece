#!/usr/bin/env python3
"""cut-045R1 — Local same-origin reverse proxy for deployment-smoke testing.

Codex R3-B3 finding (cut-045 R1 HOLD): the previous cut-045 deployment
smoke was actually pointed at an API-only uvicorn (port 8765), so its
SPA-specific checks (1 / 10) SKIPPED. This script starts a stand-alone
same-origin HTTP server that:

  1. Serves SPA static files (`demos/spa/`) — so check 1 + check 10
     actually run against real HTML, not a 404.
  2. Reverse-proxies `<origin>/api/*` + `/healthz` to the FastAPI
     upstream — so every API call in the smoke traverses the same
     origin the SPA uses in the browser (no CORS / cross-origin).

This mirrors the cut-042R2 R2-F3 + cut-044R1 R1-B3 reverse-proxy
pattern; the only difference is the port (8080 default — chosen to
NOT collide with cut-042R2's 8088 or cut-044R2's 8089).

Usage:
  # Terminal A:
  uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765

  # Terminal B:
  python scripts/cut_045_local_origin.py              # default port 8080
  DEMO_BASE_URL=http://127.0.0.1:8080 \\
      python scripts/cut_045_demo_deployment_smoke.py  # expect PASS=10

Exits on SIGINT / SIGTERM. Logs every request (unlike cut-044's silent
log_message) so an operator can confirm the proxy chain is live.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SPA_DIR = REPO_ROOT / "demos" / "spa"

DEFAULT_ORIGIN_PORT = 8080
DEFAULT_API_UPSTREAM = "http://127.0.0.1:8765"

PROXY_PREFIXES = ("/api/", "/healthz", "/openapi.json")


class _ProxyHandler(BaseHTTPRequestHandler):
    """SPA static + /api/ reverse-proxy (cut-045R1 R3-B3 fix)."""

    server_version = "cut-045R1-origin-proxy/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Surface the proxy chain in stdout so operators can see it
        sys.stdout.write(
            f"[cut-045-origin] {self.command} {self.path} → "
            f"{'proxy' if self._should_proxy(self.path.split('?', 1)[0]) else 'static'}\n"
        )
        sys.stdout.flush()

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if self._should_proxy(path):
            self._proxy_request("GET", path)
            return
        self._serve_static(path)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if self._should_proxy(path):
            self._proxy_request("POST", path)
            return
        self.send_error(405, "POST only valid for /api/")

    def do_OPTIONS(self) -> None:
        # Same-origin deployment: browser never fires CORS preflight
        # (Origin == Host). If a script does send OPTIONS, return 204
        # for any /api/ path so the smoke can still run.
        path = self.path.split("?", 1)[0]
        if self._should_proxy(path):
            self._proxy_request("OPTIONS", path)
            return
        self.send_response(204)
        self.end_headers()

    @staticmethod
    def _should_proxy(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PROXY_PREFIXES)

    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        # Resolve SPA files relative to demos/spa/. Disallow parent
        # traversal to prevent serving repo-internal files.
        target = (SPA_DIR / rel).resolve()
        try:
            target.relative_to(SPA_DIR.resolve())
        except ValueError:
            self.send_error(404, f"path outside SPA root: {rel}")
            return
        if not target.is_file():
            # SPA index.html fallback for client-side routes (kept simple
            # since this server is for smoke testing, not browser routing).
            fallback = SPA_DIR / "index.html"
            if fallback.is_file():
                target = fallback
            else:
                self.send_error(404, f"no SPA asset at {rel}")
                return
        try:
            data = target.read_bytes()
        except OSError as exc:
            self.send_error(500, f"failed to read {rel}: {exc}")
            return
        ctype = self._guess_content_type(rel)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _proxy_request(self, method: str, path: str) -> None:
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        upstream_url = f"{API_UPSTREAM}{path}{('?' + qs) if qs else ''}"
        req_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        body: bytes | None = None
        if method in ("POST", "PUT", "PATCH"):
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                body = self.rfile.read(length)
        try:
            upstream_req = urllib.request.Request(
                upstream_url, data=body, method=method, headers=req_headers,
            )
            with urllib.request.urlopen(upstream_req, timeout=10) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for h in ("Content-Type", "Content-Length"):
                    v = resp.headers.get(h)
                    if v is not None:
                        self.send_header(h, v)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read()
            except Exception:
                payload = str(exc).encode()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except urllib.error.URLError as exc:
            self.send_error(502, f"upstream unreachable: {exc}")

    @staticmethod
    def _guess_content_type(rel: str) -> str:
        if rel.endswith(".html"):
            return "text/html; charset=utf-8"
        if rel.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if rel.endswith(".css"):
            return "text/css; charset=utf-8"
        if rel.endswith(".json"):
            return "application/json; charset=utf-8"
        return "application/octet-stream"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="cut-045R1 local same-origin reverse proxy (SPA + /api/)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CUT_045_ORIGIN_PORT", DEFAULT_ORIGIN_PORT)),
        help=f"origin port (default {DEFAULT_ORIGIN_PORT})",
    )
    parser.add_argument(
        "--upstream",
        default=os.environ.get("API_UPSTREAM", DEFAULT_API_UPSTREAM),
        help=f"FastAPI upstream base URL (default {DEFAULT_API_UPSTREAM})",
    )
    args = parser.parse_args()

    # Override module-level constant so the handler uses the chosen upstream.
    global API_UPSTREAM
    API_UPSTREAM = args.upstream

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _ProxyHandler)
    print(f"[cut-045-origin] listening on 127.0.0.1:{args.port}")
    print(f"[cut-045-origin] SPA static   → {SPA_DIR}")
    print(f"[cut-045-origin] API upstream → {API_UPSTREAM}")
    print(f"[cut-045-origin] proxy prefixes: {', '.join(PROXY_PREFIXES)}")
    print(f"[cut-045-origin] run smoke:    DEMO_BASE_URL=http://127.0.0.1:{args.port} \\")
    print(f"                       python scripts/cut_045_demo_deployment_smoke.py")

    def _shutdown(_signum: int, _frame: object) -> None:
        print("\n[cut-045-origin] shutting down ...")
        server.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())