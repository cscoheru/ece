"""ECE v0 FastAPI application -- S0.2 only ships /healthz.

后续 Sprint 逐步添加:
- Sprint 1: /ingest/runs
- Sprint 2: /permissions/check
- Sprint 3: /context
- Sprint 4: /search
- Sprint 5: /actions/preview (v0 不实现 /actions/execute)
- Sprint 6: /audit/context/{id}
"""

from fastapi import FastAPI

from ece.api.entities import router as entities_router
from ece.api.ingest import router as ingest_router

app = FastAPI(
    title="ECE v0",
    version="0.1.0",
    description="Enterprise Context Engine -- v0 (Procurement domain pack validation)",
)

# S1.1: ingest routes
app.include_router(ingest_router)
# S1.3: entity / relationship routes
app.include_router(entities_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness/readiness check (S0.2 only). Returns 200 if service is up."""
    return {"status": "ok", "service": "ece", "version": app.version}
