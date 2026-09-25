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
    """Per-type FLOORS (KC-001 baseline), not an exact distribution.

    KC-001 §4.2 documented case=10, methodology=10, proposal_play=6,
    deliverable_template=4, risk_check=4, industry_note=2 as the *suggested*
    distribution of a 36-object corpus. Those numbers are a FLOOR here: the
    original `==` form also, by accident, forbade ever growing the catalogue
    (`sum(expected) == 36`), which is not what this test is for. Its real
    intent — "no type may be quietly starved or deleted" — is kept.

    OEI-011 raised the corpus to 45: case=13, methodology=10, proposal_play=6,
    deliverable_template=4, risk_check=6, industry_note=6 (see TASKS.md 附录 Q).
    """
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
        assert actual[t] >= n, (
            f"type={t!r}: expected at least {n} objects (KC-001 floor), got {actual[t]} "
            f"(full counts: {dict(actual)})"
        )
    # Self-consistency: the floors cannot between them exceed the corpus, or the
    # `>=` comparisons above would be vacuous against a shrinking catalogue.
    assert sum(expected.values()) <= len(catalog.objects), (
        f"the KC-001 floors sum to {sum(expected.values())} but the catalogue holds "
        f"only {len(catalog.objects)} objects"
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
