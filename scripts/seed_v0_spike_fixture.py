#!/usr/bin/env python3
"""S1 — V0 Technical Spike fixture seeder.

    TECHNICAL SPIKE FIXTURE
    NOT CUSTOMER-VALIDATED
    NOT PRODUCT REFERENCE WORKFLOW

This is the minimal synthetic fixture used ONLY to prove the six-step V0 Kernel
loop (Context → Entity/Knowledge → Rule → Decision → Evidence → Context Update).
It is **not** a product direction and **not** the Reference Workflow — that is
"B", which must wait for "A" (customer validation).

Contract (per docs/v0/V0_EXECUTION_SPEC.md §1, approved 2026-09-20):

  * source_system = ``spike:v0-technical-fixture`` — DELETE-then-INSERT is
    scoped to **exactly this value**, never a ``LIKE`` sweep (the FER lesson:
    "broad range + blacklist" silently destroys other fixtures).
  * All fixture objects are addressed by **source_id**; ``display_id`` is
    resolved at runtime and **never hardcoded** (display_ids drift on
    wipe+replay — also an FER lesson).
  * 3 suppliers exist but only **1 SELECTS** relationship is created, so
    ``quote_count == 1`` unambiguously triggers R-SPIKE-REVIEW.
  * PR starts with ``review_status = "pending"``.

Objects:

  | entity_type      | source_id               | notes                          |
  |------------------|-------------------------|--------------------------------|
  | purchase_request | SPIKE-PR-001            | amount=1280000, pending        |
  | supplier         | SPIKE-SUP-A/B/C         | only A is SELECTed             |
  | policy           | SPIKE-POL-001           | placeholder, no relationship   |
  | person           | spike-user-procurement  | dept=procurement, roles=[buyer]|
  | person           | spike-user-unrelated    | dept=sales → must be DENIED    |

  relationships: SPIKE-PR-001 -SELECTS-> SPIKE-SUP-A   (exactly one)
  acl_entries  : DENY  spike-user-unrelated  on entity/<PR display_id>

Usage:
    uv run python scripts/seed_v0_spike_fixture.py
Exit codes: 0 = seeded + self-check passed; 1 = self-check failed.
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from ece.db import get_engine
from ece.entities.pipeline import upsert_entity, upsert_relationship

SPIKE_SOURCE_SYSTEM = "spike:v0-technical-fixture"

FIXTURE_NOTICE = (
    "TECHNICAL SPIKE FIXTURE — NOT CUSTOMER-VALIDATED — "
    "NOT PRODUCT REFERENCE WORKFLOW"
)

# (entity_type, source_id, display_id, name, attributes)
#
# display_id is EXPLICIT for every fixture entity. The shared numeric namespace
# (PR### / SUP### / POL### / U###) is allocated by `_next_display_id` = global
# max+1; a surviving foreign entity raises that ceiling and shifts the whole
# demo space on the next wipe+replay (cut-040R-2 S1 finding). `SPIKE-*` ids match
# no allocation prefix, so this fixture can never perturb it.
FIXTURE_ENTITIES: list[tuple[str, str, str, str, dict[str, object]]] = [
    (
        "purchase_request",
        "SPIKE-PR-001",
        "SPIKE-PR-001",
        "V0 Spike Purchase Request",
        {
            "amount": 1_280_000,
            "review_status": "pending",
            "fixture_notice": FIXTURE_NOTICE,
        },
    ),
    ("supplier", "SPIKE-SUP-A", "SPIKE-SUP-A", "Spike Supplier A", {}),
    ("supplier", "SPIKE-SUP-B", "SPIKE-SUP-B", "Spike Supplier B", {}),
    ("supplier", "SPIKE-SUP-C", "SPIKE-SUP-C", "Spike Supplier C", {}),
    ("policy", "SPIKE-POL-001", "SPIKE-POL-001", "Spike Procurement Policy", {}),
    (
        "person",
        "spike-user-procurement",
        "SPIKE-U-PROC",
        "Spike Procurement Buyer",
        {"department": "procurement", "roles": ["buyer"], "is_management": False},
    ),
    (
        "person",
        "spike-user-unrelated",
        "SPIKE-U-UNREL",
        "Spike Unrelated User",
        {"department": "sales", "roles": [], "is_management": False},
    ),
]

# Exactly ONE relationship — this is what makes quote_count == 1 unambiguous.
FIXTURE_RELATIONSHIPS: list[tuple[str, str, str]] = [
    ("SPIKE-PR-001", "SELECTS", "SPIKE-SUP-A"),
]

# The permission hard gate for this fixture: this user must never see the PR.
DENIED_USER_REF = "spike-user-unrelated"


def _delete_own_rows(engine) -> dict[str, int]:
    """DELETE-then-INSERT, scoped to exactly this fixture's source_system."""
    removed: dict[str, int] = {}
    with engine.begin() as conn:
        # children first (FK)
        removed["relationships"] = conn.execute(
            text("DELETE FROM relationships WHERE source_system = :s"),
            {"s": SPIKE_SOURCE_SYSTEM},
        ).rowcount
        removed["entity_aliases"] = conn.execute(
            text(
                "DELETE FROM entity_aliases WHERE entity_id IN "
                "(SELECT id FROM entities WHERE source_system = :s)"
            ),
            {"s": SPIKE_SOURCE_SYSTEM},
        ).rowcount
        removed["entities"] = conn.execute(
            text("DELETE FROM entities WHERE source_system = :s"),
            {"s": SPIKE_SOURCE_SYSTEM},
        ).rowcount
        removed["acl_entries"] = conn.execute(
            text("DELETE FROM acl_entries WHERE source_system = :s"),
            {"s": SPIKE_SOURCE_SYSTEM},
        ).rowcount
    return removed


def _display_id_for(engine, source_id: str) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE source_id = :sid AND source_system = :s"
            ),
            {"sid": source_id, "s": SPIKE_SOURCE_SYSTEM},
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
            source_system=SPIKE_SOURCE_SYSTEM,
            source_id=source_id,
            attributes=attrs,
            display_id=display_id,   # explicit → never touches the shared namespace
        )
        created += 1 if result.created else 0

    # Relationships need display_ids — resolved at runtime, never hardcoded.
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
            source_system=SPIKE_SOURCE_SYSTEM,
        )
        relationships_created += 1 if inserted else 0

    # Permission hard gate: DENY the unrelated user on the PR entity.
    # object_ref must be the *current* display_id — resolve it, never hardcode.
    pr_display = _display_id_for(engine, "SPIKE-PR-001")
    if not pr_display:
        raise RuntimeError("fixture PR not resolved after upsert")
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
            {"subj": DENIED_USER_REF, "oref": pr_display, "s": SPIKE_SOURCE_SYSTEM},
        )

    return {
        "source_system": SPIKE_SOURCE_SYSTEM,
        "removed": removed,
        "entities_created": created,
        "relationships_created": relationships_created,
        "pr_display_id": pr_display,
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

    pr_display = _display_id_for(engine, "SPIKE-PR-001")
    if pr_display:
        with engine.connect() as conn:
            # exactly one SELECTS relationship
            n_rel = conn.execute(
                text(
                    "SELECT count(*) FROM relationships r "
                    "JOIN entities s ON s.id = r.src_entity_id "
                    "WHERE s.source_system = :s AND r.relation = 'SELECTS'"
                ),
                {"s": SPIKE_SOURCE_SYSTEM},
            ).scalar()
            if n_rel != 1:
                failures.append(f"expected exactly 1 SELECTS relationship, got {n_rel}")

            # PR business state
            attrs = conn.execute(
                text("SELECT attributes FROM entities WHERE display_id = :d"),
                {"d": pr_display},
            ).scalar()
            attrs = attrs or {}
            if attrs.get("review_status") != "pending":
                failures.append(
                    f"PR review_status must start as 'pending', got {attrs.get('review_status')!r}"
                )
            if attrs.get("amount") != 1_280_000:
                failures.append(f"PR amount must be 1280000, got {attrs.get('amount')!r}")

            # ACL deny row must point at the CURRENT display_id
            n_acl = conn.execute(
                text(
                    "SELECT count(*) FROM acl_entries "
                    "WHERE source_system = :s AND object_type = 'entity' "
                    "AND object_ref = :oref AND subject_ref = :subj AND effect = 'deny'"
                ),
                {"s": SPIKE_SOURCE_SYSTEM, "oref": pr_display, "subj": DENIED_USER_REF},
            ).scalar()
            if n_acl != 1:
                failures.append(
                    f"expected 1 DENY acl row for {DENIED_USER_REF} on {pr_display}, got {n_acl} "
                    "(stale display_id? re-run the seeder)"
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
    print(f"PR display_id        : {result['pr_display_id']}  (resolved at runtime)")
    print("-" * 72)

    failures = self_check(engine)
    if failures:
        print("SELF-CHECK FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELF-CHECK PASSED — all 7 fixture entities present, 1 SELECTS relationship,")
    print("                     PR review_status='pending', DENY acl on current display_id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
