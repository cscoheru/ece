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
import os
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

    # cut-043R R5-B1 — server-owned temporal anchor. Packs that declare
    # `requires_server_today_anchor: true` MUST receive `today` from the server,
    # not from `req.params.today`. The boundary:
    #   1. refuses any client-supplied `today` (422 — the client has no authority
    #      to rewrite the validity window)
    #   2. injects `params["today"] = <server_anchor>` so the rule layer can
    #      read it from `params` without code changes
    # The server anchor is read from `ECE_SERVER_TODAY_ANCHOR` env var, with
    # a fallback to today's date so dev / test environments work without
    # explicit configuration.
    #
    # cut-043R3 R7-B2 — anchor must be a valid ISO date. Codex R7 reproduced
    # that `ECE_SERVER_TODAY_ANCHOR=not-a-date` silently flowed through to the
    # rule layer, returning 200 with reason text containing "今日 not-a-date".
    # We now validate with `date.fromisoformat()` and 422 on failure so an
    # ops misconfig fails fast at the API boundary, not inside the rule.
    #
    # cut-043R4 R8-B1 — `date.fromisoformat()` accepts ISO 8601 forms other
    # than strict `YYYY-MM-DD`: e.g. `20260922` (basic format) and
    # `2026-W38-2` (ISO week date). Both would pass the R7-B2 check, then
    # silently enter business reason text as the operator-supplied raw
    # string (which would NOT match the parsed date's `isoformat()`). Codex
    # R8 reproduced this drift. The fix is a canonical round-trip check:
    # the parsed date's `isoformat()` MUST equal the raw input. This
    # rejects `20260922`, `2026-W38-2`, and any other non-`YYYY-MM-DD`
    # ISO form while still accepting the canonical date format.
    #
    # cut-043R4 R8-B1 (UTC vs local) — fallback is `date.today()` which
    # returns the **local** date, not UTC. The docstring previously said
    # "today's UTC date (canonical)" — that was wrong. In a single-host
    # demo server this is fine, but the comment now matches the actual
    # behavior. The `requires_server_today_anchor` opt-in exists precisely
    # so that production deployments set the env var explicitly and avoid
    # this local-time ambiguity.
    if spec.requires_server_today_anchor:
        if "today" in req.params:
            raise HTTPException(
                status_code=422,
                detail=(
                    "today is server-owned for pack="
                    f"{spec.pack!r} (requires_server_today_anchor=true); "
                    "do not pass params.today — server will inject the anchor"
                ),
            )
        from datetime import date
        raw_anchor = os.environ.get("ECE_SERVER_TODAY_ANCHOR")
        if raw_anchor is not None:
            try:
                parsed = date.fromisoformat(raw_anchor)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "ECE_SERVER_TODAY_ANCHOR must be a strict YYYY-MM-DD "
                        f"date, got {raw_anchor!r}; fix the env var or unset "
                        "it to fall back to today's local date"
                    ),
                ) from exc
            # R8-B1: canonical round-trip — the parsed date's `isoformat()`
            # MUST equal the raw input. This rejects ISO 8601 forms other
            # than strict `YYYY-MM-DD` (e.g. `20260922` basic format or
            # `2026-W38-2` week date) which `date.fromisoformat()` accepts
            # but which would silently flow into business reason text as a
            # different string than the parsed date represents.
            if parsed.isoformat() != raw_anchor:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "ECE_SERVER_TODAY_ANCHOR must be a strict YYYY-MM-DD "
                        f"date, got {raw_anchor!r} (parsed as {parsed.isoformat()!r}); "
                        "non-canonical ISO 8601 forms (basic, week-date, ordinal) "
                        "are not accepted to keep the value safe to embed in "
                        "business reason text"
                    ),
                )
            server_today = parsed.isoformat()
        else:
            server_today = date.today().isoformat()
        req.params["today"] = server_today

    # cut-044R2 R2-B1 / R2-B2 — spec-driven required-date validation.
    # Replaces the cut-044R1 R1-B1 trigger ("if caller sends EITHER period
    # field"). The R1 trigger was caller-behavior-driven and let the caller
    # silently omit BOTH period fields, bypassing validation; the rule
    # layer then returned 200/gap_list with zero-write but an invalid
    # audit request (R2-B1 finding).
    #
    # R2 fix: derive ALL date-field requirements from `spec.params_schema`.
    # Any date field declared in params_schema is REQUIRED (non-empty)
    # and MUST pass strict `YYYY-MM-DD` canonical round-trip. The block
    # covers three date fields:
    #   - period_start, period_end  (R2-B1: BOTH required)
    #   - today                      (R2-B2: caller-supplied, required when
    #                                 declared and pack is NOT server-anchored)
    #
    # Specs that declare NONE of these (e.g. procurement, knowledge) never
    # enter this block. The `requires_server_today_anchor=true` packs
    # already validated ECE_SERVER_TODAY_ANCHOR above and inject into
    # req.params["today"], so `today` is not caller-supplied for those
    # packs — this block treats that as "today is server-injected, skip".
    spec_declares_period = (
        "period_start" in spec.params_schema
        or "period_end" in spec.params_schema
    )
    spec_declares_today_caller_supplied = (
        "today" in spec.params_schema and not spec.requires_server_today_anchor
    )

    if spec_declares_period or spec_declares_today_caller_supplied:
        from datetime import date as _date

        # R2-B1: audit-period BOTH required + canonical + reversal check.
        if spec_declares_period:
            canonical_period: dict[str, str] = {}
            for _pfield in ("period_start", "period_end"):
                _raw = str(req.params.get(_pfield, "") or "")
                if not _raw:
                    # R2-B1: spec.params_schema declares this field →
                    # caller MUST supply it. Empty/missing = 422.
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"{_pfield} is required for pack={spec.pack!r} "
                            f"(declared in params_schema); got missing/empty"
                        ),
                    )
                try:
                    _parsed = _date.fromisoformat(_raw)
                except ValueError:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"{_pfield} must be strict YYYY-MM-DD, got {_raw!r}"
                        ),
                    ) from None
                # R8-B1 mirror: canonical round-trip — parsed.isoformat()
                # must equal raw input. Rejects basic `20260922`,
                # week-date `2026-W38-2`, ordinal `2026-265` etc.
                if _parsed.isoformat() != _raw:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"{_pfield} must be strict YYYY-MM-DD (canonical), "
                            f"got {_raw!r} (parsed as {_parsed.isoformat()!r}); "
                            "non-canonical ISO 8601 forms are not accepted to keep "
                            "the value safe to embed in business reason text"
                        ),
                    ) from None
                canonical_period[_pfield] = _raw
            if canonical_period["period_start"] > canonical_period["period_end"]:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"period_start ({canonical_period['period_start']!r}) "
                        f"must be <= period_end ({canonical_period['period_end']!r})"
                    ),
                )

        # R2-B2: today strict canonical round-trip (caller-supplied only).
        if spec_declares_today_caller_supplied:
            _raw = str(req.params.get("today", "") or "")
            if not _raw:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"today is required for pack={spec.pack!r} "
                        f"(declared in params_schema, caller-supplied); "
                        "got missing/empty"
                    ),
                )
            try:
                _parsed = _date.fromisoformat(_raw)
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"today must be strict YYYY-MM-DD, got {_raw!r}"
                    ),
                ) from None
            if _parsed.isoformat() != _raw:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"today must be strict YYYY-MM-DD (canonical), "
                        f"got {_raw!r} (parsed as {_parsed.isoformat()!r}); "
                        "non-canonical ISO 8601 forms are not accepted"
                    ),
                ) from None

    # cut-043R R5-B4 — when route_root_via_params is true, the routing field
    # is the SINGLE source of root identity. The legacy `root_source_id` /
    # `pr_source_id` overrides MUST be rejected (they would silently route
    # to a different entity, defeating the validation we just did).
    if spec.route_root_via_params and (
        "root_source_id" in req.params or "pr_source_id" in req.params
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"root_source_id / pr_source_id overrides are forbidden when "
                f"route_root_via_params=true (pack={spec.pack!r}); the routing "
                f"field {spec.root_params_fields[0]!r} is the single source of root identity"
            ),
        )

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
