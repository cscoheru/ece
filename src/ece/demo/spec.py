"""cut-042 — ScenarioSpec data model + YAML loader.

A ScenarioSpec is the **declarative wiring** of one six-step loop run: which
intent, which root entity, which subject (for Evidence), which rule to
evaluate, and which decision_key to write back. The ContextSpec
(`ece.context.spec`) is the **assembly-only** counterpart; both coexist
because they govern different stages of the pipeline.

Loader pattern follows `ece.context.spec.load_spec`: pack is the directory,
scenario is the file basename, YAML is loaded via the project's preferred
parser (ruamel-yaml or PyYAML — see `pyproject.toml`).

Per cut-042 PRD §5 #1: subject_entity_type / rule_id / intent are read from
spec, never hardcoded. Per cut-042 PRD §7: no LLM, deterministic pure load.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["ScenarioSpec", "load_scenario_spec"]


@dataclass(frozen=True)
class ScenarioSpec:
    """Pack-driven configuration for one `run_demo_loop` invocation.

    All fields are required except `params` (which defaults to empty).
    The dataclass is `frozen=True` so the loop cannot mutate it mid-run —
    this protects the deterministic-byte-equal contract from accidental
    in-place edits.
    """

    pack: str
    spec: str
    root_entity: dict[str, Any]
    subject_entity_type: str
    rule_id: str
    decision_key: str
    params_schema: dict[str, Any] = field(default_factory=dict)
    denied_users: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)


def load_scenario_spec(pack: str, scenario: str) -> ScenarioSpec:
    """Load ScenarioSpec YAML for a given pack + scenario name.

    Path: ``src/ece/domain_packs/<pack>/scenarios/<scenario>.yaml``

    Raises:
        FileNotFoundError: YAML file does not exist at the resolved path.
        ValueError: required key missing or wrong shape.
        yaml.YAMLError: file is malformed.
    """
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
        params_schema=dict(raw.get("params_schema") or {}),
        denied_users=list(raw.get("denied_users") or []),
        params=dict(raw.get("params") or {}),
    )
