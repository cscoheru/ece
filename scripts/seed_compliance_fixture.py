#!/usr/bin/env python3
"""cut-044 — Compliance Pack fixture seeder.

    TECHNICAL DEMO FIXTURE (Compliance Pack)
    SYNTHETIC DATA — NOT CUSTOMER-VALIDATED

Mirrors `seed_knowledge_fixture.py` structurally so the two fixtures are
provably independent: different `source_system`, separate DELETE-then-INSERT
scope, runtime-resolved display_ids, denial ACL on a denied user.

Contract (per PRD §6 row 3 — Compliance scenario):

  * source_system = ``comp:v0-compliance-fixture`` — DELETE-then-INSERT is
    scoped to exactly this value (FER lesson: never a `LIKE` sweep).
  * 3 controls with distinct evidence-package coverage so the R-COMP-AUDIT
    rule's four truth-table branches are all exercisable on a single seeded
    fixture:
      COMP-CTL-001 → both conditions pass → evidence_package_sufficient
      COMP-CTL-002 → both conditions fail → gap_list (zero-evidence allowlist)
      COMP-CTL-003 → count passes, coverage fails → gap_list (1 evidence row)
  * 3 systems (erp, hr, finance) + REQUIRES_SYSTEM relations for each
    control to ALL 3 systems — the gap is in EVIDENCE, not in REQUIREMENTS.
  * evidence_packages are inlined into control.attrs.evidence_packages
    (NOT a separate entity type) — cut-044 design decision documented in
    plan §3.1 + the rule module docstring.
  * Denied user `comp-eve` for PRD §7 纪律 #2 demonstration.

Objects:

  | entity_type | source_id    | notes                                                |
  |-------------|--------------|------------------------------------------------------|
  | control     | COMP-CTL-001 | requires all 3 systems; 3 evidence pkgs (1 each)     |
  | control     | COMP-CTL-002 | requires all 3 systems; 2 evidence pkgs (erp only)   |
  | control     | COMP-CTL-003 | requires all 3 systems; 3 evidence pkgs (erp+2*hr)   |
  | system      | erp-system   | entity; control -REQUIRES_SYSTEM-> erp-system        |
  | system      | hr-system    | entity; control -REQUIRES_SYSTEM-> hr-system         |
  | system      | finance-system | entity; control -REQUIRES_SYSTEM-> finance-system  |

  relationships:
    COMP-CTL-001 -REQUIRES_SYSTEM-> erp-system
    COMP-CTL-001 -REQUIRES_SYSTEM-> hr-system
    COMP-CTL-001 -REQUIRES_SYSTEM-> finance-system
    COMP-CTL-002 -REQUIRES_SYSTEM-> erp-system
    COMP-CTL-002 -REQUIRES_SYSTEM-> hr-system
    COMP-CTL-002 -REQUIRES_SYSTEM-> finance-system
    COMP-CTL-003 -REQUIRES_SYSTEM-> erp-system
    COMP-CTL-003 -REQUIRES_SYSTEM-> hr-system
    COMP-CTL-003 -REQUIRES_SYSTEM-> finance-system

  acl_entries:
    DENY comp-eve on COMP-CTL-001 (explicit demonstration per PRD §7 纪律 #2)

Usage:
    uv run python scripts/seed_compliance_fixture.py
Exit codes: 0 = seeded + self-check passed; 1 = self-check failed.
"""
from __future__ import annotations

import sys

from sqlalchemy import text

# cut-044 — the inverted resolver requires the pack side-effect to fire
# (otherwise `is_allowed_for_system` is fail-closed and rejects comp:*
# relations). Importing `ece.domain_packs.compliance` triggers
# self-registration of the `comp` prefix in `ece.entities.ontology_resolver`.
# Mirrors the cut-043R R5-B3 lesson from `seed_knowledge_fixture.py:63`.
import ece.domain_packs.compliance  # noqa: F401
from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship

COMP_SOURCE_SYSTEM = "comp:v0-compliance-fixture"

FIXTURE_NOTICE = (
    "CUT-044 COMPLIANCE DEMO FIXTURE — "
    "SYNTHETIC — NOT CUSTOMER-VALIDATED"
)

# Audit-period window for every evidence_package in this fixture.
# The default `today` in `v0_rules._evaluate_via_params` is "2026-09-22"
# which falls inside this window — same pattern as `seed_knowledge_fixture`.
PERIOD_START = "2026-07-01"
PERIOD_END = "2026-09-30"

# (entity_type, source_id, display_id, name, attributes)
FIXTURE_ENTITIES: list[tuple[str, str, str, str, dict[str, object]]] = [
    # ─── Controls ───
    (
        "control",
        "COMP-CTL-001",
        "COMP-CTL-001",
        "关联交易披露完整性 (CTL-001)",
        {
            "required_systems": ["erp-system", "hr-system", "finance-system"],
            "evidence_min": 3,
            "evidence_packages": [
                {"system": "erp-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
                {"system": "hr-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
                {"system": "finance-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
            ],
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    (
        "control",
        "COMP-CTL-002",
        "COMP-CTL-002",
        "采购审批合规性 (CTL-002, 缺财务系统证据)",
        {
            "required_systems": ["erp-system", "hr-system", "finance-system"],
            "evidence_min": 3,
            "evidence_packages": [
                {"system": "erp-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
                {"system": "erp-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
            ],
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    (
        "control",
        "COMP-CTL-003",
        "COMP-CTL-003",
        "薪酬内控有效性 (CTL-003, 缺财务系统证据)",
        {
            "required_systems": ["erp-system", "hr-system", "finance-system"],
            "evidence_min": 3,
            "evidence_packages": [
                {"system": "erp-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
                {"system": "hr-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
                {"system": "hr-system", "period_start": PERIOD_START, "period_end": PERIOD_END},
            ],
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    # ─── Systems (referenced by REQUIRES_SYSTEM) ───
    (
        "system",
        "erp-system",
        "COMP-S-ERP",
        "ERP 系统",
        {"system_kind": "erp", "fixture_notice": FIXTURE_NOTICE},
    ),
    (
        "system",
        "hr-system",
        "COMP-S-HR",
        "HR 系统",
        {"system_kind": "hr", "fixture_notice": FIXTURE_NOTICE},
    ),
    (
        "system",
        "finance-system",
        "COMP-S-FIN",
        "财务系统",
        {"system_kind": "finance", "fixture_notice": FIXTURE_NOTICE},
    ),
    # ─── Person for permission / denial demonstration ───
    # NOTE: `comp-alice` and `comp-eve` are NOT entities in the engine schema
    # (the engine keys users by `X-User-Id` header string). They are recorded
    # here only for fixture documentation; the ACL row uses `subject_ref` =
    # raw user_id string.
]

# Pre-seeded relations — no runtime materializer (cut-044 design).
# Each control -REQUIRES_SYSTEM-> each of the 3 systems (= 9 total rows).
FIXTURE_RELATIONSHIPS: list[tuple[str, str, str]] = []
for ctrl in ("COMP-CTL-001", "COMP-CTL-002", "COMP-CTL-003"):
    for sys_name in ("erp-system", "hr-system", "finance-system"):
        FIXTURE_RELATIONSHIPS.append((ctrl, "REQUIRES_SYSTEM", sys_name))

# Denied user demonstration (PRD §7 纪律 #2 — every domain must show denied users)
DENIED_USER_REF = "comp-eve"


def _delete_own_rows(engine) -> dict[str, int]:
    """DELETE-then-INSERT, scoped to exactly this fixture's source_system."""
    removed: dict[str, int] = {}
    with engine.begin() as conn:
        removed["relationships"] = conn.execute(
            text("DELETE FROM relationships WHERE source_system = :s"),
            {"s": COMP_SOURCE_SYSTEM},
        ).rowcount
        removed["entity_aliases"] = conn.execute(
            text(
                "DELETE FROM entity_aliases WHERE entity_id IN "
                "(SELECT id FROM entities WHERE source_system = :s)"
            ),
            {"s": COMP_SOURCE_SYSTEM},
        ).rowcount
        removed["entities"] = conn.execute(
            text("DELETE FROM entities WHERE source_system = :s"),
            {"s": COMP_SOURCE_SYSTEM},
        ).rowcount
        removed["acl_entries"] = conn.execute(
            text("DELETE FROM acl_entries WHERE source_system = :s"),
            {"s": COMP_SOURCE_SYSTEM},
        ).rowcount
    return removed


def _display_id_for(engine, source_id: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": source_id, "s": COMP_SOURCE_SYSTEM},
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
            source_system=COMP_SOURCE_SYSTEM,
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
            source_system=COMP_SOURCE_SYSTEM,
        )
        relationships_created += 1 if inserted else 0

    # Denied-user demonstration: DENY comp-eve on COMP-CTL-001.
    ctl_display = _display_id_for(engine, "COMP-CTL-001")
    if not ctl_display:
        raise RuntimeError("fixture control COMP-CTL-001 not resolved after upsert")
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
            {"subj": DENIED_USER_REF, "oref": ctl_display, "s": COMP_SOURCE_SYSTEM},
        )

    return {
        "source_system": COMP_SOURCE_SYSTEM,
        "removed": removed,
        "entities_created": created,
        "relationships_created": relationships_created,
        "ctl001_display_id": ctl_display,
        "period": (PERIOD_START, PERIOD_END),
    }


def self_check(engine) -> list[str]:
    """Return a list of failures (empty = OK). Never silently pass."""
    failures: list[str] = []

    # 1. All 6 fixture entities present with expected display_ids
    for _etype, source_id, want_display_id, _name, _attrs in FIXTURE_ENTITIES:
        got = _display_id_for(engine, source_id)
        if got is None:
            failures.append(f"missing fixture entity: {source_id}")
        elif got != want_display_id:
            failures.append(
                f"display_id drift: {source_id} expected {want_display_id!r}, got {got!r}"
            )

    # 2. Each control has exactly 3 REQUIRES_SYSTEM relationships
    for ctrl_sid in ("COMP-CTL-001", "COMP-CTL-002", "COMP-CTL-003"):
        ctl_display = _display_id_for(engine, ctrl_sid)
        if not ctl_display:
            continue
        with engine.connect() as conn:
            n_rel = conn.execute(
                text(
                    "SELECT count(*) FROM relationships r "
                    "JOIN entities s ON s.id = r.src_entity_id "
                    "WHERE s.source_system = :s AND r.relation = 'REQUIRES_SYSTEM' "
                    "AND s.display_id = :d"
                ),
                {"s": COMP_SOURCE_SYSTEM, "d": ctl_display},
            ).scalar()
            if n_rel != 3:
                failures.append(
                    f"{ctrl_sid}: expected exactly 3 REQUIRES_SYSTEM, got {n_rel}"
                )

    # 3. CTL-001 attrs have evidence_min=3 and required_systems length=3
    ctl001_display = _display_id_for(engine, "COMP-CTL-001")
    if ctl001_display:
        with engine.connect() as conn:
            attrs = conn.execute(
                text("SELECT attributes FROM entities WHERE display_id = :d"),
                {"d": ctl001_display},
            ).scalar()
            attrs = attrs or {}
            req = attrs.get("required_systems") or []
            if len(req) != 3:
                failures.append(
                    f"COMP-CTL-001 required_systems must have 3 entries, got {len(req)}: {req!r}"
                )
            if attrs.get("evidence_min") != 3:
                failures.append(
                    f"COMP-CTL-001 evidence_min must be 3, got {attrs.get('evidence_min')!r}"
                )
            ev_pkgs = attrs.get("evidence_packages") or []
            if len(ev_pkgs) != 3:
                failures.append(
                    f"COMP-CTL-001 evidence_packages must have 3 entries, got {len(ev_pkgs)}"
                )

    # 4. CTL-002 attrs have evidence_min=3 and 2 evidence_packages (both erp)
    ctl002_display = _display_id_for(engine, "COMP-CTL-002")
    if ctl002_display:
        with engine.connect() as conn:
            attrs = conn.execute(
                text("SELECT attributes FROM entities WHERE display_id = :d"),
                {"d": ctl002_display},
            ).scalar()
            attrs = attrs or {}
            ev_pkgs = attrs.get("evidence_packages") or []
            if len(ev_pkgs) != 2:
                failures.append(
                    f"COMP-CTL-002 evidence_packages must have 2 entries, got {len(ev_pkgs)}"
                )
            systems = {e.get("system") for e in ev_pkgs if isinstance(e, dict)}
            if systems != {"erp-system"}:
                failures.append(
                    f"COMP-CTL-002 evidence_packages systems must be {{'erp-system'}}, got {systems!r}"
                )

    # 5. CTL-003 attrs have 3 evidence_packages spanning erp + hr
    ctl003_display = _display_id_for(engine, "COMP-CTL-003")
    if ctl003_display:
        with engine.connect() as conn:
            attrs = conn.execute(
                text("SELECT attributes FROM entities WHERE display_id = :d"),
                {"d": ctl003_display},
            ).scalar()
            attrs = attrs or {}
            ev_pkgs = attrs.get("evidence_packages") or []
            if len(ev_pkgs) != 3:
                failures.append(
                    f"COMP-CTL-003 evidence_packages must have 3 entries, got {len(ev_pkgs)}"
                )
            systems = {e.get("system") for e in ev_pkgs if isinstance(e, dict)}
            if systems != {"erp-system", "hr-system"}:
                failures.append(
                    f"COMP-CTL-003 evidence_packages systems must be "
                    f"{{'erp-system', 'hr-system'}}, got {systems!r}"
                )

    # 6. DENY ACL on comp-eve → COMP-CTL-001
    if ctl001_display:
        with engine.connect() as conn:
            n_acl = conn.execute(
                text(
                    "SELECT count(*) FROM acl_entries "
                    "WHERE source_system = :s AND object_type = 'entity' "
                    "AND object_ref = :oref AND subject_ref = :subj AND effect = 'deny'"
                ),
                {"s": COMP_SOURCE_SYSTEM, "oref": ctl001_display, "subj": DENIED_USER_REF},
            ).scalar()
            if n_acl != 1:
                failures.append(
                    f"expected 1 DENY acl row for {DENIED_USER_REF} on {ctl001_display}, "
                    f"got {n_acl}"
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
    print(f"CTL-001 display_id   : {result['ctl001_display_id']}  (resolved at runtime)")
    print(f"audit period         : {result['period'][0]} .. {result['period'][1]}")
    print("-" * 72)

    failures = self_check(engine)
    if failures:
        print("SELF-CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-CHECK PASSED — all 6 fixture entities present, 9 REQUIRES_SYSTEM (3 per control),")
    print("                     CTL-001 3 evidence / 3 systems, CTL-002 2 evidence / erp only,")
    print("                     CTL-003 3 evidence / erp+hr, DENY acl on comp-eve → CTL-001.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
