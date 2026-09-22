"""cut-042 — Demo application layer.

Re-exports the generic loop, spec loader, and FastAPI router. The engine
(`src/ece/v0/loop.py`) and the procurement pack's `agent/v0_rules.py` are the
only producers / consumers — this package is wiring, not policy.
"""
from ece.demo.api import router as api_router
from ece.demo.loop import run_demo_loop
from ece.demo.registry import get_rule, list_rule_ids, register_rule
from ece.demo.spec import ScenarioSpec, load_scenario_spec

__all__ = [
    "ScenarioSpec",
    "api_router",
    "get_rule",
    "list_rule_ids",
    "load_scenario_spec",
    "register_rule",
    "run_demo_loop",
]
