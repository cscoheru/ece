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

from sqlalchemy import text

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
    {
        # cut-040R-2 R40R2.3: dedicated admin/ingestion identity.
        #
        # POST /entities is gated on `is_management or "admin" in roles`. The
        # three users above must NOT be management — the six
        # management-classification E2 cases all expect deny — so the ingestion
        # tests cannot borrow them any more. Before R40R2.3 they "worked" only
        # because `is_management` was derived from the substring "manager" in
        # "procurement_manager", i.e. they depended on the bug.
        #
        # This user is deliberately NOT management (admin ≠ management); it is
        # authorized via the explicit "admin" role, and it appears in no E2 case.
        "source_id": "demo-user-admin",
        "name": "Demo Admin",
        "department": "it",
        "roles": ["admin"],
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

    # cut-040R-2 R40R2.1 (RC-6 — 状态洗库): the department injection lives
    # INSIDE this function so the idempotent replay self-heals. Previously it
    # was only called from run_seed(), so any test that wipes `demo:%`
    # entities and replays seed_from_demo_json (e.g.
    # test_s14_seed_idempotent) destroyed attributes.department and never
    # restored it — E2 then measured a scrubbed DB, neutralizing R40.1c.
    dept_updated = _seed_entity_departments(engine)

    return {
        "created_by_type": dict(counters),
        "skipped": skipped,
        "attributes_department_updated": dept_updated,
    }


def seed_acl_entries(engine) -> dict[str, int]:
    """cut-040 R40.1a: seed acl_entries rows for E2 explicit-acl cases.

    3 rows (e2-059 allow, e2-060 allow, e2-061 deny) — match
    data/eval/e2_permission.json 'acl_explicit' category. Idempotent via
    source_system tag ('demo:cut-040-test-acl').

    Closes cut-039 R39.1 根因三连 #1: acl_entries 表 0 行。
    """

    rows = [
        # cut-040R-2 R40R2.2 (RC-9 — ACL 全域哑弹): object_type MUST use the
        # dataset's DOMAIN vocabulary. The API prefetches ACLs with
        # `WHERE object_type = :otype` and every E2 case passes a domain type
        # (purchase_request / supplier / contract) — never 'entity'. The
        # previous 'entity' rows were therefore dead in E2: e2-059/060/061
        # never saw their own ACL.
        #
        # cut-040R-2 R40R2.4 (RC-7 — dataset self-contradiction): e2-060 and
        # e2-061 use DEDICATED objects. An ACL row is keyed on
        # (subject, object) only, so sharing an object with a classification
        # case makes the expectations unsatisfiable:
        #   - e2-060 (finance, PR001, department, ALLOW) vs e2-010/049
        #     (finance, PR001, department, DENY) — same triple, opposite want
        #   - e2-061 (procurement, CON001, confidential, DENY) vs e2-021
        #     (procurement, CON001, confidential, ALLOW) — same triple
        # Dedicated objects PR003 / CON002 are referenced by no other E2 case.
        # e2-059 is safe: SUP052 has no conflicting classification case.
        {
            "subject_type": "user",
            "subject_ref": "demo-user-procurement",
            "object_type": "supplier",
            "object_ref": "SUP052",
            "effect": "allow",
        },
        {
            "subject_type": "user",
            "subject_ref": "demo-user-finance",
            "object_type": "purchase_request",
            "object_ref": "PR003",  # dedicated (R40R2.4)
            "effect": "allow",
        },
        {
            "subject_type": "user",
            "subject_ref": "demo-user-procurement",
            "object_type": "contract",
            "object_ref": "CON002",  # dedicated (R40R2.4)
            "effect": "deny",
        },
    ]
    counters: Counter[str] = Counter()
    tag = "demo:cut-040-test-acl"
    with engine.begin() as conn:
        # cut-040R-2 R40R2.2: DELETE-then-INSERT instead of ON CONFLICT DO
        # NOTHING. The object_type vocabulary changed ('entity' → domain types),
        # and the old rows would survive an ON CONFLICT insert as dead duplicates
        # — still filtering to zero hits but polluting the table. Delete is
        # scoped to this seed's own tag so no other ACL row is touched.
        deleted = conn.execute(
            text("DELETE FROM acl_entries WHERE source_system = :tag"),
            {"tag": tag},
        ).rowcount
        counters["replaced"] += deleted
        for r in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO acl_entries
                      (subject_type, subject_ref, object_type, object_ref, effect, source_system)
                    VALUES (:subject_type, :subject_ref, :object_type, :object_ref, :effect, :source_system)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {**r, "source_system": tag},
            )
            counters["created"] += 1
    return dict(counters)


def _seed_entity_departments(engine) -> int:
    """cut-040 R40.1c: post-seed UPDATE injects attributes.department
    for entities referenced in e2_permission.json 'department' classification
    cases with expected_allowed=True. Closes cut-039 R39.1 根因三连 #3:
    entities.attributes.department 为 NULL → 17 expected-allow 反向失败.

    Uses `||` jsonb merge to preserve existing keys; WHERE clause limits
    to entities with no existing department (idempotent).
    """
    dept_by_entity: dict[str, str] = {
        # entity_type → default dept (matches _object_dept prefix_map in
        # permissions/engine.py:168-211; keeps seed & engine consistent)
        "supplier": "procurement",
        "purchase_request": "procurement",
        # e2-021: finance allowed PR via ownership-of-PR; CON001 referenced
        # by e2-061 (procurement DENIED via acl_explicit). For default
        # department check (e.g. e2-009 dept allowed) we map contracts to
        # procurement too — the explicit ACL on CON001 still wins.
        "contract": "procurement",
        "policy": "procurement",
        "document": "procurement",
        "product": "procurement",
    }
    total = 0
    with engine.begin() as conn:
        for entity_type, dept in dept_by_entity.items():
            # Skip the WHERE filter for empty jsonb (avoids 'IndeterminateDatatype'
            # from `->>` on {}). `||` is idempotent — overwrites 'department' key
            # with same value if already present. Cheap since each entity_type has
            # <200 rows. Idempotency: re-running `make seed` is safe.
            result = conn.execute(
                text(
                    """
                    UPDATE entities
                    SET attributes = COALESCE(attributes, '{}'::jsonb) || jsonb_build_object('department', CAST(:dept AS text))
                    WHERE entity_type = :etype
                    """
                ),
                {"etype": entity_type, "dept": dept},
            )
            total += result.rowcount
    return total


def run_seed() -> dict[str, object]:
    """Entry: load demo.json, upsert all entities, return summary.

    cut-040 additions:
    - _seed_entity_departments() injects attributes.department per entity_type
      (R40.1c) — now called from INSIDE seed_from_demo_json (R40R2.1) so the
      idempotent replay self-heals
    - seed_acl_entries() seeds 3 acl_entries for E2 'acl_explicit' cases
      (R40.1a)
    """
    engine = get_engine()
    out = seed_from_demo_json(engine, Path("data/dataset/demo.json"))
    users = seed_test_users(engine)
    out["test_users"] = users
    # cut-040R-2 R40R2.1: attributes.department is now injected inside
    # seed_from_demo_json (out["attributes_department_updated"]), so it is not
    # re-injected here.
    # cut-040 R40.1a: seed 3 acl_entries for E2 explicit-acl cases
    out["acl_entries"] = seed_acl_entries(engine)
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
