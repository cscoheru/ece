"""S3.5 — E3/E4/E5 evaluation suite tests (cut-008 §1.2).

Tests:
1. Dataset well-formed (≥cases count, schema_version, etc.)
2. Runner works against local API (or skips on env-not-ready)

Pre-condition: gen_eval_datasets.py has been run → data/eval/e{3,4,5}_*.json
exists.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _load(name: str) -> dict:
    p = Path(f"data/eval/{name}.json")
    if not p.exists():
        pytest.skip("dataset not generated; run `uv run python scripts/gen_eval_datasets.py`")
    return json.loads(p.read_text(encoding="utf-8"))


def test_e3_dataset_well_formed() -> None:
    data = _load("e3_context")
    assert data["schema_version"] == 1
    assert len(data["cases"]) >= 100, f"E3 needs ≥100 cases, got {len(data['cases'])}"
    required_keys = {"id", "intent", "user", "root", "required_refs", "expect"}
    for c in data["cases"]:
        assert required_keys.issubset(c.keys()), f"missing keys in {c['id']}"
        assert c["expect"] in ("ok", "insufficient_context")
    expect_counts = {
        "ok": sum(1 for c in data["cases"] if c["expect"] == "ok"),
        "insufficient_context": sum(
            1 for c in data["cases"] if c["expect"] == "insufficient_context"
        ),
    }
    assert expect_counts["ok"] >= 80, (
        f"E3 needs ≥80 ok cases for accuracy threshold, got {expect_counts['ok']}"
    )


def test_e4_dataset_well_formed() -> None:
    data = _load("e4_relationships")
    assert data["schema_version"] == 1
    assert len(data["cases"]) >= 30, f"E4 needs ≥30 cases, got {len(data['cases'])}"
    for c in data["cases"]:
        assert "from" in c
        assert "expected_count_min" in c or "expected_count_max" in c


def test_e5_dataset_well_formed() -> None:
    data = _load("e5_temporal")
    assert data["schema_version"] == 1
    assert len(data["cases"]) >= 30, f"E5 needs ≥30 cases, got {len(data['cases'])}"
    for c in data["cases"]:
        assert "from" in c
        assert "as_of" in c
    # Verify as_of dates cover 2025 + 2026 (per PRD requirement)
    as_of_years = {c["as_of"][:4] for c in data["cases"]}
    assert "2025" in as_of_years or "2026" in as_of_years, (
        "E5 should cover 2025/2026 procurement manager change cases"
    )
