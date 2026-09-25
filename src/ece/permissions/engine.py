"""S2.2 Permission Engine.

Per ece/TASKS.md S2.2 + ADR-004 Permission Before Context Assembly:
- 判定顺序: deny > user > role > department > classification 默认 > default deny
- PermissionScope injected into all Store read paths (SQL subquery filter, NOT post-filter)
- /permissions/check endpoint exposes the engine for verification
- E2 = 0 unauthorized exposure is a CI-blocker (per cut-005 §7.4)

OEI-009 changes (compare to OEI-008):

1. **Time-box (ACL `valid_from` / `valid_to`)** — the columns have been in the
   schema since `0001_initial` and have always been `SELECT`-ed by
   `api/identity.py:118`, but `check_permission` rules 1–4 never looked at
   them. That meant a temporary grant (e.g. "valid for 14 days") stayed
   effective forever. We now fold both columns into both the deny and the
   allow rules. Semantics match DATA_MODEL.md: `valid_from IS NULL -> -∞`,
   `valid_to IS NULL -> +∞`, comparison is half-open
   `[valid_from, valid_to)`. The check is parameterised on `now` so tests
   can drive the boundary deterministically (without monkey-patching the
   clock).

2. **`PermissionScope.org_id`** — the org dimension is now first-class on
   the dataclass. The OEI-009 scope is *minimum* placement: we add the
   field, we don't yet use it as a SELECT-side predicate (no `WHERE org_id
   = :org_id` in any store path). That is the OEI-010 hook — memory has to
   read *after* permission, and the hook lives here.

The deny-then-allow order, the SQL subquery filter at Store level, and the
classification matrix are all unchanged. Per TASK v1.3 §7, this module's
判定顺序 is frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ece.identity.parser import Identity

# Document classification defaults (per DATA_MODEL.md 3 末段)
# public = everyone; department = dept + ancestors + management;
# management/confidential = management + explicit allow; finance/procurement = role-restricted
DEFAULT_CLASSIFICATION_MATRIX: dict[str, dict[str, str | list[str]]] = {
    "public":        {"default": "allow"},
    # cut-040R RC-4 fix: dataset (e2_permission.json) uses 'internal' and
    # 'restricted' classifications that weren't in this matrix → 14 cases
    # expected-allowed silently failed at the matrix miss (default-deny).
    "internal":      {"default": "allow"},
    "department":    {"default": "allow_dept"},
    # cut-040R-2 R40R2.5 (RC-10 — restricted 错置): restricted = DENY unless an
    # explicit ACL allow exists. It was previously allow_dept, which leaked
    # e2-025 (procurement + PR001 + restricted, expected deny). Dataset: 6 of
    # the 7 restricted cases expect deny; the 7th (e2-059) is allowed by an
    # explicit ACL row, which fires before this matrix is consulted.
    "restricted":    {"default": "deny"},
    "management":    {"default": "allow_management"},
    "confidential":  {"default": "allow_dept"},  # cut-040 R40.1b
    "finance":       {"default": "allow_role", "roles": ["finance_manager", "cfo"]},
    "procurement":   {"default": "allow_role", "roles": ["procurement_manager", "buyer"]},
}

# ⚠️ KNOWN MODEL LIMITATION (Codex 第二轮判词 §7, 2026-09-20 — documented, not fixed):
# an acl_entries row is keyed on (subject_type, subject_ref, object_type, object_ref)
# only — it has NO classification dimension. Consequences:
#   1. One ACL row cannot express "allow for user X on object Y *when classified
#      as A*, deny when classified as B".
#   2. Therefore an ACL-explicit test case must not share (subject, object) with a
#      classification test case — the two expectations would be unsatisfiable.
#      That is why cut-040R-2 moved e2-060/e2-061 onto dedicated objects
#      (PR003 / CON002). The test intent was "explicit OBJECT acl", so decoupling
#      was the correct fix.
#   3. If the product later genuinely needs classification-scoped ACLs, the ACL
#      model itself must change (add a classification column / scope predicate) —
#     do NOT work around it by editing datasets again.


@dataclass
class PermissionScope:
    """SQL subquery filter parameters for permission-aware Store reads.

    Per ADR-004: NOT post-filter (which leaks via sort/limit signals). SQL-level filter
    applied in WHERE clause of every Store read method.

    OEI-009: `org_id` is added but NOT yet used as a SELECT-side predicate.
    It exists so the OEI-010 memory pipeline can branch on it (the *read*
    step happens after this scope has been consulted; that order is the
    only thing keeping memory read from re-introducing the post-filter
    side-channel). See `10-design-org-scope.md`.
    """

    user_ref: str
    department: str = ""
    roles: list[str] = field(default_factory=list)
    is_management: bool = False  # role contains 'manager' or display_id starts 'D01' etc.
    org_id: str | None = None  # OEI-009: now first-class; no SELECT-side predicate yet

    def dept_match_clause(self, column: str = "department") -> str:
        """SQL fragment: WHERE department = :user_dept OR :user_dept = '' (no dept set -> no filter).

        Caller is responsible for binding :user_dept. Empty user_dept means no filter applied.
        """
        return f"({column} = :user_dept OR :user_dept = '')"


@dataclass
class PermissionDecision:
    """Result of a permission check."""

    allowed: bool
    reason: str = ""
    matched_rule: str = ""  # which rule in the ordered list fired


def _acl_in_window(
    entry: dict[str, object],
    *,
    now: date,
) -> bool:
    """Is the ACL row in effect at `now`?

    Per DATA_MODEL.md: `valid_from IS NULL -> -∞`,
    `valid_to IS NULL -> +∞`, comparison is half-open `[valid_from, valid_to)`.

    `valid_from = now` -> ACTIVE (boundary inclusive on the left).
    `valid_to   = now` -> INACTIVE (boundary exclusive on the right).
    Returns False when `now` is outside the window — caller treats the row
    as if it doesn't exist.
    """
    vf = entry.get("valid_from")
    vt = entry.get("valid_to")
    if vf is not None and now < vf:
        return False
    if vt is not None and now >= vt:
        return False
    return True


def _now_date(now: datetime | date | None = None) -> date:
    """Coerce `now` to a `date` for half-open comparison.

    Defaults to "now" in UTC. Tests can pass any `date` (deterministic
    boundary coverage without monkey-patching) or a tz-aware `datetime`
    (which gets converted via `.astimezone(timezone.utc).date()`).
    """
    if now is None:
        return datetime.now(tz=timezone.utc).date()
    if isinstance(now, datetime):
        if now.tzinfo is None:
            return now.date()
        return now.astimezone(timezone.utc).date()
    return now


def check_permission(
    identity: Identity,
    object_type: str,
    object_ref: str,
    classification: str = "department",
    acl_entries: list[dict] | None = None,
    engine=None,
    *,
    now: datetime | date | None = None,
) -> PermissionDecision:
    """Determine if identity can access object.

    判定顺序 (per ADR-004):
      1. deny entries (subject=identity.user_ref or role or dept)
      2. user-level allow entries
      3. role-level allow entries
      4. department-level allow entries
      5. classification default matrix (public allow, etc.)
      6. default: deny

    OEI-009 — rules 1–4 now consult `valid_from` / `valid_to` via
    `_acl_in_window(acl_entry, now=now)`. Rows outside the window are
    skipped (treated as if they didn't exist). `now` defaults to UTC today
    so production behaviour is unchanged; tests pass a fixed date for
    boundary coverage (A8).

    identity: Identity object with user_ref / department / roles / aliases
    object_type: 'entity' | 'document' | 'engine_document' | etc.
    object_ref: display_id like 'SUP001' or 'engine_document:42' for engine docs
    classification: 'public' | 'department' | 'management' | etc.
    acl_entries: optional pre-fetched list of acl_entries rows matching object_type/object_ref
    """
    acl_entries = [
        {
            # Coerce non-date scalars to str (the SQL loader returns strings for
            # most columns); preserve `date` for `valid_from` / `valid_to` so
            # _acl_in_window can compare directly (OEI-009 time-box).
            **{
                k: (v if k in ("valid_from", "valid_to") else (str(v) if v is not None else ""))
                for k, v in (e or {}).items()
            }
        }
        for e in (acl_entries or [])
    ]
    today = _now_date(now)

    # 1. deny entries: subject_type in [user, role, department]
    for entry in acl_entries:
        if not _acl_in_window(entry, now=today):
            continue
        effect = entry.get("effect", "")
        subject_type = entry.get("subject_type", "")
        subject_ref = entry.get("subject_ref", "")
        if effect != "deny":
            continue
        if _subject_matches(entry, identity):
            return PermissionDecision(
                allowed=False,
                reason=f"explicit deny for {subject_type}={subject_ref}",
                matched_rule="deny",
            )

    # 2-4. allow entries
    for entry in acl_entries:
        if not _acl_in_window(entry, now=today):
            continue
        effect = entry.get("effect", "")
        subject_type = entry.get("subject_type", "")
        subject_ref = entry.get("subject_ref", "")
        if effect != "allow":
            continue
        if _subject_matches(entry, identity):
            return PermissionDecision(
                allowed=True,
                reason=f"explicit allow for {subject_type}={subject_ref}",
                matched_rule=f"allow-{subject_type}",
            )

    # 5. classification default
    matrix = DEFAULT_CLASSIFICATION_MATRIX.get(classification, {})
    default_mode = matrix.get("default", "deny")

    if default_mode == "allow":
        return PermissionDecision(
            allowed=True, reason="classification public", matched_rule="classification-public",
        )
    if (
        default_mode == "allow_dept"
        and identity.department
        and object_ref
        and _object_dept(acl_entries, object_ref=object_ref, engine=engine) == identity.department
    ):
        return PermissionDecision(
            allowed=True, reason="classification department (matched)",
            matched_rule="classification-dept",
        )
    if (
        default_mode == "allow_management"
        and identity.is_management
    ):
        # cut-040R RC-2 fix: tighten allow_management — require EXPLICIT
        # is_management flag. Substring check ("manager" in role.lower()) was
        # too loose: procurement_manager / finance_manager roles fired this
        # branch even though no test user is actually "management" — exposed
        # e2-029/030/055. Without explicit is_management=True, deny.
        return PermissionDecision(
            allowed=True, reason="classification management",
            matched_rule="classification-management",
        )
    if default_mode == "allow_role":
        required_roles_value = matrix.get("roles", [])
        required_roles = set(required_roles_value) if isinstance(required_roles_value, list) else set()
        if required_roles & set(identity.roles):
            return PermissionDecision(
                allowed=True,
                reason=f"classification role (matched: {sorted(required_roles & set(identity.roles))})",
                matched_rule="classification-role",
            )

    # 6. default deny
    return PermissionDecision(
        allowed=False, reason="default deny (no matching rule)", matched_rule="default-deny",
    )


def _subject_matches(entry: dict[str, object], identity: Identity) -> bool:
    """Does this acl_entry subject match the identity?"""
    st = entry.get("subject_type", "")
    sr = entry.get("subject_ref", "")
    if not st or not sr:
        return False
    if st == "user" and sr == identity.user_ref:
        return True
    if st == "role" and sr in identity.roles:
        return True
    return st == "department" and sr == identity.department


def _object_dept(
    acl_entries: list[dict],
    object_ref: str | None = None,
    engine=None,
) -> str:
    """Resolve entity dept for allow_dept classification default.

    Per cut-006 §7.3 R2 acceptance:
    - Priority 1: read entities.attributes.department from DB (live)
    - Priority 2: fallback heuristic prefix_map (when engine is None or entity not found)
    - Returns "" when object_ref unknown AND no ACL hint (default deny)

    Used by allow_dept branch: department default matches identity.department.
    """
    if not object_ref:
        return ""
    if engine is not None:
        try:
            from sqlalchemy import text as _sql_text
            with engine.connect() as conn:
                row = conn.execute(
                    _sql_text(
                        "SELECT attributes->>'department' FROM entities WHERE display_id = :d"
                    ),
                    {"d": object_ref},
                ).first()
            if row and row[0]:
                return str(row[0])
        except Exception:
            pass  # fall through to prefix_map
    # Prefix-map fallback (v0 demo seed may not yet have department attr)
    prefix_map = {
        "SUP": "procurement",
        "PR": "procurement",
        "PO": "procurement",
        "POL": "procurement",
        "APR": "procurement",
        "CON": "finance",
        "DOC": "all",
    }
    for prefix, dept in prefix_map.items():
        if object_ref.startswith(prefix):
            return dept if dept != "all" else ""
    return ""


__all__ = [
    "DEFAULT_CLASSIFICATION_MATRIX",
    "PermissionScope",
    "PermissionDecision",
    "check_permission",
]