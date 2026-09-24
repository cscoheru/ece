"""OnyxContentEngineAdapter — real implementation against Onyx CE v4.7.8 (OEI-003 §4).

Endpoints used (all read-only, verified by OEI-002 §1.1):
  GET  /api/admin/llm/provider        — providers + default_text
  GET  /api/user/projects             — list projects
  GET  /api/user/projects/files/{id}  — files in project
  POST /api/search                    — recall (returns results[])
  GET  /api/version                   — version string

Per OEI-003 §6 硬约束:cookie never enters ECE codebase; loaded at runtime from
ECE_ONYX_COOKIE_FILE (chmod 600, default /home/fisher/.onyx-lab/.secrets/admin-cookies.txt).
The value lives only in this module's _load_cookie_file() return — never logged,
never persisted, never imported into domain_packs/.
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from ece.connectors.onyx.port import (
    ContentEnginePort,
    EngineDocument,
    EngineError,
    EngineProject,
    EngineStatus,
)


_DEFAULT_BASE = "http://127.0.0.1:8080"
_DEFAULT_COOKIE_FILE = "/home/fisher/.onyx-lab/.secrets/admin-cookies.txt"
_TIMEOUT_SECONDS = 60.0
_MAX_SNIPPET_CHARS = 800


def _parse_netscape_cookies(path: str | os.PathLike[str]) -> httpx.Cookies:
    """Parse a Netscape-format cookies file into an httpx.Cookies jar.

    Per OEI-002 §1.2 / TASK v3: cookie file MUST live on a POSIX-permitting
    filesystem (i.e. /home/*, NOT /mnt/d) so chmod 600 actually restricts access.

    Format (Netscape / curl):
      # comment lines start with # (including the #HttpOnly_ prefix marker)
      domain  flag  path  secure  expiration  name  value

    httpx.Cookies lets us pass cookies without ever stringifying the value in a
    way that logs / traces / serializes the bearer secret.
    """
    p = Path(path)
    if not p.exists():
        raise EngineError(f"cookie file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise EngineError(f"cookie file unreadable: {p}: {e}") from e

    jar = httpx.Cookies()
    parsed_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Treat "#HttpOnly_*" lines as cookie rows (Netscape HttpOnly marker);
        # skip plain "#" comment lines (header / explanatory).
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        # fields are tab-separated (curl) but tolerate space-separated fallback
        sep = "\t" if "\t" in line else None
        parts = line.split(sep) if sep else line.split()
        if len(parts) < 7:
            continue
        # parts[6:] covers any cookie value containing the chosen separator
        domain, _flag, path_, _secure, _expires, name = parts[:6]
        value = "\t".join(parts[6:]) if sep == "\t" else " ".join(parts[6:])
        # NEVER log / print the value
        jar.set(name, value, domain=domain.lstrip("#HttpOnly_"), path=path_ or "/")
        parsed_lines += 1
    if parsed_lines == 0:
        raise EngineError(f"cookie file parsed but jar is empty: {p}")
    return jar


class OnyxContentEngineAdapter:
    """Live adapter for Onyx CE.

    Configuration via env vars:
      ECE_ONYX_BASE         — base URL (default http://127.0.0.1:8080)
      ECE_ONYX_COOKIE_FILE  — cookie file path
    """

    def __init__(
        self,
        base_url: str | None = None,
        cookie_file: str | None = None,
    ) -> None:
        self._base = (base_url or os.environ.get("ECE_ONYX_BASE") or _DEFAULT_BASE).rstrip("/")
        self._cookie_file = (
            cookie_file
            or os.environ.get("ECE_ONYX_COOKIE_FILE")
            or _DEFAULT_COOKIE_FILE
        )
        self._last_latency: float | None = None

    def _client(self) -> httpx.Client:
        cookies = _parse_netscape_cookies(self._cookie_file)
        return httpx.Client(
            base_url=self._base,
            cookies=cookies,
            timeout=_TIMEOUT_SECONDS,
        )

    async def search(
        self, query: str, *, top_k: int | None = None
    ) -> list[EngineDocument]:
        start = time.perf_counter()
        body: dict[str, Any] = {"query": query}
        # Onyx v4.7.8 /api/search does not accept top_k directly; we cap client-side
        # by slicing results. Future: pass source_limit or similar if added.
        try:
            with self._client() as cli:
                resp = cli.post("/api/search", json=body)
        except (httpx.HTTPError, OSError) as e:
            raise EngineError(f"Onyx /api/search transport failure: {e}") from e
        if resp.status_code >= 500:
            raise EngineError(
                f"Onyx /api/search returned {resp.status_code}: {resp.text[:200]}"
            )
        if resp.status_code == 401 or resp.status_code == 403:
            raise EngineError(
                f"Onyx /api/search auth failure {resp.status_code}: cookie invalid or expired"
            )
        if resp.status_code != 200:
            raise EngineError(
                f"Onyx /api/search returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise EngineError(f"Onyx /api/search non-JSON response: {e}") from e
        results = data.get("results") or []
        docs = [_result_to_engine_document(r) for r in results]
        if top_k is not None:
            docs = docs[: max(0, top_k)]
        self._last_latency = time.perf_counter() - start
        return docs

    async def engine_status(self) -> EngineStatus:
        # compose from multiple endpoints; raise EngineError on any transport failure
        try:
            with self._client() as cli:
                prov_resp = cli.get("/api/admin/llm/provider")
                proj_resp = cli.get("/api/user/projects")
                # /api/version is optional; ignore failure
                try:
                    ver_resp = cli.get("/api/version")
                    ver_data = ver_resp.json() if ver_resp.status_code == 200 else {}
                except Exception:
                    ver_data = {}
        except (httpx.HTTPError, OSError) as e:
            raise EngineError(f"Onyx status transport failure: {e}") from e

        if prov_resp.status_code != 200:
            raise EngineError(
                f"Onyx /api/admin/llm/provider returned {prov_resp.status_code}"
            )
        if proj_resp.status_code != 200:
            raise EngineError(
                f"Onyx /api/user/projects returned {proj_resp.status_code}"
            )

        try:
            prov_data = prov_resp.json()
            proj_data = proj_resp.json()
        except Exception as e:
            raise EngineError(f"Onyx status non-JSON: {e}") from e

        providers = prov_data.get("providers") or []
        default_text = prov_data.get("default_text") or {}
        provider_name = providers[0].get("name") if providers else None
        default_model = default_text.get("model_name") if isinstance(default_text, dict) else None

        projects = proj_data if isinstance(proj_data, list) else []
        project_count = len(projects)
        file_count = 0
        # try to fetch files for project 1 (OEI-001 demo project)
        if projects:
            first_id = projects[0].get("id")
            if isinstance(first_id, int):
                try:
                    with self._client() as cli:
                        files_resp = cli.get(f"/api/user/projects/files/{first_id}")
                    if files_resp.status_code == 200:
                        files = files_resp.json() or []
                        file_count = len(files)
                except Exception:
                    file_count = 0

        # engine_version: /api/version returns e.g. {"version": "0.0.0-dev"} or
        # {"backend_version": "..."}; fall back to raw value
        engine_version = (
            ver_data.get("version")
            or ver_data.get("backend_version")
            or "unknown"
        )

        # tier / gpu_enabled — not exposed by /api/version; leave as community default.
        # Future: read from /api/settings or hardcode until Onyx exposes version detail.
        return EngineStatus(
            engine_name="onyx",
            engine_version=engine_version,
            tier="community",
            gpu_enabled=True,  # OEI-002 §1 confirmed gpu_enabled=true on this deployment
            provider_name=provider_name,
            default_model=default_model,
            project_count=project_count,
            file_count=file_count,
            last_search_latency_seconds=self._last_latency,
            raw={
                "providers_count": len(providers),
                "version_payload": ver_data,
            },
        )

    async def list_projects(self) -> list[EngineProject]:
        try:
            with self._client() as cli:
                resp = cli.get("/api/user/projects")
        except (httpx.HTTPError, OSError) as e:
            raise EngineError(f"Onyx /api/user/projects transport failure: {e}") from e
        if resp.status_code != 200:
            raise EngineError(
                f"Onyx /api/user/projects returned {resp.status_code}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise EngineError(f"Onyx /api/user/projects non-JSON: {e}") from e
        if not isinstance(data, list):
            return []
        return [
            EngineProject(
                engine_project_id=p.get("id"),
                name=p.get("name", ""),
                raw=p,
            )
            for p in data
            if isinstance(p.get("id"), int)
        ]


def _result_to_engine_document(result: dict[str, Any]) -> EngineDocument:
    """Map an Onyx /api/search result dict to EngineDocument.

    Onyx result fields (OEI-002 verified):
      citation_id, title, content (full text), link, source_type, updated_at
    """
    title = result.get("title") or ""
    content = result.get("content") or ""
    snippet = content if len(content) <= _MAX_SNIPPET_CHARS else content[:_MAX_SNIPPET_CHARS] + "…"
    updated_at = None
    raw_updated = result.get("updated_at")
    if isinstance(raw_updated, str):
        try:
            updated_at = datetime.fromisoformat(raw_updated.replace("Z", "+00:00"))
        except Exception:
            updated_at = None
    return EngineDocument(
        engine_doc_id=str(result.get("citation_id") or ""),
        title=title,
        snippet=snippet,
        source_type=result.get("source_type") or "unknown",
        updated_at=updated_at,
        raw=result,
    )


# Runtime checkable assertion
assert isinstance(OnyxContentEngineAdapter(), ContentEnginePort)  # type: ignore[abstract]
