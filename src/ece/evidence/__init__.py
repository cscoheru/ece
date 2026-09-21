"""Evidence store — the Kernel's business-evidence persistence (V0 spike: S2).

See `store.py` for the scope lock and the reasoning behind keeping Business Evidence
separate from engineering audit.
"""
from __future__ import annotations

from ece.evidence.store import get_evidence_for_decision, persist_evidence

__all__ = ["get_evidence_for_decision", "persist_evidence"]
