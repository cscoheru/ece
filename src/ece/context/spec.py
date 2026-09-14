"""S3.1 Context Specification loader.

Per ARCHITECTURE §2.1 / PRD §40-41:
  Each domain task declares its Required Context as YAML, stored in the
  domain pack's context_specs/ directory. Runtime loads + parses into a
  typed model (Pydantic v2). Versioned for backward compatibility.

Spec structure (matches ARCHITECTURE §2.1 example):
  spec: evaluate_purchase_request
  version: 1
  root_entity: purchase_request
  requires:
    user: true
    entities:
      - {type: supplier, via: "SELECTS", max_hops: 1}
    relationships: [SUBMITTED_BY, BELONGS_TO, SELECTS, ...]
    documents:
      - {doc_type: procurement_policy, match: "..."}
    structured_data:
      - historical_purchase
  temporal: {mode: current}
  limits: {max_entities: 60, max_chunks: 30, max_rows: 200}
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class RequiredEntity(BaseModel):
    type: str
    via: str = ""  # relation path; "" = direct entity
    max_hops: int = Field(default=1, ge=1, le=10)


class RequiredDocument(BaseModel):
    doc_type: str
    match: str = ""  # free-text match rule


class TemporalSpec(BaseModel):
    mode: str = "current"  # current | as_of | between
    as_of: date | None = None
    between_from: date | None = None
    between_to: date | None = None

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        if v not in ("current", "as_of", "between"):
            raise ValueError(
                f"temporal.mode must be one of current|as_of|between, got {v!r}"
            )
        return v


class LimitsSpec(BaseModel):
    max_entities: int = Field(default=50, ge=1, le=1000)
    max_relationships: int = Field(default=100, ge=1, le=5000)
    max_chunks: int = Field(default=30, ge=1, le=1000)
    max_rows: int = Field(default=200, ge=1, le=10000)


class RequiresBlock(BaseModel):
    user: bool = False
    entities: list[RequiredEntity] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    documents: list[RequiredDocument] = Field(default_factory=list)
    structured_data: list[str] = Field(default_factory=list)


class ContextSpec(BaseModel):
    spec: str  # intent name (e.g., "evaluate_purchase_request")
    version: int = 1
    root_entity: str = ""
    requires: RequiresBlock = Field(default_factory=RequiresBlock)
    temporal: TemporalSpec = Field(default_factory=TemporalSpec)
    limits: LimitsSpec = Field(default_factory=LimitsSpec)


def load_spec(pack: str, intent: str) -> ContextSpec:
    """Load Context Spec YAML for the given domain pack + intent.

    Path resolution: caller must run from repo root (cwd = ece/).
    Looks for: src/ece/domain_packs/<pack>/context_specs/<intent>.yaml

    Raises:
        FileNotFoundError: if YAML file does not exist
        pydantic.ValidationError: if YAML is malformed
    """
    yaml_path = Path(f"src/ece/domain_packs/{pack}/context_specs/{intent}.yaml")
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"context spec not found: pack={pack!r} intent={intent!r}; "
            f"expected at {yaml_path}"
        )
    return load_spec_from_path(yaml_path)


def load_spec_from_path(yaml_path: Path) -> ContextSpec:
    """Load and validate Context Spec from an explicit YAML path."""
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"context spec YAML must be a mapping at top level, got {type(raw).__name__}"
        )
    return ContextSpec(**raw)
