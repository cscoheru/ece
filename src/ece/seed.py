"""S1.4 -- Seed entrypoint: chain S1.1 (Connectors) -> S1.2 (entity pipeline).

Idempotency contract:
- First run: created = N (initial seed)
- Re-run: created = 0 (all rows hit ON CONFLICT DO NOTHING)

Per ece/TASKS.md S1.4:
- Source: data/dataset/demo.json (S0.6 gen_dataset output)
- Source: data/sample/*.csv / *.json (Cline/seed custom data; not provided in S0.6)
- Strategy v0: seed from demo.json -> upsert entities (suppliers / purchase_requests / contracts / etc.)
- Future: S1.4R adds csv / json connectors reading from data/source/{connector_type}/
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity

# Map from gen_dataset top-level key -> entity_type (per PRD §27)
# Suppliers / PRs / Contracts / etc map directly; users / departments / policies / approval_records are derived
_DATASET_TO_ENTITY = {
    "suppliers": "supplier",
    "products": "product",
    "purchase_requests": "purchase_request",
    "contracts": "contract",
    "policies": "policy",
}


def seed_from_demo_json(engine, path: Path) -> dict[str, object]:
    """Seed entities from data/dataset/demo.json. Returns per-entity-type created/updated counts.

    Per S1.4 acceptance: created=0 on re-run (upsert idempotency).
    """
    if not path.exists():
        raise FileNotFoundError(f"demo dataset not found: {path} (run 'make gen-dataset' first)")

    raw = json.loads(path.read_text(encoding="utf-8"))
    counters: Counter[str] = Counter()
    skipped: list[dict[str, object]] = []

    for dataset_key, entity_type in _DATASET_TO_ENTITY.items():
        for idx, record in enumerate(raw.get(dataset_key, [])):
            # derive source_id from record id if present, else from name + index
            source_id = (
                str(record["id"]) if "id" in record else f"{entity_type}:{idx}"
            )
            name = record.get("name") or record.get("title")
            if not name:
                skipped.append({
                    "dataset_key": dataset_key,
                    "index": idx,
                    "reason": "missing name/title",
                })
                continue

            try:
                result = upsert_entity(
                    engine,
                    entity_type=entity_type,
                    name=name,
                    source_system=f"demo:{path.stem}",
                    source_id=source_id,
                    attributes=_strip_keys(record, {"id", "name", "title"}),
                )
                counters[entity_type] += 1 if result.created else 0
            except Exception as e:
                skipped.append({
                    "entity_type": entity_type,
                    "source_id": source_id,
                    "error": str(e),
                })

    return {"created_by_type": dict(counters), "skipped": skipped}


def _strip_keys(d: dict[str, object], keys: set[str]) -> dict[str, object]:
    """Strip given keys from dict for attributes JSONB."""
    return {k: v for k, v in d.items() if k not in keys}


def run_seed() -> dict[str, object]:
    """Entry: load demo.json, upsert all entities, return summary."""
    engine = get_engine()
    return seed_from_demo_json(engine, Path("data/dataset/demo.json"))


if __name__ == "__main__":
    import sys

    result = run_seed()
    created_by_type: dict[str, int] = result["created_by_type"]  # type: ignore[assignment]
    skipped_list: list[dict[str, object]] = result["skipped"]  # type: ignore[assignment]
    print(f"Seed complete: {created_by_type}")
    if skipped_list:
        print(f"Skipped: {len(skipped_list)}")
        for s in skipped_list[:5]:
            print(f"  {s}")
    sys.exit(0)
