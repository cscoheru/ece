"""ECE v0 FastAPI application -- S0.2 ships /healthz, Sprint 1-4 routes.

Endpoint map:
- Sprint 0: /healthz
- Sprint 1: /ingest/runs
- Sprint 2: /permissions/check, /resolve
- Sprint 3: /context
- Sprint 4: /search
- Sprint 5: /actions/preview (v0 不实现 /actions/execute)
- Sprint 6: /audit/context/{id}
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ece.api.actions import router as actions_router
from ece.api.audit import router as audit_router
from ece.api.context import router as context_router
from ece.api.debug import router as debug_router
from ece.api.engine_status import router as engine_status_router
from ece.api.entities import router as entities_router
from ece.api.identity import router as identity_router
from ece.api.ingest import router as ingest_router
from ece.api.memory import router as memory_router
from ece.api.search import router as search_router
from ece.consulting.router import router as consulting_router
from ece.demo.api import DemoSpecError
from ece.demo.api import router as demo_router

app = FastAPI(
    title="ECE v0",
    version="0.1.0",
    description="Enterprise Context Engine -- v0 (Procurement domain pack validation)",
)

# S1.1: ingest routes
app.include_router(ingest_router)
# S1.3: entity / relationship routes
app.include_router(entities_router)
# S2: identity / permissions / resolve
app.include_router(identity_router)
# S3.4: context assembly endpoint
app.include_router(context_router)
# OEI-010: persistent memory (write goes through the permission engine;
# GET/DELETE are the compliance surface)
app.include_router(memory_router)
# S4.3: unified search endpoint (FTS keyword route; vector/structured/rel stubbed)
app.include_router(search_router)
# S4.5+: actions preview endpoint (per ADR-004 /actions/execute v0 disabled)
app.include_router(actions_router)
# S6: audit trace (JSON) + debug UI (private deployment only)
app.include_router(audit_router)
app.include_router(debug_router)
# cut-042: /demo/* generic multi-domain live runner (PRD §5)
# cut-042R2 R2-F5: demo-specific exception mapping is registered AFTER demo
# router is included so its routes are known, but the handler is scoped by
# request path prefix to /api/v1/demo/ — non-demo routes retain their native
# error semantics (no global ValueError → 422 mapping).
DEMO_PREFIX = "/api/v1/demo"


@app.exception_handler(FileNotFoundError)
async def _demo_scenario_not_found_handler(
    request: Request, exc: FileNotFoundError,
) -> JSONResponse:
    if not request.url.path.startswith(DEMO_PREFIX):
        # Re-raise so Starlette's default 500 applies for non-demo routes.
        raise exc
    return JSONResponse(
        status_code=422,
        content={"error": "scenario_not_found", "detail": str(exc)},
    )


@app.exception_handler(DemoSpecError)
async def _demo_spec_error_handler(
    _request: Request, exc: DemoSpecError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": exc.kind, "detail": exc.detail},
    )


app.include_router(demo_router)

# KC-001: /api/v1/consulting/* read-only consulting knowledge catalog
# (file-backed seed, no DB, no LLM, no embedding — Task §3 Out-of-scope).
app.include_router(consulting_router)

# OEI-003: /engine/status visible deliverable — engine snapshot + ECE-rendered citations
app.include_router(engine_status_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness/readiness check (S0.2 only). Returns 200 if service is up."""
    return {"status": "ok", "service": "ece", "version": app.version}
