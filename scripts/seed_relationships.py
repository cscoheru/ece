"""Seed demo relationships — thin CLI wrapper over `ece.seed.seed_demo_relationships`.

R2: this used to hold the ONLY implementation. `make seed` never called it, so
rebuilding the DB produced 428 entities and ZERO relationships, and E4/E5 then
measured an empty graph. The logic now lives in `src/ece/seed.py` so that
`run_seed()` (the canonical entrypoint) and this script share ONE implementation
instead of two copies that drift apart.

Kept as a standalone command because existing callers and docs use it:
    uv run python scripts/seed_relationships.py
and three integration tests shell out to it, depending on the exit-code contract
(0 = seeded, 1 = could not seed) and on the `Total relationships in DB: N` line.

R2.1: exit 1 now also covers "the fixture would come out incomplete" (a rejected
edge, or fewer rows than `PRs x 6`). Previously such a run exited 0 while
building less than the canonical fixture.

Prefer `make seed`, which now performs this step automatically.

Per DATA_MODEL.md §2 + ontology whitelist (ece/domain_packs/procurement/ontology.py).
"""
from __future__ import annotations

import sys

from ece.db import get_engine
from ece.seed import seed_demo_relationships


def main() -> int:
    engine = get_engine()

    print("Seeding 4 department entities...")
    result = seed_demo_relationships(engine)

    # Report rejections BEFORE the ok check: since R2.1 a rejected edge makes the
    # seed fail, so printing them only on the happy path would hide the reason.
    rejected: list[str] = result["rejected"]  # type: ignore[assignment]
    if rejected:
        print(f"  REJECTED {len(rejected)} relationship(s):")
        for r in rejected[:5]:
            print(f"    {r}")

    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}", file=sys.stderr)
        return 1

    removed = result["removed"]
    if removed:
        print(f"  Removed {removed} prior 'demo:seed_relationships' rows (canonical reseed)")

    inserted: dict[str, int] = result["inserted_by_type"]  # type: ignore[assignment]
    print(f"\nSeeded relationships from {result['prs']} PRs:")
    for rel, count in inserted.items():
        print(f"  {rel}: {count} new insertions")

    # Kept verbatim: existing tooling and archived stdout compare on this line.
    print(f"Total relationships in DB: {result['total_in_db']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
