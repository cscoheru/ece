"""S5 (V0 Technical Spike) — loop orchestrator.

Re-exports the public API for `ece.v0.loop` so callers can write
`from ece.v0 import run_v0_loop, V0LoopResult`.
"""
from __future__ import annotations

from ece.v0.loop import V0LoopResult, run_v0_loop

__all__ = ["V0LoopResult", "run_v0_loop"]
