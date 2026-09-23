"""KC-001 — Consulting seed schema binding tests.

Per `docs/demo-platform/CONSULTING_CONTEXT_KERNEL_KC001_TASK.md` §4.1:
the bundled JSON seed must parse cleanly, every record must conform to the
KnowledgeObject Pydantic schema (enums + list fields), and no record may
have duplicate ids. These tests gate "the seed is loadable and well-typed"
without requiring the FastAPI app to be running.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ece.consulting.models import KnowledgeObject
from ece.consulting.service import ConsultingCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "src" / "ece" / "consulting" / "seed" / "consulting_objects.json"


@pytest.fixture(scope="module")
def seed_raw() -> list[dict]:
    if not SEED_PATH.exists():
        pytest.fail(f"Consulting seed bundle missing at {SEED_PATH}")
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def seed_objects(seed_raw: list[dict]) -> list[KnowledgeObject]:
    return [KnowledgeObject(**item) for item in seed_raw]


def test_seed_bundle_is_valid_json() -> None:
    """The seed file must parse as JSON (UTF-8)."""
    assert SEED_PATH.exists(), f"missing {SEED_PATH}"
    text = SEED_PATH.read_text(encoding="utf-8")
    parsed = json.loads(text)
    assert isinstance(parsed, list), f"seed root must be a JSON array, got {type(parsed)}"


def test_every_seed_record_passes_pydantic_schema(seed_raw: list[dict]) -> None:
    """Every record must conform to KnowledgeObject (Pydantic v2 enforces enums)."""
    for i, item in enumerate(seed_raw):
        try:
            KnowledgeObject(**item)
        except Exception as exc:  # noqa: BLE001 — binding: surface any pydantic error
            pytest.fail(f"seed[{i}]={item.get('id')!r} failed schema: {exc}")


def test_type_enum_is_exactly_one_of_six(seed_objects: list[KnowledgeObject]) -> None:
    """Every type value must be one of the six documented KnowledgeObject types."""
    allowed = {"case", "methodology", "proposal_play", "deliverable_template", "risk_check", "industry_note"}
    for o in seed_objects:
        assert o.type in allowed, (
            f"{o.id!r} has unexpected type={o.type!r}; allowed={sorted(allowed)}"
        )


def test_source_origin_enum_is_exactly_one_of_four(seed_objects: list[KnowledgeObject]) -> None:
    allowed = {"founder_case", "methodology_note", "synthetic_variant", "licensed_public"}
    for o in seed_objects:
        assert o.source_origin in allowed, (
            f"{o.id!r} has source_origin={o.source_origin!r}; allowed={sorted(allowed)}"
        )


def test_required_text_fields_are_nonempty(seed_objects: list[KnowledgeObject]) -> None:
    """title / summary must be non-empty (business-facing content gate)."""
    for o in seed_objects:
        assert o.title.strip(), f"{o.id!r} has empty title"
        assert o.summary.strip(), f"{o.id!r} has empty summary"


def test_catalog_can_load_seed_without_error() -> None:
    """ConsultingCatalog.from_seed_path() must succeed on the bundled seed."""
    catalog = ConsultingCatalog.from_seed_path()
    assert len(catalog.objects) >= 1, "catalog must hold at least one object"
    # Every object must be retrievable via .get(id)
    for o in catalog.objects:
        assert catalog.get(o.id) is o, f"get({o.id!r}) must return the original object"
