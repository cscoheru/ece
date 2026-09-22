"""cut-042 spec + registry direct-drive suite.

Loads ScenarioSpec YAML and exercises the rule registry directly without going
through FastAPI. Per cut-042 acceptance #5 (test-first), these tests are RED
before the implementation commit and GREEN after.
"""
from __future__ import annotations

import importlib

import pytest


def test_procurement_default_scenario_loads_with_required_keys() -> None:
    """load_scenario_spec('procurement', 'default') → frozen dataclass 必备字段齐备.

    Per PRD §5 #1: spec 注入 subject_entity_type / rule_id / decision_key /
    intent_name / root_entity. registry 反查必须命中.
    """
    from ece.demo.spec import load_scenario_spec

    spec = load_scenario_spec("procurement", "default")

    assert spec.pack == "procurement", f"pack mismatch: {spec.pack!r}"
    assert spec.spec == "evaluate_purchase_request", f"spec mismatch: {spec.spec!r}"
    assert spec.subject_entity_type == "purchase_request", \
        f"subject_entity_type mismatch: {spec.subject_entity_type!r}"
    assert spec.rule_id == "R-SPIKE-REVIEW", \
        f"rule_id mismatch: {spec.rule_id!r}"
    assert spec.decision_key == "review_status", \
        f"decision_key mismatch: {spec.decision_key!r}"
    # frozen dataclass guarantees immutability (cut-042 scope: spec is config,
    # not mutable runtime state).
    with pytest.raises((AttributeError, Exception)):
        spec.rule_id = "mutated"  # type: ignore[misc]


def test_registry_resolves_R_SPIKE_REVIEW_after_pack_import() -> None:
    """Pack 导入后 registry.list_rule_ids() 包含 'R-SPIKE-REVIEW'.

    Per cut-042 §3b: pack 自注册机制. importlib.import_module 触发 pack 的
    scenarios init → register_rule(...) → _REGISTRY 注入. 这同时证明 pack
    模块的 side-effect registration 流程闭环.
    """
    # Touch the demo package so registry is reachable.
    import ece.demo.registry as registry

    # Trigger procurement pack import (runtime, not static — keeps lint-imports
    # 2 kept contract unbroken).
    importlib.import_module("ece.domain_packs.procurement.scenarios")

    rule_ids = registry.list_rule_ids()
    assert "R-SPIKE-REVIEW" in rule_ids, \
        f"R-SPIKE-REVIEW not registered after pack import: {rule_ids!r}"

    descriptor = registry.get_rule("R-SPIKE-REVIEW")
    assert descriptor.rule_id == "R-SPIKE-REVIEW"
    assert descriptor.decision_key == "review_status"
    # evaluate_fn is callable; signature is intentionally generic.
    assert callable(descriptor.evaluate_fn)
    # build_decision_fn is callable.
    assert callable(descriptor.build_decision_fn)


def test_registry_rejects_duplicate_rule_id() -> None:
    """register_rule 二次同 id 注册必须报错 (不允许静默覆盖).

    Per cut-042 §3b: duplicate registration raises ValueError to surface
    packaging bugs immediately, not at first call.
    """
    import ece.demo.registry as registry

    def _dummy_eval(ctx, params):  # pragma: no cover - replaced by real fn
        return []

    def _dummy_build(conditions, ctx):  # pragma: no cover - replaced by real fn
        return {}

    registry.register_rule(
        "R-DUPLICATE-TEST",
        decision_key="x",
        evaluate_fn=_dummy_eval,
        build_decision_fn=_dummy_build,
    )
    try:
        with pytest.raises(ValueError, match="duplicate"):
            registry.register_rule(
                "R-DUPLICATE-TEST",
                decision_key="x",
                evaluate_fn=_dummy_eval,
                build_decision_fn=_dummy_build,
            )
    finally:
        registry._REGISTRY.pop("R-DUPLICATE-TEST", None)  # cleanup


def test_registry_get_unknown_rule_raises_keyerror() -> None:
    """get_rule(unknown) → KeyError (不允许 None 静默通过)."""
    import ece.demo.registry as registry

    with pytest.raises(KeyError):
        registry.get_rule("R-NEVER-REGISTERED-XYZ")
