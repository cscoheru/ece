"""S2.1 Identity: X-User-Id -> Person + roles + dept + aliases."""
from __future__ import annotations

from ece.db import get_engine
from ece.identity.parser import resolve_identity, upsert_identity


def test_identity_resolve_unknown_user_returns_stub() -> None:
    engine = get_engine()
    ident = resolve_identity(engine, "X-NONEXISTENT-USER-001")
    assert ident.entity_id is None
    assert ident.user_ref == "X-NONEXISTENT-USER-001"


def test_identity_upsert_then_resolve_returns_match() -> None:
    engine = get_engine()
    user_ref = "X-S21-TEST-USER"
    # Clean prior
    with engine.begin() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM entity_aliases WHERE source_ref = :r"
            ),
            {"r": user_ref},
        )
        conn.execute(
            __import__("sqlalchemy").text(
                "DELETE FROM entities WHERE source_id = :r AND entity_type = 'person'"
            ),
            {"r": user_ref},
        )

    display_id = upsert_identity(
        engine,
        x_user_id=user_ref,
        name="S21 Test User",
        department="D01",
        roles=["procurement_manager", "buyer"],
        aliases=["测试用户"],
    )
    assert display_id is not None

    ident = resolve_identity(engine, user_ref)
    assert ident.entity_id is not None
    assert ident.name == "S21 Test User"
    assert ident.department == "D01"
    assert "procurement_manager" in ident.roles
    assert "测试用户" in ident.aliases
    # is_management derived from roles
    assert ident.is_management is True
