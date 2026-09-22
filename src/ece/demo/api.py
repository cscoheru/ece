"""cut-042 — /api/v1/demo/* FastAPI router.

Two endpoints (per PRD §5):
  - GET  /api/v1/demo/domains          → domain manifest (business-named)
  - POST /api/v1/demo/scenarios/generate → live six-step loop run, business JSON

Auth follows the existing convention: `X-User-Id` header (with optional JWT
in `Authorization`, decoded by `ece.auth.jwt.resolve_caller_user_ref`).
"""
from __future__ import annotations

import contextlib
import importlib
import time
from typing import Any

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from ece.db import get_engine
from ece.demo.loop import run_demo_loop
from ece.demo.mapper import to_business
from ece.demo.spec import load_scenario_spec

__all__ = ["router"]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GenerateScenarioRequest(BaseModel):
    domain: str
    scenario: str = "default"
    params: dict[str, Any] = Field(default_factory=dict)
    seed: bool = False  # re-seed pack fixture before loop (idempotent, advisory)


class DomainEntry(BaseModel):
    name: str
    label: str
    scenarios: list[str]


class DomainsResponse(BaseModel):
    domains: list[DomainEntry]


# ---------------------------------------------------------------------------
# Domain manifest — static, scanned at import time
# ---------------------------------------------------------------------------


_DOMAIN_LABELS: dict[str, str] = {
    "procurement": "采购合规审查",
}


def _discover_domains() -> list[DomainEntry]:
    """Return all packs that have at least one scenario YAML under
    `src/ece/domain_packs/<pack>/scenarios/`.

    Runtime import triggers pack side-effects (rule registration); cut-042
    keeps the manifest read-only — no DB access here.
    """
    from pathlib import Path

    discovered: list[DomainEntry] = []
    packs_root = Path("src/ece/domain_packs")
    if not packs_root.exists():
        return discovered

    for pack_dir in sorted(packs_root.iterdir()):
        if not pack_dir.is_dir():
            continue
        scenarios_dir = pack_dir / "scenarios"
        if not scenarios_dir.is_dir():
            continue
        yamls = sorted(p.stem for p in scenarios_dir.glob("*.yaml"))
        if not yamls:
            continue
        # Touch the scenarios package so registry side-effects run once.
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"ece.domain_packs.{pack_dir.name}.scenarios")
        discovered.append(
            DomainEntry(
                name=pack_dir.name,
                label=_DOMAIN_LABELS.get(pack_dir.name, pack_dir.name),
                scenarios=yamls,
            )
        )
    return discovered


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.get("/domains", response_model=DomainsResponse)
def get_domains() -> DomainsResponse:
    """GET /api/v1/demo/domains — domain manifest.

    Per PRD §5: business-named domain list, no internal field leakage.
    """
    return DomainsResponse(domains=_discover_domains())


@router.post("/scenarios/generate")
def generate_scenario(
    req: GenerateScenarioRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """POST /api/v1/demo/scenarios/generate — live six-step loop run.

    Reads ScenarioSpec from `domain_packs/<req.domain>/scenarios/<req.scenario>.yaml`,
    invokes `run_demo_loop`, returns business-named JSON via `to_business`.

    Per PRD §5 #4: permission 反差 — if `req.params.actor` is in
    `spec.denied_users`, the loop returns the denied branch (zero side effect).
    """
    spec = load_scenario_spec(req.domain, req.scenario)

    actor = (
        req.params.get("actor")
        or x_user_id
        or "anonymous"
    )

    engine = get_engine()

    # Root source_id is a required scenario parameter; default to the spike
    # PR's source_id so the procurement-default scenario runs out of the box.
    root_source_id = str(
        req.params.get("root_source_id")
        or req.params.get("pr_source_id")
        or "SPIKE-PR-001"
    )

    started = time.perf_counter()
    loop_result = run_demo_loop(
        engine, actor, root_source_id, spec,
        params=req.params,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0

    return to_business(
        loop_result, spec,
        actor=actor, elapsed_ms=elapsed_ms,
    )
