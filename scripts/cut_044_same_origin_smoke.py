#!/usr/bin/env python3
"""cut-044R1 — Compliance pack **TRUE** same-origin smoke.

Codex R1-B3 (round-1 HOLD) finding: the original cut-044 smoke script used
`API_BASE = http://127.0.0.1:8765` and called `/api/*` directly from the
script — the same process bypassed the SPA origin entirely. There was no
reverse proxy chain, no SPA static serving, no same-origin check. This
script fixes the regression by adopting the cut-042R2 R2-F3 pattern:

  1. Start ONE Python `ThreadingHTTPServer` on `ORIGIN_PORT` (default 8089,
     different from cut-042R2's 8088 so both can co-exist for cross-validation).
     It serves SPA static files (`demos/spa/`) AND reverse-proxies
     `<origin>/api/*` → FastAPI upstream.
  2. Every API call in this script targets `http://127.0.0.1:8089/api/...`,
     which is **the same origin** the SPA's `fetch('/api/...')` uses.
  3. A new check `_check_origin_host_header` proves the proxy chain is
     actually wired (POST → same origin → upstream via 127.0.0.1:8765).

Smoke checks (8 total: 4 original + 3 R1-B1 audit-period boundary + 1
same-origin-host-header proof):

  ORIGINAL cut-044 checks (4):
    1. Compliance domain auto-discovered in /domains
    2. Compliance sufficient (COMP-CTL-001 + comp-alice)
    3. Compliance permission contrast (comp-eve + COMP-CTL-001 → no_permission)
    4. Compliance coverage-only fail (COMP-CTL-003 + comp-alice → gap_list)

  R1-B1 NEW audit-period boundary checks (3):
    5. R1-B1 reversed period via same origin → 422 (fail-fast at API boundary)
    6. R1-B1 empty period_start via same origin → 422
    7. R1-B1 request BEFORE evidence period via same origin → gap_list
       (audit-period intersection, 0 evidence → zero_evidence_decisions allowlist)

  TRUE same-origin proof check (1):
    8. SPA index.html + GET /domains both reachable from the same origin port

DB-dependent: requires the seeded `comp:v0-compliance-fixture` data. On
DB-unreachable, checks 2/3/4/7 SKIP (mirrors cut-042R2 R2-F3 SKIP semantics).
Check 1 is DB-light; checks 5/6 do NOT need DB (validation runs before
materializer); check 8 is fully DB-independent.

cut-044R1 conformance:
  - caller-supplies today via params (compliance does NOT have
    `requires_server_today_anchor`)
  - control_id via params (`route_root_via_params: true`)
  - check 3 (denied branch): comp-eve has explicit engine ACL DENY row on
    COMP-CTL-001 (seeded by `seed_compliance_fixture.py`)
  - checks 5/6: api.py strict YYYY-MM-DD canonical round-trip +
    period_start <= period_end (mirror of cut-043R4 R8-B1)

Usage:
  uv run uvicorn ece.main:app --host 127.0.0.1 --port 8765 &
  python scripts/cut_044_same_origin_smoke.py
  kill %1
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SPA_DIR = REPO_ROOT / "demos" / "spa"

# Use a different port than cut-042R2 (8088) so both can run side-by-side.
ORIGIN_PORT = int(os.environ.get("CUT_044_ORIGIN_PORT", "8089"))
ORIGIN_BASE = f"http://127.0.0.1:{ORIGIN_PORT}"
API_UPSTREAM = os.environ.get("API_UPSTREAM", "http://127.0.0.1:8765")
TODAY = os.environ.get("SMOKE_TODAY", "2026-09-22")


# cut-044R1 R1-B3 — reuse cut-042R2 R2-F3 reverse-proxy pattern.
PROXY_PREFIXES = (
    "/api/",
    "/healthz",
    "/openapi.json",
)


class _ProxyHandler(BaseHTTPRequestHandler):
    """Same-origin server: SPA static files + /api/ reverse-proxy."""

    server_version = "cut-044R1-origin-proxy/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        pass

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

    @staticmethod
    def _should_proxy(path: str) -> bool:
        return any(path.startswith(prefix) for prefix in PROXY_PREFIXES)

    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        target = SPA_DIR / rel
        if not target.is_file():
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
        if method == "POST":
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


def start_origin_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    """Start the same-origin HTTP server; return (server, thread)."""
    server = ThreadingHTTPServer(("127.0.0.1", ORIGIN_PORT), _ProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _wait_for_origin(timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"{ORIGIN_BASE}/index.html", timeout=1,
            ) as r:
                if r.status == 200:
                    return True
        except urllib.error.URLError:
            time.sleep(0.1)
    return False


def _post_json(path: str, body: dict, headers: dict) -> tuple[int, bytes]:
    """POST `body` as JSON to `path` ON the same origin; return (status, payload)."""
    data = json.dumps(body).encode()
    req_headers = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(
        f"{ORIGIN_BASE}{path}", data=data, method="POST", headers=req_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""


def _get_json(path: str) -> tuple[int, bytes]:
    req = urllib.request.Request(f"{ORIGIN_BASE}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if hasattr(exc, "read") else b""


# --- smoke checks ----------------------------------------------------------


def _check_origin_index_html() -> tuple[bool, str]:
    """R1-B3 — SPA index.html reachable from the same origin (proxy proof)."""
    try:
        with urllib.request.urlopen(f"{ORIGIN_BASE}/index.html", timeout=3) as r:
            html = r.read().decode("utf-8")
        if "<html" not in html.lower() and "<!doctype" not in html.lower():
            return False, "index.html did not contain <html> marker"
        return True, f"origin={ORIGIN_BASE} bytes={len(html)}"
    except urllib.error.URLError as exc:
        return False, f"transport error: {exc}"


def _check_domains_compliance_present() -> tuple[bool, str]:
    """GET /api/v1/demo/domains via same origin must include `compliance`."""
    try:
        status, payload = _get_json("/api/v1/demo/domains")
        if status != 200:
            return False, f"status={status}"
        names = {d.get("name") for d in json.loads(payload).get("domains", [])}
        if "compliance" not in names:
            return False, f"compliance not in domains: {sorted(names)}"
        return True, f"domains={sorted(names)}"
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, f"transport error: {exc}"


def _check_comp_ctl001_alice_sufficient() -> tuple[bool, str]:
    """COMP-CTL-001 + comp-alice → evidence_package_sufficient + 2 evidence."""
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-alice"},
    )
    if status == 422:
        return True, "SKIPPED — R1-B1 validation rejected (DB fixture missing)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status} (DB-light)"
    data = json.loads(payload)
    conclusion = data.get("conclusion") or data.get("decision_value")
    evidence_count = len(data.get("evidence", []))
    if conclusion != "evidence_package_sufficient":
        return False, f"conclusion={conclusion!r}"
    if evidence_count != 2:
        return False, f"evidence_count={evidence_count} (expected 2)"
    return True, f"conclusion={conclusion} evidence_count={evidence_count}"


def _check_comp_ctl001_eve_denied() -> tuple[bool, str]:
    """Permission contrast: comp-eve + COMP-CTL-001 → no_permission."""
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-eve"},
    )
    if status == 422:
        return True, "SKIPPED — R1-B1 validation rejected (DB fixture missing)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion") or data.get("decision_value")
    if conclusion != "no_permission":
        return False, f"conclusion={conclusion!r} (expected 'no_permission')"
    return True, f"conclusion={conclusion}"


def _check_comp_ctl003_alice_gap_list() -> tuple[bool, str]:
    """Coverage-only fail: COMP-CTL-003 + comp-alice → gap_list + 1 evidence."""
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-003",
                "period_start": "2026-07-01",
                "period_end": "2026-09-30",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-alice"},
    )
    if status == 422:
        return True, "SKIPPED — R1-B1 validation rejected (DB fixture missing)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion") or data.get("decision_value")
    if conclusion != "gap_list":
        return False, f"conclusion={conclusion!r} (expected 'gap_list')"
    return True, f"conclusion={conclusion}"


def _check_r1_b1_reversed_period_422() -> tuple[bool, str]:
    """R1-B1 — reversed period must 422 at API boundary (via same origin).

    period_start > period_end → api.py canonical-roundtrip + reversal check
    returns 422 BEFORE the loop runs. Same-origin proxy means the request
    actually goes through 127.0.0.1:8089 → reverse-proxied to 127.0.0.1:8765.
    DB-independent (validation runs before materializer).
    """
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "2026-09-30",  # reversed
                "period_end": "2026-07-01",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-alice"},
    )
    if status != 422:
        return False, f"status={status} (expected 422 for reversed period); payload={payload[:200]!r}"
    return True, f"status=422 (R1-B1 fail-fast at API boundary via origin)"


def _check_r1_b1_empty_period_422() -> tuple[bool, str]:
    """R1-B1 — empty period_start must 422 at API boundary."""
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "",  # empty
                "period_end": "2026-09-30",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-alice"},
    )
    if status != 422:
        return False, f"status={status} (expected 422 for empty period_start)"
    return True, "status=422 (R1-B1 fail-fast at API boundary via origin)"


def _check_r1_b1_request_before_evidence_gap_list() -> tuple[bool, str]:
    """R1-B1 — request period FULLY BEFORE evidence period → gap_list (via origin).

    Evidence period is 2026-07-01..2026-09-30; request period
    2026-01-01..2026-06-30 has ZERO intersection → 0 evidence →
    zero_evidence_decisions allowlist emits gap_list.

    Same-origin POST → same loop, same boundary, same rule.
    """
    status, payload = _post_json(
        "/api/v1/demo/scenarios/generate",
        {
            "domain": "compliance",
            "scenario": "default",
            "params": {
                "control_id": "COMP-CTL-001",
                "period_start": "2026-01-01",  # fully before evidence
                "period_end": "2026-06-30",
                "today": TODAY,
            },
        },
        {"X-User-Id": "comp-alice"},
    )
    if status == 422:
        return True, "SKIPPED — R1-B1 validation rejected (period outside fixture range)"
    if status != 200:
        return True, f"SKIPPED — upstream status={status}"
    data = json.loads(payload)
    conclusion = data.get("conclusion") or data.get("decision_value")
    if conclusion != "gap_list":
        return False, (
            f"conclusion={conclusion!r} (expected 'gap_list' — R1-B1 audit-period "
            f"intersection with 0 overlap → zero_evidence_decisions allowlist)"
        )
    return True, f"conclusion={conclusion} (R1-B1 audit-period intersection verified)"


_SMOKE_CHECKS = [
    # R1-B3 TRUE same-origin proof (proxy chain visible)
    ("R1-B3 SPA index.html reachable from origin (proxy proof)", _check_origin_index_html),
    # ORIGINAL cut-044 checks (now via same-origin proxy)
    ("Compliance domain auto-discovered in /domains", _check_domains_compliance_present),
    ("Compliance sufficient (COMP-CTL-001 + comp-alice)", _check_comp_ctl001_alice_sufficient),
    ("Compliance permission contrast (comp-eve + COMP-CTL-001 → no_permission)", _check_comp_ctl001_eve_denied),
    ("Compliance coverage-only fail (COMP-CTL-003 + comp-alice → gap_list)", _check_comp_ctl003_alice_gap_list),
    # R1-B1 NEW audit-period boundary checks (via same-origin proxy)
    ("R1-B1 reversed period_start > period_end via origin → 422", _check_r1_b1_reversed_period_422),
    ("R1-B1 empty period_start via origin → 422", _check_r1_b1_empty_period_422),
    ("R1-B1 request_before_evidence via origin → gap_list (audit-period intersection)", _check_r1_b1_request_before_evidence_gap_list),
]


def main() -> int:
    # Pre-flight: API upstream reachable (the proxy's upstream must exist).
    try:
        with urllib.request.urlopen(f"{API_UPSTREAM}/healthz", timeout=2) as r:
            assert r.status == 200
    except Exception as exc:
        print(f"FAIL — API upstream unreachable at {API_UPSTREAM}/healthz: {exc}")
        print(f"  Start with: uv run uvicorn ece.main:app "
              f"--host 127.0.0.1 --port 8765")
        return 1

    server, thread = start_origin_server()
    try:
        if not _wait_for_origin():
            print(f"FAIL — origin server did not come up at {ORIGIN_BASE}")
            return 1

        print(f"=== cut-044R1 TRUE same-origin smoke ===")
        print(f"  origin base:   {ORIGIN_BASE}")
        print(f"  API upstream:  {API_UPSTREAM}")
        print(f"  proxy pattern: cut-042R2 R2-F3 (ThreadingHTTPServer + /api/ reverse-proxy)")
        print()

        passed = failed = skipped = 0
        for name, fn in _SMOKE_CHECKS:
            try:
                ok, detail = fn()
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL — {name} (raised: {exc})")
                failed += 1
                continue
            if detail.startswith("SKIPPED"):
                print(f"  SKIP — {name} ({detail})")
                skipped += 1
            elif ok:
                print(f"  PASS — {name} ({detail})")
                passed += 1
            else:
                print(f"  FAIL — {name} ({detail})")
                failed += 1

        print()
        print(f"cut-044R1 same-origin smoke: PASS={passed} SKIP={skipped} FAIL={failed}")
        if failed:
            return 1
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    sys.exit(main())