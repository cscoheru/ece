"""Content engine selector — ECE_CONTENT_ENGINE=onyx|mock (OEI-003 §4 步骤 3).

Default is `mock` so /engine/status and any caller works without a live engine
(CI / demos on a fresh laptop). Onyx requires ECE_ONYX_COOKIE_FILE to be readable.
"""
from __future__ import annotations

import os

from ece.connectors.onyx.mock_adapter import MockContentEngineAdapter
from ece.connectors.onyx.onyx_adapter import OnyxContentEngineAdapter
from ece.connectors.onyx.port import ContentEnginePort


def get_content_engine() -> ContentEnginePort:
    """Build the configured content engine adapter (singleton-ish — fresh per call).

    Selection via env:
      ECE_CONTENT_ENGINE=onyx  → OnyxContentEngineAdapter (real)
      ECE_CONTENT_ENGINE=mock  → MockContentEngineAdapter (default)
    """
    which = (os.environ.get("ECE_CONTENT_ENGINE") or "mock").lower()
    if which == "onyx":
        return OnyxContentEngineAdapter()
    if which == "mock":
        return MockContentEngineAdapter()
    # unknown value → fall back to mock (fail-soft)
    return MockContentEngineAdapter()
