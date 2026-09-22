# cut-044 — Compliance pack scenarios.
#
# Each Python module under this package is a single ScenarioSpec's runtime
# "anchor" — its top-level import statements trigger `register_rule(...)`
# side-effects in pack modules that import `ece.demo.registry`. The actual
# scenario YAML files live alongside this package as `.yaml` siblings.
#
# Mirrors `knowledge/scenarios/__init__.py` to keep the two packs
# structurally identical (PRD §5 底座泛化: "换域不换底座").

from ece.domain_packs.compliance.agent import v0_rules  # noqa: F401 (side-effect import)
