"""S1.4 -- Seed entrypoint: chain S1.1 (Connectors) -> S1.2 (entity pipeline).

Idempotency contract:
- First run: created = N (initial seed)
- Re-run: created = 0 (all rows hit ON CONFLICT DO NOTHING)

Per ece/TASKS.md S1.4:
- Source: data/dataset/demo.json (S0.6 gen_dataset output)
- Strategy v0: seed from demo.json -> upsert entities (suppliers / products / purchase_requests / contracts / policies)
- Demo.json record shapes (per S0.6 gen_dataset):
  - suppliers / products / policies: list[str] (name only)
  - purchase_requests / contracts: list[dict] (id + fields)
  - Generic record handler: dict has .get(); str is the name; dict without name falls back to id.

B4 fix (cut-005 Cline review): seed.py no longer assumes dict records.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity

# Map from gen_dataset top-level key -> entity_type (per PRD §27).
# Some lists contain str (name only), others contain dict (id + fields).
_DATASET_TO_ENTITY = {
    "suppliers": "supplier",
    "products": "product",
    "purchase_requests": "purchase_request",
    "contracts": "contract",
    "policies": "policy",
}


def _normalize_record(record: object, idx: int, entity_type: str) -> tuple[str | None, str, dict[str, object]]:
    """Return (name, source_id, attributes) from a heterogeneous record.

    - str: name = record, source_id = f"{entity_type}:{idx}", attributes = {}
    - dict: name = record.get("name") or record.get("title") or str(record.get("id", idx))
      source_id = str(record.get("id", f"{entity_type}:{idx}"))
      attributes = record minus id/name/title
    - other: rejected (name=None)

    Per ece/TASKS.md S1.2: provenance fields source_system/source_ref are
    stored separately (not in attributes); the entity_type prefix in
    source_id avoids collisions when the same name appears in different
    entity_type lists.
    """
    if isinstance(record, str):
        name = record.strip() if record else ""
        if not name:
            return (None, "", {})
        return (name, f"{entity_type}:{idx}", {})

    if not isinstance(record, dict):
        return (None, "", {})

    rid = record.get("id", f"{entity_type}:{idx}")
    name = (
        record.get("name")
        or record.get("title")
        or (str(rid) if rid is not None else f"{entity_type}:{idx}")
    )
    name_str = str(name).strip() if name is not None else ""
    if not name_str:
        return (None, "", {})
    src_id = str(rid) if rid is not None else f"{entity_type}:{idx}"
    attrs = {k: v for k, v in record.items() if k not in ("id", "name", "title")}
    return (name_str, src_id, attrs)


# R1 (cut-006): seed a known test user with X-User-Id 'demo-user-procurement'
# so permission filter tests have a known identity to resolve.
_TEST_USERS: list[dict[str, str | list[str]]] = [
    {
        "source_id": "demo-user-procurement",
        "name": "Demo Procurement Manager",
        "department": "procurement",
        "roles": ["procurement_manager", "buyer"],
    },
    {
        "source_id": "demo-user-finance",
        "name": "Demo Finance Manager",
        "department": "finance",
        "roles": ["finance_manager"],
    },
    {
        "source_id": "demo-user-engineering",
        "name": "Demo Engineering Manager",
        "department": "sales",  # 'sales' dept; not procurement/finance
        "roles": ["buyer"],
    },
]


def seed_test_users(engine) -> dict[str, int]:
    """Seed a few known test users so permission tests have identities to resolve."""
    from ece.identity.parser import upsert_identity

    counters: Counter[str] = Counter()
    for u in _TEST_USERS:
        # Typed locals to satisfy mypy (dict[str, str|list[str]] union)
        user_id: str = str(u["source_id"])
        user_name: str = str(u["name"])
        user_dept: str = str(u["department"])
        user_roles: list[str] = list(u["roles"]) if isinstance(u["roles"], list) else []
        display_id = upsert_identity(
            engine,
            x_user_id=user_id,
            name=user_name,
            department=user_dept,
            roles=user_roles,
        )
        if display_id:
            counters["person"] += 1
    return dict(counters)


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
            name, source_id, attrs = _normalize_record(record, idx, entity_type)
            if name is None:
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
                    attributes=attrs,
                )
                counters[entity_type] += 1 if result.created else 0
            except Exception as e:
                skipped.append({
                    "entity_type": entity_type,
                    "source_id": source_id,
                    "error": str(e),
                })

    return {"created_by_type": dict(counters), "skipped": skipped}


def run_seed() -> dict[str, object]:
    """Entry: load demo.json, upsert all entities, return summary."""
    engine = get_engine()
    out = seed_from_demo_json(engine, Path("data/dataset/demo.json"))
    users = seed_test_users(engine)
    out["test_users"] = users
    return out


if __name__ == "__main__":
    import sys

    result = run_seed()
    created_by_type: dict[str, int] = result["created_by_type"]  # type: ignore[assignment]
    skipped_list: list[dict[str, object]] = result["skipped"]  # type: ignore[assignment]
    print(f"Seed complete: {created_by_type}")
    print(f"Total created: {sum(created_by_type.values())}")
    print(f"Total skipped: {len(skipped_list)}")
    if skipped_list:
        for s in skipped_list[:5]:
            print(f"  skipped: {s}")
    sys.exit(0)
