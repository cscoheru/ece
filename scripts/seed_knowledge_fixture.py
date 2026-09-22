#!/usr/bin/env python3
"""cut-043 — Knowledge Management Pack fixture seeder.

    TECHNICAL DEMO FIXTURE (Knowledge Management Pack)
    SYNTHETIC DATA — NOT CUSTOMER-VALIDATED

Mirrors the structure of `seed_v0_spike_fixture.py` so the two fixtures are
provably independent: different `source_system`, separate DELETE-then-INSERT
scope, runtime-resolved display_ids, denial ACL on a denied user.

Contract (per PRD §6 row 2 — Knowledge Management scenario):

  * source_system = ``km:v0-knowledge-fixture`` — DELETE-then-INSERT is
    scoped to **exactly this value** (FER lesson: never a `LIKE` sweep).
  * 3 policies with distinct validity/permission combinations so the
    R-KM-ACCESS rule's four truth-table branches are all exercisable
    on a single seeded fixture.
  * 3 employees with distinct role sets so denied-user demonstration
    (PRD §7 纪律 #2) is straightforward.
  * Policy + role relationships are pre-seeded (no runtime materializer —
    policy/permission relations are static in the fixture, by design).

Objects:

  | entity_type     | source_id    | notes                                       |
  |-----------------|--------------|---------------------------------------------|
  | policy_document | KM-POL-001   | valid 2026-01-01..2026-12-31, requires hr  |
  | policy_document | KM-POL-002   | EXPIRED (valid 2024-01-01..2024-12-31)      |
  | policy_document | KM-POL-003   | valid 2026-01-01..2026-12-31, requires fin |
  | person          | km-alice     | roles=[hr] → allowed on KM-POL-001         |
  | person          | km-bob       | roles=[finance] → allowed on KM-POL-003    |
  | person          | km-eve       | roles=[] → DENIED on all policies           |
  | role            | km-role-hr   | placeholder for HAS_ROLE mapping           |
  | role            | km-role-fin  | placeholder for HAS_ROLE mapping           |

  relationships:
    KM-POL-001  -REQUIRES_ROLE-> km-role-hr
    KM-POL-003  -REQUIRES_ROLE-> km-role-fin
    km-alice    -HAS_ROLE->     km-role-hr
    km-bob      -HAS_ROLE->     km-role-fin

  acl_entries:
    DENY km-eve on KM-POL-001 (explicit demonstration per PRD §7 纪律 #2)

Usage:
    uv run python scripts/seed_knowledge_fixture.py
Exit codes: 0 = seeded + self-check passed; 1 = self-check failed.
"""
from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import text

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship
# cut-043R R5-B3 — the inverted resolver requires the pack side-effect to fire
# (otherwise `is_allowed_for_system` is fail-closed and rejects km:* relations).
# Importing `ece.domain_packs.knowledge` triggers self-registration of the
# `km` prefix in `ece.entities.ontology_resolver`. The seeder mirrors what the
# API path does via `_discover_domains`.
import ece.domain_packs.knowledge  # noqa: F401

KM_SOURCE_SYSTEM = "km:v0-knowledge-fixture"

FIXTURE_NOTICE = (
    "CUT-043 KNOWLEDGE MANAGEMENT DEMO FIXTURE — "
    "SYNTHETIC — NOT CUSTOMER-VALIDATED"
)

# Anchor date used by the rule's validity check. Must match the default
# `today` in `_register_for_demo._evaluate_via_params` so a bare
# `POST /api/v1/demo/scenarios/generate` with no `today` param exercises
# the "validity passed" branch for KM-POL-001 / KM-POL-003.
TODAY_ANCHOR = date(2026, 9, 22).isoformat()

# (entity_type, source_id, display_id, name, attributes)
FIXTURE_ENTITIES: list[tuple[str, str, str, str, dict[str, object]]] = [
    (
        "policy_document",
        "KM-POL-001",
        "KM-POL-001",
        "员工差旅报销制度 v3",
        {
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "required_role": "hr",
            "version": "v3",
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    (
        "policy_document",
        "KM-POL-002",
        "KM-POL-002",
        "旧版报销制度（已过期）",
        {
            "valid_from": "2024-01-01",
            "valid_to": "2024-12-31",
            "required_role": "hr",
            "version": "v1",
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    (
        "policy_document",
        "KM-POL-003",
        "KM-POL-003",
        "财务审批权限制度 v2",
        {
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "required_role": "finance",
            "version": "v2",
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    (
        "person",
        "km-alice",
        "KM-U-ALICE",
        "Alice（HR 经理）",
        {"department": "hr", "roles": ["hr"], "is_management": True},
    ),
    (
        "person",
        "km-bob",
        "KM-U-BOB",
        "Bob（财务经理）",
        {"department": "finance", "roles": ["finance"], "is_management": True},
    ),
    (
        "person",
        "km-eve",
        "KM-U-EVE",
        "Eve（无角色员工）",
        {"department": "operations", "roles": [], "is_management": False},
    ),
    ("role", "km-role-hr", "KM-R-HR", "HR 角色", {"fixture_notice": FIXTURE_NOTICE}),
    ("role", "km-role-fin", "KM-R-FIN", "Finance 角色", {"fixture_notice": FIXTURE_NOTICE}),
]

# Pre-seeded relations — no runtime materializer (cut-043 design).
FIXTURE_RELATIONSHIPS: list[tuple[str, str, str]] = [
    ("KM-POL-001", "REQUIRES_ROLE", "km-role-hr"),
    ("KM-POL-003", "REQUIRES_ROLE", "km-role-fin"),
    ("km-alice", "HAS_ROLE", "km-role-hr"),
    ("km-bob", "HAS_ROLE", "km-role-fin"),
]

# Denied user demonstration (PRD §7 纪律 #2 — every domain must show denied users)
DENIED_USER_REF = "km-eve"


def _delete_own_rows(engine) -> dict[str, int]:
    """DELETE-then-INSERT, scoped to exactly this fixture's source_system."""
    removed: dict[str, int] = {}
    with engine.begin() as conn:
        removed["relationships"] = conn.execute(
            text("DELETE FROM relationships WHERE source_system = :s"),
            {"s": KM_SOURCE_SYSTEM},
        ).rowcount
        removed["entity_aliases"] = conn.execute(
            text(
                "DELETE FROM entity_aliases WHERE entity_id IN "
                "(SELECT id FROM entities WHERE source_system = :s)"
            ),
            {"s": KM_SOURCE_SYSTEM},
        ).rowcount
        removed["entities"] = conn.execute(
            text("DELETE FROM entities WHERE source_system = :s"),
            {"s": KM_SOURCE_SYSTEM},
        ).rowcount
        removed["acl_entries"] = conn.execute(
            text("DELETE FROM acl_entries WHERE source_system = :s"),
            {"s": KM_SOURCE_SYSTEM},
        ).rowcount
    return removed


def _display_id_for(engine, source_id: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": source_id, "s": KM_SOURCE_SYSTEM},
        ).first()
    return row[0] if row else None


def seed(engine) -> dict[str, object]:
    """Seed the fixture. Idempotent: canonical re-seed every run."""
    removed = _delete_own_rows(engine)

    created = 0
    for entity_type, source_id, display_id, name, attrs in FIXTURE_ENTITIES:
        result = upsert_entity(
            engine,
            entity_type=entity_type,
            name=name,
            source_system=KM_SOURCE_SYSTEM,
            source_id=source_id,
            attributes=attrs,
            display_id=display_id,
        )
        created += 1 if result.created else 0

    relationships_created = 0
    for src_sid, relation, dst_sid in FIXTURE_RELATIONSHIPS:
        src_display = _display_id_for(engine, src_sid)
        dst_display = _display_id_for(engine, dst_sid)
        if not src_display or not dst_display:
            raise RuntimeError(
                f"fixture relationship endpoints not resolved: {src_sid} -> {dst_sid}"
            )
        inserted, _reason = upsert_relationship(
            engine,
            src_display_id=src_display,
            relation=relation,
            dst_display_id=dst_display,
            source_system=KM_SOURCE_SYSTEM,
        )
        relationships_created += 1 if inserted else 0

    # Denied-user demonstration: DENY km-eve on KM-POL-001.
    pol_display = _display_id_for(engine, "KM-POL-001")
    if not pol_display:
        raise RuntimeError("fixture policy KM-POL-001 not resolved after upsert")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO acl_entries
                  (subject_type, subject_ref, object_type, object_ref, effect, source_system)
                VALUES ('user', :subj, 'entity', :oref, 'deny', :s)
                ON CONFLICT DO NOTHING
                """
            ),
            {"subj": DENIED_USER_REF, "oref": pol_display, "s": KM_SOURCE_SYSTEM},
        )

    return {
        "source_system": KM_SOURCE_SYSTEM,
        "removed": removed,
        "entities_created": created,
        "relationships_created": relationships_created,
        "policy_display_id": pol_display,
        "today_anchor": TODAY_ANCHOR,
    }


def self_check(engine) -> list[str]:
    """Return a list of failures (empty = OK). Never silently pass."""
    failures: list[str] = []

    for _etype, source_id, want_display_id, _name, _attrs in FIXTURE_ENTITIES:
        got = _display_id_for(engine, source_id)
        if got is None:
            failures.append(f"missing fixture entity: {source_id}")
        elif got != want_display_id:
            failures.append(
                f"display_id drift: {source_id} expected {want_display_id!r}, got {got!r}"
            )

    pol_display = _display_id_for(engine, "KM-POL-001")
    if pol_display:
        with engine.connect() as conn:
            n_rel = conn.execute(
                text(
                    "SELECT count(*) FROM relationships r "
                    "JOIN entities s ON s.id = r.src_entity_id "
                    "WHERE s.source_system = :s AND r.relation = 'REQUIRES_ROLE'"
                ),
                {"s": KM_SOURCE_SYSTEM},
            ).scalar()
            if n_rel != 2:
                failures.append(
                    f"expected exactly 2 REQUIRES_ROLE relationships, got {n_rel}"
                )

            attrs = conn.execute(
                text("SELECT attributes FROM entities WHERE display_id = :d"),
                {"d": pol_display},
            ).scalar()
            attrs = attrs or {}
            if attrs.get("valid_from") != "2026-01-01":
                failures.append(
                    f"KM-POL-001 valid_from must be '2026-01-01', got {attrs.get('valid_from')!r}"
                )
            if attrs.get("required_role") != "hr":
                failures.append(
                    f"KM-POL-001 required_role must be 'hr', got {attrs.get('required_role')!r}"
                )

            n_acl = conn.execute(
                text(
                    "SELECT count(*) FROM acl_entries "
                    "WHERE source_system = :s AND object_type = 'entity' "
                    "AND object_ref = :oref AND subject_ref = :subj AND effect = 'deny'"
                ),
                {"s": KM_SOURCE_SYSTEM, "oref": pol_display, "subj": DENIED_USER_REF},
            ).scalar()
            if n_acl != 1:
                failures.append(
                    f"expected 1 DENY acl row for {DENIED_USER_REF} on {pol_display}, got {n_acl}"
                )

    return failures


def main() -> int:
    engine = get_engine()
    print(FIXTURE_NOTICE)
    print("-" * 72)
    result = seed(engine)
    print(f"source_system        : {result['source_system']}")
    print(f"removed (prior rows) : {result['removed']}")
    print(f"entities created     : {result['entities_created']}")
    print(f"relationships created: {result['relationships_created']}")
    print(f"policy display_id    : {result['policy_display_id']}  (resolved at runtime)")
    print(f"today anchor         : {result['today_anchor']}")
    print("-" * 72)

    failures = self_check(engine)
    if failures:
        print("SELF-CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-CHECK PASSED — all 8 fixture entities present, 2 REQUIRES_ROLE + 2 HAS_ROLE,")
    print("                     KM-POL-001 valid+requires_hr, DENY acl on km-eve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
