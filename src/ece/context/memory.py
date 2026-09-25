"""OEI-010 Step 6.9 — persistent memory selection (READ, after permission).

Where this sits
---------------
`assemble_context` is a fixed-order pipeline (ADR-004: permission before
context). This module is the memory step, inserted **after** documents /
structured data and **before** rank/truncate, and — crucially — it does its own
per-row `check_permission` **before** anything is returned. Memory is therefore
never "returned and then filtered": that post-filter shape is exactly the
side-channel OEI-009 closed for engine results, and TASK §0 forbids
re-introducing it here.

Two layers, deliberately
------------------------
1. **Candidate set** (SQL): rows the caller *could* be asking about —
   `scope='user' AND owner_ref=<me>` or `scope='org' AND owner_ref=<my org>`,
   live and unexpired. This is a *scope* narrowing, not an authorization.
2. **Per-row authorization** (`authorize`): each candidate is handed to
   `check_permission(object_type='memory', object_ref='memory:<id>',
   classification=<row.classification>, acl_entries=<memory ACLs> )`.
   `classification` defaults to `restricted` -> `default deny`, so the only way
   a memory becomes visible is an explicit `effect='allow'` ACL row naming the
   caller (user scope) or their org (org scope).

Fail-closed properties
----------------------
- No ACL row -> no visibility. Merely existing is not enough.
- A row whose `owner_ref` matches nobody related to the caller is never even a
  candidate.
- Denied candidates are **silently dropped**: they are not injected, and they
  are **not** written to `context_items` either. Recording "memory:7 denied"
  would leak the *existence* of memory 7 to whoever can read the audit trace —
  the same existence side-channel OEI-009 shut. TASK §3.5 marks denied-candidate
  audit entries as optional ("可"), so we take the fail-closed option.
  Trade-off: a denial is not individually auditable. The injected set is, which
  is what the compliance requirement (§A8 "可追溯") actually asks for.

Pure functions vs DB access
---------------------------
`is_active`, `matches_scope`, `authorize`, `order_candidates`,
`order_and_truncate`, `to_item` and `audit_items` are pure — they take plain
dicts and an `Identity`, so the whole policy is unit-testable with no Postgres.
Only `load_acl_for_memory` and `select_memory` touch the DB.

The SQL WHERE clause and the Python predicates (`is_active` / `matches_scope`)
state the SAME rule. The SQL is a narrowing optimization; the Python predicates
are authoritative and run on every fetched row, so the two cannot diverge in
the unsafe direction (a row that should be hidden can only be hidden twice).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from ece.permissions.engine import check_permission

#: Budget: at most this many memories enter one context package (TASK §3.4).
MEMORY_LIMIT = 10

#: Provenance system tag for the audit `sources[]` of an injected memory.
AUDIT_SYSTEM = "ece:memory"

#: `object_type` used for ACL rows governing memory objects.
ACL_OBJECT_TYPE = "memory"

# Columns selected everywhere (kept in one place so `SELECT *` never sneaks in
# and silently changes the row shape the pure functions depend on).
_COLUMNS = (
    "id, scope, owner_ref, statement, classification, source, source_ref, "
    "confidence, created_at, updated_at, expires_at, deleted_at"
)


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────


def object_ref_for(memory_id: object) -> str:
    """ACL / audit ref for a memory row: `memory:<id>`."""
    return f"memory:{memory_id}"


def resolve_now(now: datetime | None = None) -> datetime:
    """Tz-aware "now" for expiry comparisons.

    A naive datetime is interpreted as UTC rather than rejected — the value is
    only ever compared against `timestamptz` columns, and guessing the server
    local zone would make the same row active or expired depending on where the
    process runs.
    """
    if now is None:
        return datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now


def is_active(row: Mapping[str, Any], *, now: datetime) -> bool:
    """Is this memory live at `now`? (TASK §3.6)

    `deleted_at` non-null -> soft-deleted -> never injected.
    `expires_at` non-null and `<= now` -> expired -> never injected.
    `expires_at IS NULL` -> never expires.

    Half-open on the right, matching the ACL window convention
    (`valid_to = now` is already INACTIVE): a memory expiring exactly at `now`
    is expired.
    """
    if row.get("deleted_at") is not None:
        return False
    expires_at = row.get("expires_at")
    if expires_at is None:
        return True
    return expires_at > now


def matches_scope(
    row: Mapping[str, Any], *, user_ref: str, org_id: str | None
) -> bool:
    """Is this row in the caller's own scope?

    `user` rows: only their owner. `org` rows: only a caller with a resolved,
    matching org — a caller with no org claim (`None` / `""`) matches nothing,
    so an org memory can never leak to an org-less caller.
    """
    scope = row.get("scope")
    owner_ref = row.get("owner_ref")
    if scope == "user":
        return bool(user_ref) and owner_ref == user_ref
    if scope == "org":
        return bool(org_id) and owner_ref == org_id
    return False


def _recency_key(row: Mapping[str, Any]) -> tuple[str, int]:
    """Total order key: newest first, ties broken by descending id.

    `created_at` is normalised to an ISO string so DB rows (datetime) and
    hand-built test stubs (str) sort identically, and so the ordering is
    byte-stable across runs — A7 requires N=5 identical injections including
    order.
    """
    created = row.get("created_at")
    if hasattr(created, "isoformat"):
        created_key = created.isoformat()  # type: ignore[union-attr]
    else:
        created_key = str(created or "")
    return (created_key, int(row.get("id") or 0))


def order_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic order: **org scope first**, then newest-first within group.

    Two stable sorts rather than one composite key: the second sort
    (`scope != 'org'`) only regroups, so the `(created_at DESC, id DESC)` order
    from the first survives intact inside each group. `id` makes the order
    total, which is what makes repeated assembly byte-identical.
    """
    by_recency = sorted(rows, key=_recency_key, reverse=True)
    return sorted(by_recency, key=lambda r: r.get("scope") != "org")


def order_and_truncate(
    rows: list[dict[str, Any]], limit: int = MEMORY_LIMIT
) -> tuple[list[dict[str, Any]], int]:
    """Apply the budget. Returns `(kept, dropped)`.

    `dropped` counts candidates dropped by the budget **after** authorization
    (TASK §3.4 orders the steps: authorize, then sort/budget). Denied rows are
    not "dropped" — they were never eligible and are not reported.
    """
    ordered = order_candidates(rows)
    kept = ordered[:limit]
    return kept, max(0, len(ordered) - len(kept))


def to_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """The one injected-memory shape (TASK §3.5), and nothing more.

    Exactly these 7 keys — no `owner_ref`, no `classification`, no
    `_matched_rule`. `confidence` is normalised to `float | None` (`numeric`
    arrives as `Decimal`, which does not JSON-encode cleanly), and the two
    timestamps become ISO strings so two runs compare byte-for-byte.
    """
    confidence = row.get("confidence")
    if isinstance(confidence, Decimal):
        confidence = float(confidence)
    elif confidence is not None:
        confidence = float(confidence)

    def _iso(value: object) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else None  # type: ignore[union-attr]

    return {
        "ref": object_ref_for(row.get("id")),
        "scope": row.get("scope"),
        "statement": row.get("statement"),
        "source": row.get("source"),
        "confidence": confidence,
        "created_at": _iso(row.get("created_at")),
        "expires_at": _iso(row.get("expires_at")),
    }


def audit_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`items_for_audit` entries for the injected memories (TASK §3.5).

    Takes the **authorized rows** (`select_memory`'s internal kept list, which
    still carries `_matched_rule`) — not `to_item` output, whose 7-key shape
    deliberately drops the rule. `reason` records which ACL rule authorized the
    injection.

    `kind='memory'`, `decision='allowed'`. The **statement never appears here**
    — the audit records *that* a memory was injected and *why* it was
    authorized, not its content. (Content lives in the package the caller
    already receives; copying it into the audit table would widen the blast
    radius of an audit-read compromise for no traceability gain.)
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        ref = object_ref_for(row.get("id"))
        out.append({
            "kind": "memory",
            "ref": ref,
            "source": {"system": AUDIT_SYSTEM, "record_id": ref},
            "decision": "allowed",
            "reason": f"acl:{row.get('_matched_rule') or 'allow'}",
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Authorization
# ─────────────────────────────────────────────────────────────────────────────


def authorize(
    rows: list[dict[str, Any]],
    identity: Any,
    acl_by_ref: Mapping[str, list[dict]],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    """Keep only the rows `check_permission` allows. Fail-closed.

    Each row is judged as an independent object, on its own `classification`
    (which the write path always sets to `restricted`) and its own ACL rows.
    The surviving rows carry `_matched_rule` so the audit reason records which
    rule fired.

    NOTE: this deliberately does NOT reuse `assembly._load_acl_for` — that
    helper hardcodes `object_type='entity'` and returns `valid_from` /
    `valid_to` as `None`, which would both query the wrong object type and
    silently disable the OEI-009 time-box on this path (TASK §1.6).
    """
    allowed: list[dict[str, Any]] = []
    for row in rows:
        ref = object_ref_for(row.get("id"))
        decision = check_permission(
            identity=identity,
            object_type=ACL_OBJECT_TYPE,
            object_ref=ref,
            classification=str(row.get("classification") or "restricted"),
            acl_entries=list(acl_by_ref.get(ref, [])),
            now=now,
        )
        if not decision.allowed:
            continue
        enriched = dict(row)
        enriched["_matched_rule"] = decision.matched_rule
        allowed.append(enriched)
    return allowed


def load_acl_for_memory(
    engine: Engine, object_refs: list[str]
) -> dict[str, list[dict]]:
    """Load `object_type='memory'` ACL rows, keyed by `object_ref`.

    Unlike `assembly._load_acl_for`, this
    1. filters on the **memory** object type (not `entity`), and
    2. returns the real `valid_from` / `valid_to` columns, so a time-boxed
       grant on a memory actually expires (OEI-009 semantics, unchanged).
    """
    if not object_refs:
        return {}
    stmt = text(f"""
        SELECT object_ref, subject_type, subject_ref, effect,
               valid_from, valid_to, source_system
        FROM acl_entries
        WHERE object_type = :otype AND object_ref IN :refs
    """).bindparams(bindparam("refs", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(
            stmt, {"otype": ACL_OBJECT_TYPE, "refs": list(object_refs)}
        ).fetchall()

    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r[0], []).append({
            "subject_type": r[1],
            "subject_ref": r[2],
            "effect": r[3],
            "valid_from": r[4],
            "valid_to": r[5],
            "source_system": r[6],
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The step
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MemorySelection:
    """Result of the memory step.

    `items`      — injected memories, final shape + order (`to_item` output).
    `audit`      — `items_for_audit` entries for exactly those memories.
    `dropped`    — authorized candidates cut by `MEMORY_LIMIT` (-> metadata).
    `candidates` — how many rows entered authorization (diagnostics only; not
                   exposed in the package, since a count is itself a signal).
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    dropped: int = 0
    candidates: int = 0


def select_memory(
    engine: Engine,
    identity: Any,
    *,
    now: datetime | None = None,
    limit: int = MEMORY_LIMIT,
) -> MemorySelection:
    """Run the memory step for `identity`. Never raises on a denial."""
    now_dt = resolve_now(now)

    # `CAST(:org_id AS text)` is required, not cosmetic: `:org_id IS NOT NULL`
    # gives Postgres no type context for the placeholder and it refuses to plan
    # the statement.
    stmt = text(f"""
        SELECT {_COLUMNS}
        FROM memories
        WHERE deleted_at IS NULL
          AND (expires_at IS NULL OR expires_at > :now)
          AND (
                (scope = 'user' AND owner_ref = :user_ref)
             OR (CAST(:org_id AS text) IS NOT NULL
                 AND scope = 'org' AND owner_ref = :org_id)
              )
    """)
    with engine.connect() as conn:
        raw = conn.execute(
            stmt,
            {
                "now": now_dt,
                "user_ref": identity.user_ref,
                "org_id": identity.org_id,
            },
        ).fetchall()

    columns = [c.strip() for c in _COLUMNS.split(",")]
    candidates = [dict(zip(columns, r, strict=True)) for r in raw]

    # Authoritative predicates (the SQL above is only a narrowing pass).
    candidates = [
        row for row in candidates
        if is_active(row, now=now_dt)
        and matches_scope(row, user_ref=identity.user_ref, org_id=identity.org_id)
    ]

    acl_by_ref = load_acl_for_memory(
        engine, [object_ref_for(row["id"]) for row in candidates]
    )
    authorized = authorize(candidates, identity, acl_by_ref, now=now_dt)
    kept, dropped = order_and_truncate(authorized, limit=limit)

    return MemorySelection(
        items=[to_item(row) for row in kept],
        audit=audit_items(kept),
        dropped=dropped,
        candidates=len(candidates),
    )


__all__ = [
    "ACL_OBJECT_TYPE",
    "AUDIT_SYSTEM",
    "MEMORY_LIMIT",
    "MemorySelection",
    "audit_items",
    "authorize",
    "is_active",
    "load_acl_for_memory",
    "matches_scope",
    "object_ref_for",
    "order_and_truncate",
    "order_candidates",
    "resolve_now",
    "select_memory",
    "to_item",
]
