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


@dataclass
class Identity:
    """Resolved identity for a user."""

    user_ref: str  # the original X-User-Id value
    entity_id: str | None  # uuid of the person entity, None if not yet created
    display_id: str | None  # human-readable id like 'U001'
    name: str = ""
    department: str = ""
    roles: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    source_system: str = "api:header"
    is_management: bool = False  # derived: any role contains 'manager'


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
            # Person not yet created; return stub for auto-create in S2.4
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

        return Identity(
            user_ref=x_user_id,
            entity_id=str(entity_id),
            display_id=display_id,
            name=name,
            department=department,
            roles=roles,
            aliases=aliases,
        )


def upsert_identity(
    engine: Engine,
    x_user_id: str,
    name: str,
    department: str,
    roles: list[str],
    aliases: list[str] | None = None,
) -> str:
    """Insert or update a person identity from API header info.

    Returns display_id. ON CONFLICT (entity_type, source_system, source_id) DO NOTHING
    then re-fetch display_id (entities pipeline style).
    """
    from ece.entities.pipeline import upsert_entity

    attrs = {"department": department, "roles": roles}
    upsert_entity(
        engine,
        entity_type="person",
        name=name,
        source_system="api:header",
        source_id=x_user_id,
        attributes=attrs,
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
