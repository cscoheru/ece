"""S3.1 — Context Spec loader unit tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ece.context.spec import (
    ContextSpec,
    LimitsSpec,
    RequiredEntity,
    TemporalSpec,
    load_spec,
    load_spec_from_path,
)


def test_load_spec_evaluate_purchase_request() -> None:
    spec = load_spec("procurement", "evaluate_purchase_request")
    assert isinstance(spec, ContextSpec)
    assert spec.spec == "evaluate_purchase_request"
    assert spec.version == 1
    assert spec.root_entity == "purchase_request"
    assert spec.requires.user is True
    # Required entities covers supplier + contract + product + policy + approval
    types = {e.type for e in spec.requires.entities}
    assert {"supplier", "contract", "product", "policy", "approval"}.issubset(types)
    # Relationships list covers 7 standard procurement relations
    rels = set(spec.requires.relationships)
    assert {"SUBMITTED_BY", "BELONGS_TO", "SELECTS", "HAS_CONTRACT",
            "CONTAINS", "SUBJECT_TO", "HAS_APPROVAL"}.issubset(rels)
    # Temporal + limits defaults
    assert spec.temporal.mode == "current"
    assert spec.limits.max_entities == 60
    assert spec.limits.max_relationships == 100


def test_load_spec_unknown_intent_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_spec("procurement", "does_not_exist_intent_xyz")


def test_load_spec_unknown_pack_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_spec("no_such_pack", "anything")


def test_spec_temporal_mode_validation() -> None:
    with pytest.raises(ValidationError):
        TemporalSpec(mode="invalid_mode")  # not in {current, as_of, between}


def test_spec_required_entity_max_hops_bounds() -> None:
    with pytest.raises(ValidationError):
        RequiredEntity(type="supplier", max_hops=0)  # ge=1 violated
    with pytest.raises(ValidationError):
        RequiredEntity(type="supplier", max_hops=11)  # le=10 violated


def test_spec_limits_bounds() -> None:
    with pytest.raises(ValidationError):
        LimitsSpec(max_entities=0)  # ge=1 violated
    spec = LimitsSpec(max_entities=50, max_relationships=100)
    assert spec.max_entities == 50
    assert spec.max_relationships == 100


def test_load_spec_from_path_invalid_yaml_raises() -> None:
    """Validation errors surface from Pydantic, not YAML."""
    import tempfile
    from pathlib import Path

    import yaml as _yaml

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        # missing 'spec' field → ContextSpec(**raw) fails
        _yaml.safe_dump({"version": 1}, f)
        path = Path(f.name)
    try:
        with pytest.raises(ValidationError):
            load_spec_from_path(path)
    finally:
        path.unlink()
