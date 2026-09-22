# cut-042 — Procurement domain pack scenarios.
#
# Each Python module under this package is a single ScenarioSpec's runtime
# "anchor" — its top-level import statements trigger `register_rule(...)`
# side-effects in pack modules that import `ece.demo.registry`. The actual
# scenario YAML files live alongside this package as `.yaml` siblings.
#
# Importing this package is the canonical way to make the procurement pack
# discoverable by the engine (`run_demo_loop` does NOT import this; it only
# reads the registry after another layer triggers registration).
#
# Runtime-only import of `agent.v0_rules` ensures that pack self-registration
# runs when this package is touched (e.g. by `_discover_domains` in
# `ece.demo.api` or by integration tests). grimp AST analysis does NOT see
# this `from .agent import v0_rules` as an engine→pack edge because it is
# inside the pack itself.

from ece.domain_packs.procurement.agent import v0_rules  # noqa: F401 (side-effect import)