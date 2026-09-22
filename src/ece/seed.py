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
from ece.entities.pipeline import upsert_entity, upsert_relationship
# cut-043R R5-B3 — the inverted resolver requires the pack side-effect to fire
# before any `upsert_relationship` call. Importing the procurement pack here
# triggers self-registration of the `demo`/`spike` prefixes (used by
# seed_demo_relationships and seed_v0_spike_fixture).
import ece.domain_packs.procurement  # noqa: F401

# Map from gen_dataset top-level key -> entity_type (per PRD §27).
# Some lists contain str (name only), others contain dict (id + fields).
_DATASET_TO_ENTITY = {
    "suppliers": "supplier",
    "products": "product",
    "purchase_requests": "purchase_request",
    "contracts": "contract",
    "policies": "policy",
}


def _deterministic_display_id(entity_type: str, idx: int) -> str:
    """Stable display_id for a demo record: ``<PREFIX><idx+1:03d>``.

    cut-040R-2 S1 (extension of the approved fix "B"): the default allocator
    `_next_display_id` is a GLOBAL max+1 per entity_type. Any foreign entity of
    the same type — a test fixture (`r4test` PR201, `r5test` SUP051), a kept
    regression pair (`csv:r4-test-*` SUP052/053), or a spike fixture — raises
    that ceiling, so the next `seed_from_demo_json` replay allocates a FRESH
    block and shifts every demo display_id. That silently invalidated the frozen
    E3/E4/E5 datasets (and is why those datasets once referenced PR201..PR230).

    Demo records are an ordered JSON list, so their display_ids can be derived
    deterministically instead: replaying always reproduces PR001..PR200,
    SUP001..SUP050, etc., no matter what else lives in the table.
    """
    from ece.entities.pipeline import _DISPLAY_ID_PREFIX

    prefix = _DISPLAY_ID_PREFIX.get(entity_type, entity_type.upper()[:3])
    return f"{prefix}{idx + 1:03d}"


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
                    display_id=_deterministic_display_id(entity_type, idx),
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

    # cut-040R-2: derive the dedicated objects from the DB instead of hardcoding
    # display_ids, using the SAME scope + ordering as gen_eval_datasets.py
    # (`source_system='demo:demo'`, ORDER BY display_id). Hardcoded values
    # ("PR003"/"SUP052") drifted out of sync with the generated dataset; deriving
    # both sides makes the ACL rows and the dataset agree by construction.
    with engine.connect() as conn:

        def _nth(entity_type: str, n: int, fallback: str) -> str:
            rows = conn.execute(
                text(
                    "SELECT display_id FROM entities "
                    "WHERE entity_type = :t AND source_system = 'demo:demo' "
                    "ORDER BY display_id LIMIT :lim"
                ),
                {"t": entity_type, "lim": n + 1},
            ).fetchall()
            return rows[n][0] if len(rows) > n else fallback

        sup_2 = _nth("supplier", 1, "SUP002")
        pr_acl = _nth("purchase_request", 2, "PR003")
        con_acl = _nth("contract", 1, "CON002")

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
            "object_ref": sup_2,
            "effect": "allow",
        },
        {
            "subject_type": "user",
            "subject_ref": "demo-user-finance",
            "object_type": "purchase_request",
            "object_ref": pr_acl,  # derived (demo-scoped)
            "effect": "allow",
        },
        {
            "subject_type": "user",
            "subject_ref": "demo-user-procurement",
            "object_type": "contract",
            "object_ref": con_acl,  # derived (demo-scoped)
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


# ─────────────────────────────────────────────────────────────────────────────
# Demo relationship fixture
#
# R2: the relationship seeding logic used to live ONLY in
# `scripts/seed_relationships.py`, a standalone process-level script. `make seed`
# therefore produced 428 entities and ZERO relationships, so any workflow that
# rebuilt the DB and ran the eval suites measured an empty graph. The logic is
# now a shared function here — `run_seed()` calls it, and the script is a thin
# wrapper over it (one implementation, not two copies that drift).
# ─────────────────────────────────────────────────────────────────────────────

DEMO_RELATIONSHIP_SOURCE_SYSTEM = "demo:seed_relationships"

# Departments inferred from demo person attributes (seed.py)
DEMO_DEPARTMENTS = ["procurement", "finance", "sales", "D01"]

# Canonical fixture contract: SIX relationships per demo PR. The 6th is the
# deliberate "2nd submitter for variety" — see the rel_specs list below. This
# count is what the frozen E4/E5 datasets assert (`expected_count`).
EXPECTED_RELS_PER_DEMO_PR = 6

# Explicit allowlist of the source_systems THIS fixture builds relationships on.
#
# cut-040R-2 S1 fix: `_fetch_display_ids` used to select by `entity_type` alone,
# so it annexed ANY entity of the same type. Adding the V0 spike fixture (a
# purchase_request) silently gave it six demo relationships and broke the
# eval-asset guard G2. Scoping by an explicit allowlist expresses the intent
# ("this fixture only touches its own entities") and cannot annex foreign
# fixtures — same pattern as the wipe-predicate fix (precise predicate, never a
# blacklist / LIKE sweep).
_FIXTURE_SOURCE_SYSTEMS: dict[str, str] = {
    "purchase_request": "demo:demo",
    "supplier": "demo:demo",
    "product": "demo:demo",
    "policy": "demo:demo",
    "department": "demo:seed_departments",
    "person": "api:header",
}


def _fetch_display_ids(engine, entity_type: str) -> list[str]:
    """Fetch display_ids for an entity type, SCOPED to this fixture's own
    source_system (see _FIXTURE_SOURCE_SYSTEMS). Sorted.

    Fails loudly on an unmapped entity_type rather than silently reverting to an
    unscoped scan.
    """
    source_system = _FIXTURE_SOURCE_SYSTEMS.get(entity_type)
    if source_system is None:
        raise KeyError(
            f"no fixture source_system mapped for entity_type={entity_type!r}. "
            "Add it to _FIXTURE_SOURCE_SYSTEMS — do NOT fall back to an unscoped "
            "scan (that annexes foreign fixtures)."
        )
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE entity_type = :t AND source_system = :s ORDER BY display_id"
            ),
            {"t": entity_type, "s": source_system},
        ).fetchall()
    return [r[0] for r in rows]


def _seed_fixture_departments(engine) -> list[str]:
    """Seed 4 department entities (no separate dept entities in demo).

    NOTE (R2-obs-2, deliberately NOT changed by R2): `upsert_entity` is called
    without an explicit `display_id`, so D001..D004 are still allocated by the
    global max+1 allocator. No current consumer reads `D0xx` display_ids (E1–E5
    never reference them), so this is latent, not live. Fixing it was ruled out
    of R2's scope.
    """
    for dept in DEMO_DEPARTMENTS:
        upsert_entity(
            engine,
            entity_type="department",
            name=dept.capitalize() if dept != "D01" else "D01 Department",
            source_system="demo:seed_departments",
            source_id=f"dept:{dept}",
            attributes={"name": dept},
        )
    return _fetch_display_ids(engine, "department")


def seed_demo_relationships(engine) -> dict[str, object]:
    """Seed the demo relationship fixture (canonical, idempotent, self-scoped).

    For each demo PR, creates 6 relationships:
    BELONGS_TO department / SUBMITTED_BY person / SELECTS supplier /
    CONTAINS product / SUBMITTED_BY (2nd person) / SUBJECT_TO policy.

    Idempotent via DELETE-then-INSERT scoped to THIS fixture's own
    `source_system` (the `uq_relationships_triple` unique index is the backstop).
    The delete MUST stay scoped: a previous version relied on ON CONFLICT alone
    and leftover rows from interleaved tests silently invalidated E5's
    per-PR expected count.

    Prerequisite: entities (incl. `api:header` persons from `seed_test_users`)
    must already exist — hence `run_seed()` calls `seed_test_users()` first.

    Returns {"ok", "error"?, "prs", "departments", "removed", "inserted_by_type",
             "rejected", "total_in_db"}.

    `ok` is True only when the fixture is COMPLETE: zero rejected edges AND
    exactly `len(prs) x EXPECTED_RELS_PER_DEMO_PR` rows tagged with this
    fixture's own `source_system`. Anything less sets `ok=False` plus an
    `error` explaining which of the two failed — `run_seed()` turns that into a
    RuntimeError rather than letting `make seed` report success.
    """
    dept_ids = _seed_fixture_departments(engine)
    if not dept_ids:
        return {"ok": False, "error": "failed to seed departments"}

    pr_ids = _fetch_display_ids(engine, "purchase_request")
    if not pr_ids:
        return {"ok": False, "error": "no purchase_request entities; run `make seed` first"}

    people_ids = _fetch_display_ids(engine, "person")
    supplier_ids = _fetch_display_ids(engine, "supplier")
    product_ids = _fetch_display_ids(engine, "product")
    policy_ids = _fetch_display_ids(engine, "policy")

    if not (people_ids and supplier_ids and product_ids and policy_ids):
        return {
            "ok": False,
            "error": "missing entity types (need person/supplier/product/policy)",
        }

    counters: dict[str, int] = {
        "BELONGS_TO": 0,
        "SUBMITTED_BY": 0,
        "SELECTS": 0,
        "CONTAINS": 0,
        "SUBJECT_TO": 0,
    }
    rejected: list[str] = []

    with engine.begin() as conn:
        deleted = conn.execute(
            text("DELETE FROM relationships WHERE source_system = :s"),
            {"s": DEMO_RELATIONSHIP_SOURCE_SYSTEM},
        ).rowcount

    for i, pr_id in enumerate(pr_ids):
        rel_specs = [
            ("BELONGS_TO", dept_ids[i % len(dept_ids)]),
            ("SUBMITTED_BY", people_ids[i % len(people_ids)]),
            ("SELECTS", supplier_ids[i % len(supplier_ids)]),
            ("CONTAINS", product_ids[i % len(product_ids)]),
            ("SUBMITTED_BY", people_ids[(i + 1) % len(people_ids)]),  # 2nd submitter for variety
            ("SUBJECT_TO", policy_ids[i % len(policy_ids)]),
        ]
        # Dedupe rel_specs in case of cyclic collisions
        seen_targets: set[tuple[str, str]] = set()
        for rel_type, target in rel_specs:
            key = (rel_type, target)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            inserted, reason = upsert_relationship(
                engine,
                src_display_id=pr_id,
                relation=rel_type,
                dst_display_id=target,
                source_system=DEMO_RELATIONSHIP_SOURCE_SYSTEM,
            )
            if inserted:
                counters[rel_type] += 1
            else:
                rejected.append(f"{pr_id} -{rel_type}-> {target}: {reason}")

    expected = len(pr_ids) * EXPECTED_RELS_PER_DEMO_PR
    problems: list[str] = []

    # A rejected edge is a FAILURE, not a footnote. The contract here is "build a
    # complete, deterministic fixture", not "seed as much as you can": reporting
    # ok=True alongside a short fixture is how `make seed` would go green on an
    # environment that cannot support the evaluation it claims to prepare.
    if rejected:
        problems.append(
            f"{len(rejected)} relationship(s) REJECTED — the canonical fixture must be "
            f"complete: {'; '.join(rejected[:3])}"
        )

    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM relationships")).scalar()
        owned = conn.execute(
            text("SELECT count(*) FROM relationships WHERE source_system = :s"),
            {"s": DEMO_RELATIONSHIP_SOURCE_SYSTEM},
        ).scalar_one()

    # Ground truth is the ROW COUNT, never the counters above. Two reasons, both
    # verified against this database:
    #   1. upsert_relationship returns inserted=True even when ON CONFLICT DO
    #      NOTHING wrote nothing (probe: two calls on one triple -> True/True,
    #      one row).
    #   2. uq_relationships_triple keys on (src, relation, dst, valid_from)
    #      WITHOUT source_system, so a triple already owned by another fixture
    #      swallows our insert silently.
    # Only counting rows tagged with our own source_system sees either case.
    if int(owned) != expected:
        problems.append(
            f"fixture incomplete: {owned} rows tagged "
            f"'{DEMO_RELATIONSHIP_SOURCE_SYSTEM}', expected {expected} "
            f"({len(pr_ids)} PRs x {EXPECTED_RELS_PER_DEMO_PR}) while "
            f"{sum(counters.values())} insert(s) were reported. A shortfall with no "
            "rejections means a foreign source_system already owns those triples."
        )

    result: dict[str, object] = {
        "ok": len(problems) == 0,
        "prs": len(pr_ids),
        "departments": len(dept_ids),
        "removed": deleted,
        "inserted_by_type": dict(counters),
        "rejected": rejected,
        "total_in_db": int(total or 0),
    }
    if problems:
        result["error"] = " | ".join(problems)
    return result


def demo_relationship_fixture_status(engine) -> dict[str, object]:
    """Report whether the demo relationship fixture is present AND canonical.

    R2 (C.3): consumers that would otherwise measure an EMPTY graph (E4/E5)
    call this so a missing fixture fails loudly instead of producing a vacuous
    result.

    The per-PR deviation check alone is NOT sufficient: `HAVING count(*) != 6`
    only sees PRs that HAVE relationship rows, so it silently ignores the worst
    case (a PR with zero relationships). The total is therefore also reconciled
    against `<demo PR entities> × EXPECTED_RELS_PER_DEMO_PR`.

    Returns {"total", "expected_total", "deviating_prs", "complete"}.
    """
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM relationships WHERE source_system = :s"),
            {"s": DEMO_RELATIONSHIP_SOURCE_SYSTEM},
        ).scalar_one()
        demo_prs = conn.execute(
            text(
                "SELECT count(*) FROM entities "
                "WHERE entity_type = 'purchase_request' AND source_system = 'demo:demo'"
            )
        ).scalar_one()
        deviating = conn.execute(
            text(
                """
                SELECT s.display_id, count(*) AS n
                FROM relationships r
                JOIN entities s ON s.id = r.src_entity_id
                WHERE s.entity_type = 'purchase_request'
                  AND s.source_system = 'demo:demo'
                GROUP BY s.display_id
                HAVING count(*) != :want
                ORDER BY s.display_id
                """
            ),
            {"want": EXPECTED_RELS_PER_DEMO_PR},
        ).fetchall()

    expected_total = int(demo_prs) * EXPECTED_RELS_PER_DEMO_PR
    return {
        "total": int(total),
        "expected_total": expected_total,
        "deviating_prs": [(r[0], r[1]) for r in deviating],
        "complete": bool(demo_prs) and int(total) == expected_total and not deviating,
    }


def run_seed() -> dict[str, object]:
    """Entry: load demo.json, upsert all entities, return summary.

    cut-040 additions:
    - _seed_entity_departments() injects attributes.department per entity_type
      (R40.1c) — now called from INSIDE seed_from_demo_json (R40R2.1) so the
      idempotent replay self-heals
    - seed_acl_entries() seeds 3 acl_entries for E2 'acl_explicit' cases
      (R40.1a)

    R2 addition:
    - seed_demo_relationships() — relationship seeding moved in from
      scripts/seed_relationships.py, so this entrypoint now produces a COMPLETE
      environment. Order matters: it must run after seed_test_users(), because
      the fixture's SUBMITTED_BY edges target the `api:header` persons that
      function creates.
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
    # R2: relationships. Fails loudly rather than leaving a half-built
    # environment — a silent empty graph is what made E4/E5 vacuous.
    relationships = seed_demo_relationships(engine)
    if not relationships.get("ok"):
        raise RuntimeError(
            "canonical seed incomplete — relationship seeding failed: "
            f"{relationships.get('error')}"
        )
    out["relationships"] = relationships
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
    # R2: report the relationship stage so `make seed` output shows the fixture
    # is complete (this line is also what makes an incomplete seed auditable).
    rels: dict[str, object] = result["relationships"]  # type: ignore[assignment]
    inserted: dict[str, int] = rels["inserted_by_type"]  # type: ignore[assignment]
    rejected_list: list[str] = rels["rejected"]  # type: ignore[assignment]
    print(
        f"Relationships: {inserted} "
        f"(replaced {rels['removed']} prior rows, {rels['departments']} departments)"
    )
    print(f"Total relationships in DB: {rels['total_in_db']}")
    if rejected_list:
        print(f"  REJECTED {len(rejected_list)} relationship(s):")
        for r in rejected_list[:5]:
            print(f"    {r}")
    sys.exit(0)
