"""cut-042 — ScenarioSpec data model + YAML loader.

A ScenarioSpec is the **declarative wiring** of one six-step loop run: which
intent, which root entity, which subject (for Evidence), which rule to evaluate,
which decision_key to write back, plus cut-042R extensions for **generic**底座:
which business label, which source_system, which default root source id, and
which params fields should land back into the root entity's attributes.

The ContextSpec (`ece.context.spec`) is the **assembly-only** counterpart; both
coexist because they govern different stages of the pipeline.

Loader pattern follows `ece.context.spec.load_spec`: pack is the directory,
scenario is the file basename, YAML is loaded via the project's preferred
parser (ruamel-yaml or PyYAML — see `pyproject.toml`).

cut-042R F2/F5 changes:
  - ScenarioSpec now carries `label`, `source_system`, `default_root_source_id`,
    `root_params_fields`. These let the engine become pack-agnostic.
  - `load_scenario_spec` validates identifier safety BEFORE path resolution,
    rejecting `..`, `/`, `\\`, and empty strings with `ValueError`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["ScenarioSpec", "load_scenario_spec"]


# Safe-identifier pattern: alphanumeric, dash, underscore. cut-042R F5 mandates
# defensive validation against path traversal (`..`, `/`, `\`).
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class ScenarioSpec:
    """Pack-driven configuration for one `run_demo_loop` invocation.

    All fields are required except those with explicit defaults. The dataclass
    is `frozen=True` so the loop cannot mutate it mid-run — this protects the
    deterministic-byte-equal contract from accidental in-place edits.

    cut-042R new fields:
      - `label`: business-language domain label (替代 _DOMAIN_LABELS 硬编码)
      - `source_system`: 替代 v0/loop.py 模块常量 SPIKE_SOURCE_SYSTEM
      - `default_root_source_id`: 替代 api.py 硬编码 "SPIKE-PR-001"
      - `root_params_fields`: F3 — 哪些 params 字段应真实写回 root.attrs
    """

    pack: str
    spec: str
    root_entity: dict[str, Any]
    subject_entity_type: str
    rule_id: str
    decision_key: str
    # cut-042R F2/F3
    label: str = ""
    source_system: str = ""
    default_root_source_id: str = ""
    root_params_fields: tuple[str, ...] = ()
    # cut-042R2 R2-F2 — relations_fields declares which params drive relations
    # materialization (e.g. quote_count → SELECTS relations count).
    relations_fields: tuple[str, ...] = ()
    # cut-043 — explicit opt-in: when True, the API uses params[root_params_fields[0]]
    # as the root entity identifier (rather than `default_root_source_id`). KM pack
    # sets this; procurement does not (its root is fixed as SPIKE-PR-001).
    route_root_via_params: bool = False
    # cut-043R R5-B1 — server-owned temporal anchor. Packs that evaluate
    # "validity window" against `today` MUST declare this and the API will
    # inject the server anchor via params (never accept client-supplied `today`).
    requires_server_today_anchor: bool = False
    # cut-043R R5-B2 — explicit allowlist of decision_values that may have
    # ZERO evidence rows. Loop & update refuse to write a `review_status`
    # unless the value is on this list OR at least one evidence row exists.
    # Procurement: ["auto_approved"]. Knowledge: ["needs_valid_policy"].
    zero_evidence_decisions: tuple[str, ...] = ()
    # 既有
    params_schema: dict[str, Any] = field(default_factory=dict)
    denied_users: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


def _check_safe_identifier(name: str, kind: str) -> None:
    """cut-042R F5: validate identifier safety.

    Rejects `..`, `/`, `\\`, empty strings, and any character not in
    `[A-Za-z0-9_-]` BEFORE Path resolution. Without this check,
    `pack='../../etc'` becomes a real path that Path resolves silently.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(
            f"invalid {kind} identifier: must be non-empty string, got {name!r}"
        )
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"invalid {kind} identifier {name!r}: must match {_SAFE_IDENTIFIER.pattern} "
            f"(alphanumeric, dash, underscore only; reject path separators and '..')"
        )


def load_scenario_spec(pack: str, scenario: str) -> ScenarioSpec:
    """Load ScenarioSpec YAML for a given pack + scenario name.

    Path: ``src/ece/domain_packs/<pack>/scenarios/<scenario>.yaml``

    cut-042R F5: validates that `pack` and `scenario` are safe identifiers
    BEFORE Path resolution. This prevents path traversal attacks
    (pack='../../etc' → resolved to outside the domain_packs root).

    Raises:
        ValueError: identifier invalid OR required key missing.
        FileNotFoundError: YAML file does not exist at the resolved path
            (callers must map to 422).
        yaml.YAMLError: file is malformed.
    """
    _check_safe_identifier(pack, "pack")
    _check_safe_identifier(scenario, "scenario")

    yaml_path = Path(f"src/ece/domain_packs/{pack}/scenarios/{scenario}.yaml")
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"scenario spec not found: pack={pack!r} scenario={scenario!r}; "
            f"expected at {yaml_path}"
        )

    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"scenario spec root must be a mapping; got {type(raw).__name__}: {yaml_path!r}"
        )

    required = ("spec", "root_entity", "subject_entity_type", "rule_id", "decision_key")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(
            f"scenario spec {yaml_path!r} missing required keys: {missing}"
        )

    root_entity = raw["root_entity"]
    if not isinstance(root_entity, dict):
        raise ValueError(
            f"scenario spec {yaml_path!r}: root_entity must be a mapping, "
            f"got {type(root_entity).__name__}"
        )

    return ScenarioSpec(
        pack=pack,
        spec=raw["spec"],
        root_entity=root_entity,
        subject_entity_type=str(raw["subject_entity_type"]),
        rule_id=str(raw["rule_id"]),
        decision_key=str(raw["decision_key"]),
        # cut-042R F2
        label=str(raw.get("label") or ""),
        source_system=str(raw.get("source_system") or ""),
        default_root_source_id=str(raw.get("default_root_source_id") or ""),
        root_params_fields=tuple(raw.get("root_params_fields") or ()),
        # cut-042R2 R2-F2
        relations_fields=tuple(raw.get("relations_fields") or ()),
        # cut-043 — explicit opt-in flag for params-driven root routing.
        route_root_via_params=bool(raw.get("route_root_via_params") or False),
        # cut-043R R5-B1 — server-owned temporal anchor opt-in.
        requires_server_today_anchor=bool(
            raw.get("requires_server_today_anchor") or False
        ),
        # cut-043R R5-B2 — allowlist of decision_values that may have 0 evidence.
        zero_evidence_decisions=tuple(raw.get("zero_evidence_decisions") or ()),
        # 既有
        params_schema=dict(raw.get("params_schema") or {}),
        denied_users=list(raw.get("denied_users") or []),
        params=dict(raw.get("params") or {}),
    )
