"""S2.2 Permission Engine.

Per ece/TASKS.md S2.2 + ADR-004 Permission Before Context Assembly:
- 判定顺序: deny > user > role > department > classification 默认 > default deny
- PermissionScope injected into all Store read paths (SQL subquery filter, NOT post-filter)
- /permissions/check endpoint exposes the engine for verification
- E2 = 0 unauthorized exposure is a CI-blocker (per cut-005 §7.4)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ece.identity.parser import Identity

# Document classification defaults (per DATA_MODEL.md 3 末段)
# public = everyone; department = dept + ancestors + management;
# management/confidential = management + explicit allow; finance/procurement = role-restricted
DEFAULT_CLASSIFICATION_MATRIX: dict[str, dict[str, str | list[str]]] = {
    "public":        {"default": "allow"},
    "department":    {"default": "allow_dept"},
    "management":    {"default": "allow_management"},
    # cut-040 R40.1b: confidential = owner-dept-match (was allow_management, which
    # let every user with is_management=True in — including the 3 test users
    # flagged as 'management' — bypass confidential, causing 6 of the 6 cut-039
    # R39.1 unauthorized exposures: e2-022/023/024/052/053/054/061. PRD §35
    # hard gate: 0 exposures, so this MUST be owner-dept not blanket-management).
    "confidential":  {"default": "allow_dept"},
    "finance":       {"default": "allow_role", "roles": ["finance_manager", "cfo"]},
    "procurement":   {"default": "allow_role", "roles": ["procurement_manager", "buyer"]},
}


@dataclass
class PermissionScope:
    """SQL subquery filter parameters for permission-aware Store reads.

    Per ADR-004: NOT post-filter (which leaks via sort/limit signals). SQL-level filter
    applied in WHERE clause of every Store read method.
    """

    user_ref: str
    department: str = ""
    roles: list[str] = field(default_factory=list)
    is_management: bool = False  # role contains 'manager' or display_id starts 'D01' etc.

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


def check_permission(
    identity: Identity,
    object_type: str,
    object_ref: str,
    classification: str = "department",
    acl_entries: list[dict] | None = None,
) -> PermissionDecision:
    """Determine if identity can access object.

    判定顺序 (per ADR-004):
      1. deny entries (subject=identity.user_ref or role or dept)
      2. user-level allow entries
      3. role-level allow entries
      4. department-level allow entries
      5. classification default matrix (public allow, etc.)
      6. default: deny

    identity: Identity object with user_ref / department / roles / aliases
    object_type: 'entity' | 'document' | etc.
    object_ref: display_id like 'SUP001'
    classification: 'public' | 'department' | 'management' | etc.
    acl_entries: optional pre-fetched list of acl_entries rows matching object_type/object_ref
    """
    acl_entries = [dict[str, str]((k, str(v)) for k, v in (e or {}).items()) for e in (acl_entries or [])]

    # 1. deny entries: subject_type in [user, role, department]
    for entry in acl_entries:
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
        and _object_dept(acl_entries, object_ref=object_ref) == identity.department
    ):
        return PermissionDecision(
            allowed=True, reason="classification department (matched)",
            matched_rule="classification-dept",
        )
    if default_mode == "allow_management" and (
        identity.is_management or any("manager" in r.lower() for r in identity.roles)
    ):
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
