"""cut-042 — /api/v1/demo/* FastAPI router.

Two endpoints (per PRD §5):
  - GET  /api/v1/demo/domains          → domain manifest (business-named)
  - POST /api/v1/demo/scenarios/generate → live six-step loop run, business JSON

Auth follows the existing convention: `X-User-Id` header (with optional JWT
in `Authorization`, decoded by `ece.auth.jwt.resolve_caller_user_ref`).

cut-042R changes (Codex HOLD 2026-09-22, F1/F2/F5):
  - F1: `actor` is resolved strictly from `X-User-Id`. The body MUST NOT be able
    to override the caller's identity. Previously `params.actor` could spoof an
    allowed user; this is now an explicit refusal.
  - F2: domain label and default root source id are read from ScenarioSpec
    (each pack's scenarios/<scenario>.yaml), not from in-module constants.
  - F5: `FileNotFoundError` and `ValueError` raised by the spec loader are
    mapped to HTTP 422 with structured JSON. Unknown domain / scenario /
    path-traversal attempt all return 422 (no longer 500).
"""
from __future__ import annotations

import contextlib
import importlib
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ece.db import get_engine
from ece.demo.loop import run_demo_loop
from ece.demo.mapper import to_business
from ece.demo.spec import load_scenario_spec

__all__ = ["router", "DemoSpecError"]


# ---------------------------------------------------------------------------
# cut-042R F5 + cut-042R2 R2-F5 — map load_scenario_spec's
# FileNotFoundError / ValueError to HTTP 422 via a dedicated exception type
# scoped to the demo router. NOT a global @app.exception_handler(ValueError),
# which would change error semantics for non-demo routes (out of scope lock).
# ---------------------------------------------------------------------------


class DemoSpecError(Exception):
    """Wraps FileNotFoundError / ValueError raised by `load_scenario_spec`.

    Maps unknown domain / scenario / path-traversal attempt to HTTP 422 with
    structured JSON. Lives on the demo router so other FastAPI routes keep
    their native error semantics.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


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
# Domain manifest — reads label from each pack's ScenarioSpec YAML
# (cut-042R F2: business label is read from spec.label, no in-module dict).
# ---------------------------------------------------------------------------


def _discover_domains() -> list[DomainEntry]:
    """Return all packs that have at least one scenario YAML under
    `src/ece/domain_packs/<pack>/scenarios/`.

    Runtime import triggers pack side-effects (rule registration); cut-042
    keeps the manifest read-only — no DB access here.

    cut-042R F2: business label is read from each pack's ScenarioSpec YAML
    (`spec.label`), not from a hardcoded dict.
    """
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

        # Read label from the first scenario YAML (all scenarios in a pack share
        # the same domain label). Falls back to pack name if spec.label absent.
        first_yaml = scenarios_dir / f"{yamls[0]}.yaml"
        label = _read_label_from_yaml(first_yaml, fallback=pack_dir.name)

        discovered.append(
            DomainEntry(
                name=pack_dir.name,
                label=label,
                scenarios=yamls,
            )
        )
    return discovered


def _read_label_from_yaml(yaml_path: Path, *, fallback: str) -> str:
    """cut-042R F2 helper — read `label` field from a ScenarioSpec YAML.

    If the YAML is malformed or has no label, fall back to the pack directory
    name (already-safe identifier). Never raises — discovery is best-effort.
    """
    try:
        import yaml
        with yaml_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if isinstance(raw, dict):
            label = raw.get("label")
            if isinstance(label, str) and label.strip():
                return label.strip()
    except Exception:  # noqa: BLE001 — discovery is best-effort
        pass
    return fallback


# ---------------------------------------------------------------------------
# cut-042R F1 — actor strictly from X-User-Id. body MUST NOT override.
# ---------------------------------------------------------------------------


def _resolve_actor(x_user_id: str | None) -> str:
    """Resolve the calling actor strictly from the `X-User-Id` header.

    F1 finding (Codex 2026-09-22): the prior code path
    `actor = req.params.get("actor") or x_user_id or "anonymous"`
    allowed a denied caller to spoof an allowed user by sending
    `params.actor = "spike-user-procurement"` in the request body. This
    bypassed the Permission Engine entirely.

    The fix is structural: the body is NEVER inspected for actor. If the
    header is missing, the call is anonymous — but anonymous callers go
    through the SAME permission path as any other user (they will be denied
    by default since `spec.denied_users` typically lists them).
    """
    return x_user_id or "anonymous"


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


def _wrap_spec_errors(fn):
    """cut-042R2 R2-F5 — wrap load_scenario_spec exceptions as DemoSpecError.

    Scoped to demo endpoints only; other FastAPI routes keep their native
    error semantics.
    """
    import functools

    @functools.wraps(fn)
    def _inner(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except FileNotFoundError as exc:
            raise DemoSpecError("scenario_not_found", str(exc)) from exc
        except ValueError as exc:
            msg = str(exc)
            kind = (
                "invalid_identifier"
                if "identifier" in msg.lower()
                or "path" in msg.lower()
                or "match" in msg.lower()
                else "invalid_scenario_spec"
            )
            raise DemoSpecError(kind, msg) from exc

    return _inner


@router.get("/domains", response_model=DomainsResponse)
def get_domains() -> DomainsResponse:
    """GET /api/v1/demo/domains — domain manifest.

    Per PRD §5: business-named domain list, no internal field leakage.
    """
    return DomainsResponse(domains=_discover_domains())


@router.post("/scenarios/generate")
@_wrap_spec_errors
def generate_scenario(
    req: GenerateScenarioRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> dict[str, Any]:
    """POST /api/v1/demo/scenarios/generate — live six-step loop run.

    Reads ScenarioSpec from `domain_packs/<req.domain>/scenarios/<req.scenario>.yaml`,
    invokes `run_demo_loop`, returns business-named JSON via `to_business`.

    Per PRD §5 #4: permission 反差 — denied users (per `spec.denied_users`)
    get conclusion = "no_permission" with zero side effect.
    """
    spec = load_scenario_spec(req.domain, req.scenario)

    # F1: actor strictly from X-User-Id (body MUST NOT override).
    actor = _resolve_actor(x_user_id)

    # cut-042R3 R3-B1 — reject negative quote_count at the API boundary.
    # The materializer silently clamps negative values to 0, but earlier in
    # the loop the rule still saw -1 (client value) and wrote evidence with
    # observed=-1, drifting from DB. Negative has no semantic meaning for
    # "number of quotes" — 422 here is the cleanest fix.
    if isinstance(req.params, dict) and "quote_count" in req.params:
        qc = req.params["quote_count"]
        if not isinstance(qc, int) or isinstance(qc, bool) or qc < 0:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"quote_count must be a non-negative integer, got {qc!r}"
                ),
            )

    engine = get_engine()

    # F2: default root_source_id from spec, not hardcoded.
    # Allow request to override via params.root_source_id for tests that need
    # to drive other fixtures, but never fall through to a procurement default.
    #
    # cut-043 — honor `spec.root_params_fields[0]` when present: packs whose
    # root entity is identified by a params field (e.g. KM's `policy_id`)
    # declare it in `root_params_fields`. The API then routes `params[policy_id]`
    # → root_source_id, so the rule layer sees the requested policy (not the
    # pack's `default_root_source_id` fallback).
    #
    # cut-043 — explicit 422 at the boundary for empty/missing OR path-unsafe
    # required params. Without this, the rule layer silently degrades on empty
    # policy_id / employee_id (the loop just sees an empty policy and runs the
    # rule with in_window=False / has_perm=False), which is a leaky abstraction.
    # Path-unsafe values (../etc) must also be refused — the spec loader only
    # validates pack/scenario names, not params values. Mirrors
    # `_check_safe_identifier` in spec.py.
    #
    # Opt-in: only enforce when the spec explicitly declares `route_root_via_params: true`
    # AND has at least one entry in `root_params_fields`. Procurement does NOT
    # declare this flag (its root is fixed as SPIKE-PR-001), so this gate MUST NOT
    # trigger there. KM sets the flag, opting in to params-driven routing.
    #
    # All declared params (root_params_fields + relations_fields) must be non-empty
    # safe identifiers — these are the schema the pack declares it needs to function.
    from ece.demo.spec import _SAFE_IDENTIFIER  # reuse the pack-name validator
    root_id_field_used: str | None = None
    if (
        isinstance(req.params, dict)
        and spec.route_root_via_params
        and bool(spec.root_params_fields)
    ):
        all_required: tuple[str, ...] = (*spec.root_params_fields, *spec.relations_fields)
        for required_field in all_required:
            raw = req.params.get(required_field)
            if not (isinstance(raw, str) and raw.strip()):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{required_field} is required and must be a non-empty "
                        f"string for pack={spec.pack!r} (route_root_via_params=true); "
                        f"got {raw!r}"
                    ),
                )
            if not _SAFE_IDENTIFIER.match(raw):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"{required_field} contains unsafe characters; must match "
                        f"{_SAFE_IDENTIFIER.pattern} "
                        f"(alphanumeric, dash, underscore only; "
                        f"reject path separators and '..'); got {raw!r}"
                    ),
                )
        root_id_field_used = spec.root_params_fields[0]

    root_source_id_from_params: str = ""
    if root_id_field_used:
        raw_root = req.params.get(root_id_field_used)
        if isinstance(raw_root, str) and raw_root.strip():
            root_source_id_from_params = raw_root.strip()

    root_source_id = str(
        req.params.get("root_source_id")
        or req.params.get("pr_source_id")
        or root_source_id_from_params
        or spec.default_root_source_id
    )
    if not root_source_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"root_source_id is required for pack={spec.pack!r} spec={spec.spec!r}; "
                f"either pass params.root_source_id or declare "
                f"spec.default_root_source_id in scenarios/{spec.spec}.yaml"
            ),
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


# ---------------------------------------------------------------------------
# cut-042R F5 — exception handlers live on the FastAPI `app`, not the router.
# See `src/ece/main.py` for `_install_demo_exception_handlers(app)` which the
# app calls after `app.include_router(demo_router)`.
# ---------------------------------------------------------------------------
