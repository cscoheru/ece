"""S2.1 Identity: parse X-User-Id -> Person + roles + department + aliases.

Per ece/TASKS.md S2.1:
- X-User-Id header -> Person entity (entity_type='person') + roles + dept + aliases
- Aliases table lookup: source_id = X-User-Id, alias method='api-header'
- Acceptance: E1 子集通过 (entity resolution unit tests)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _coerce_org_id(raw: object) -> str | None:
    """`entities.attributes.org_id` -> `str | None` (OEI-010 A1).

    Missing key / non-string / empty-or-whitespace -> `None` ("no org claim").
    A non-empty string is taken verbatim — no case folding, no normalization:
    the value is used as an ACL `subject_ref` and must match byte-for-byte.

    `None` is NOT the same as `""`: `_subject_matches` treats a falsy
    `identity.org_id` as "cannot match any org row", so an absent org claim
    can never satisfy an `subject_type='org'` ACL entry.
    """
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


@dataclass
class Identity:
    """Resolved identity for a user."""

    user_ref: str  # the original X-User-Id value
    entity_id: str | None = None  # uuid of the person entity, None if not yet created
    display_id: str | None = None  # human-readable id like 'U001'
    name: str = ""
    department: str = ""
    roles: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_system: str = "api:header"
    is_management: bool = False  # cut-040R-2 R40R2.3: EXPLICIT seed attribute, never derived from role names
    # OEI-009 added the field (minimum placement); **OEI-010 A1 makes it real**:
    # `resolve_identity` now reads `entities.attributes.org_id` and
    # `upsert_identity(org_id=...)` writes it (incremental JSONB merge, so
    # department/roles/is_management survive). Source of truth is the DB
    # trusted attribute — the `X-Org-Id` header is NOT in the decision path
    # (`OEI-009/workspace/10-design-org-scope.md` §2, decision 2.B).
    org_id: str | None = None

    @classmethod
    def anonymous(cls) -> Identity:
        """An Identity representing an unauthenticated caller.

        `user_ref=""` is the sentinel — the consulting permissions filter
        (`_is_anonymous`) treats None-or-empty as anonymous. All other fields
        are deliberately zero so any ACL subject match fails (no user, no
        dept, no roles, not management).
        """
        return cls(
            user_ref="",
            entity_id=None,
            display_id=None,
            name="",
            department="",
            roles=[],
            aliases=[],
            is_management=False,
            org_id=None,
        )

    @classmethod
    def from_engine_caller(
        cls, user_ref: str | None, *, source: str = "header"
    ) -> Identity:
        """Build a minimal Identity from the Port-side caller.

        Used when the filter needs an Identity but the consulting route has
        not (or could not) resolved the full DB row. We accept the caller
        at face value — the *filter* layer is the only place that enforces
        anonymous semantics, and the *route* layer is the only place that
        must guard against caller-supplied principal (TASK §1.3 事实 B).
        For identified callers, the consulting route should prefer
        `resolve_identity(engine, user_ref)` to get department / roles /
        is_management; this classmethod is the no-DB shortcut.
        """
        if not user_ref:
            return cls.anonymous()
        return cls(
            user_ref=user_ref,
            entity_id=None,
            display_id=None,
            name="",
            department="",
            roles=[],
            aliases=[],
            source_system=f"caller:{source}",
            is_management=False,
            org_id=None,
        )


def resolve_identity(engine: Engine, x_user_id: str) -> Identity:
    """Resolve X-User-Id header to a Person identity.

    Lookup chain (per ece/CLAUDE.md S2 + ADR-010 domain pack isolation):
      1. entities WHERE source_id = x_user_id AND entity_type = 'person'
      2. If not found, return Identity with user_ref but no entity_id (auto-create later)
      3. entity_aliases for additional names (method = 'api-header' or 'manual')
      4. attributes JSONB: department + roles list
    """
    if not x_user_id:
        raise ValueError("X-User-Id header is required")

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, display_id, name, attributes
                FROM entities
                WHERE entity_type = 'person' AND source_id = :sid
                LIMIT 1
            """),
            {"sid": x_user_id},
        ).first()

        if row is None:
            # Person not yet created; return stub for auto-create in S2.4.
            # OEI-010 A1: an unknown caller has NO trusted attributes, so
            # `org_id` stays at its default None (four-state test: 未知用户).
            return Identity(
                user_ref=x_user_id,
                entity_id=None,
                display_id=None,
                name="",
                department="",
                roles=[],
                aliases=[],
            )

        entity_id, display_id, name, attrs = row
        attrs = attrs if isinstance(attrs, dict) else {}
        department = attrs.get("department", "")

        # roles: stored as JSONB list
        roles_raw = attrs.get("roles", [])
        roles: list[str] = roles_raw if isinstance(roles_raw, list) else []

        # Aliases: pull from entity_aliases
        alias_rows = conn.execute(
            text("""
                SELECT alias FROM entity_aliases
                WHERE entity_id = :eid AND method IN ('api-header', 'manual')
            """),
            {"eid": entity_id},
        ).fetchall()
        aliases: list[str] = [r[0] for r in alias_rows]

        # cut-040R-2 R40R2.3 (RC-8 — 空操作修复): is_management MUST be an
        # explicit stored attribute, never derived from a role-name substring.
        # The previous `any("manager" in r.lower() for r in roles)` made every
        # *_manager job title (procurement_manager, finance_manager) count as
        # management — engine.py's R40R.1 "tightening" only moved that same
        # substring from the engine into the parser, so it was a no-op and all
        # six management-classification cases (expected deny) still leaked.
        is_management = bool(attrs.get("is_management", False))

        # OEI-010 A1: org dimension now has a *source*. Same trust boundary as
        # department / roles / is_management (all DB-derived attributes); a
        # caller cannot claim an org. Missing / non-string / empty -> None.
        org_id = _coerce_org_id(attrs.get("org_id"))

        return Identity(
            user_ref=x_user_id,
            entity_id=str(entity_id),
            display_id=display_id,
            name=name,
            department=department,
            roles=roles,
            aliases=aliases,
            is_management=is_management,
            org_id=org_id,
        )


def upsert_identity(
    engine: Engine,
    x_user_id: str,
    name: str,
    department: str,
    roles: list[str],
    aliases: list[str] | None = None,
    is_management: bool = False,
    org_id: str | None = None,
) -> str:
    """Insert or update a person identity from API header info.

    Returns display_id. ON CONFLICT (entity_type, source_system, source_id) DO NOTHING
    then re-fetch display_id (entities pipeline style).

    cut-040R-2 R40R2.3: `is_management` is stored as an explicit attribute
    (default False) so the permission engine never has to infer it from role
    names.

    OEI-010 A1: `org_id` is a **keyword argument with a default of `None`**, so
    every existing caller is unchanged and "not passed" means "do not write the
    key" (back-compat).

    ⚠️ The `attributes` write is NOT a plain overwrite. `upsert_entity` inserts
    with `ON CONFLICT ... DO NOTHING`, so on a re-run (the canonical seed chain
    is replayed on an existing DB) an already-present person row would keep its
    OLD attributes and silently never receive `org_id`. We therefore merge with
    `attributes || jsonb_build_object('org_id', ...)`: incremental, so
    department / roles / is_management are preserved, and idempotent, so
    re-running the seed is safe. This is the same `||` idiom `seed.py`'s
    `_seed_entity_departments` uses.
    """
    from ece.entities.pipeline import upsert_entity

    attrs: dict[str, object] = {
        "department": department,
        "roles": roles,
        "is_management": is_management,
    }
    # Only include the key when the caller actually supplied an org — "not
    # passed" must stay "absent from the JSONB", not "set to null".
    if org_id is not None:
        attrs["org_id"] = org_id

    upsert_entity(
        engine,
        entity_type="person",
        name=name,
        source_system="api:header",
        source_id=x_user_id,
        attributes=attrs,
    )

    if org_id is not None:
        # Self-heal path for rows that already existed (insert was a no-op).
        # Scoped to this exact person row; `||` preserves every other key.
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE entities
                    SET attributes = COALESCE(attributes, '{}'::jsonb)
                                     || jsonb_build_object('org_id', CAST(:org AS text))
                    WHERE entity_type = 'person'
                      AND source_system = 'api:header'
                      AND source_id = :sid
                """),
                {"org": org_id, "sid": x_user_id},
            )

    # Re-fetch display_id for caller
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'person' AND source_id = :sid
            """),
            {"sid": x_user_id},
        ).first()
    display_id = row[0] if row else None

    # Add aliases if provided (entity_aliases)
    if aliases and display_id:
        with engine.begin() as conn:
            eid_row = conn.execute(
                text("SELECT id FROM entities WHERE display_id = :d"),
                {"d": display_id},
            ).first()
            if eid_row:
                eid = eid_row[0]
                for alias in aliases:
                    if not alias or alias == x_user_id:
                        continue
                    conn.execute(
                        text("""
                            INSERT INTO entity_aliases
                                (entity_id, alias, norm_alias, method, status, source_system, source_ref)
                            VALUES (:eid, :alias, :norm, 'manual', 'confirmed', 'api:header', :ref)
                            ON CONFLICT DO NOTHING
                        """),
                        {"eid": eid, "alias": alias, "norm": alias.lower().strip(), "ref": x_user_id},
                    )

    return display_id or ""
