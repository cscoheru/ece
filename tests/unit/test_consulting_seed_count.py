"""KC-001 — Consulting seed count + type/source distribution binding tests.

Per Task §4.2 the bundled seed must contain at least 36 knowledge objects
with a documented type distribution (10 case + 10 methodology + 6
proposal_play + 4 deliverable_template + 4 risk_check + 2 industry_note)
and a varied source_origin distribution covering at least three of the
four documented origins.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from ece.consulting.service import ConsultingCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "src" / "ece" / "consulting" / "seed" / "consulting_objects.json"


@pytest.fixture(scope="module")
def catalog() -> ConsultingCatalog:
    return ConsultingCatalog.from_seed_path(SEED_PATH)


def test_total_object_count_meets_minimum(catalog: ConsultingCatalog) -> None:
    """Task §4.2: ≥ 36 knowledge objects. Anything less is a content shortfall."""
    assert len(catalog.objects) >= 36, (
        f"need ≥ 36 seed objects; got {len(catalog.objects)}"
    )


def test_type_distribution_matches_documented_targets(catalog: ConsultingCatalog) -> None:
    """Per-type distribution: case=10, methodology=10, proposal_play=6,
    deliverable_template=4, risk_check=4, industry_note=2 (exact)."""
    expected = {
        "case": 10,
        "methodology": 10,
        "proposal_play": 6,
        "deliverable_template": 4,
        "risk_check": 4,
        "industry_note": 2,
    }
    actual = Counter(o.type for o in catalog.objects)
    for t, n in expected.items():
        assert actual[t] == n, (
            f"type={t!r}: expected {n} objects, got {actual[t]} "
            f"(full counts: {dict(actual)})"
        )


def test_source_origin_covers_at_least_three_distinct_values(catalog: ConsultingCatalog) -> None:
    """Variety check: at least three distinct source_origin values appear.
    Defends against accidentally mono-sourcing the seed (e.g. all synthetic)."""
    origins = {o.source_origin for o in catalog.objects}
    assert len(origins) >= 3, (
        f"need ≥ 3 distinct source_origin values; got {sorted(origins)}"
    )


def test_no_duplicate_object_ids(catalog: ConsultingCatalog) -> None:
    """Object id is the primary key — duplicates would shadow detail lookups."""
    ids = [o.id for o in catalog.objects]
    counts = Counter(ids)
    dupes = [i for i, n in counts.items() if n > 1]
    assert not dupes, f"duplicate ids in seed: {dupes}"
