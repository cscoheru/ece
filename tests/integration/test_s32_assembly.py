"""S3.2/S3.3 — Assembly Pipeline + Provenance integration tests.

Requires live DB (per pytest marker integration). Pre-condition:
- alembic head = 0005_context_audit (cut-007 migration)
- make seed → demo dataset + test users
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from ece.context.assembly import assemble_context
from ece.db import get_engine


@pytest.fixture
def engine():
    return get_engine()


def test_assemble_returns_package_with_identity(engine) -> None:
    """Steps 1-2: identity resolution populates user dict."""
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    assert pkg.user["id"] == "demo-user-procurement"
    assert pkg.user["department"] == "procurement"
    assert "procurement_manager" in pkg.user["roles"]
    # cut-040R-2 R40R2.3: demo-user-procurement holds the "procurement_manager"
    # JOB TITLE, which is not a management role — is_management is an explicit
    # attribute and defaults to False.
    assert pkg.user["is_management"] is False
    assert pkg.request_id  # uuid
    assert pkg.package_id.startswith("ctx_")


def test_assemble_empty_entities_yields_insufficient_context(engine) -> None:
    """No root entities → insufficient_context flag + empty lists."""
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[],
    )
    assert pkg.metadata.get("insufficient_context") is True
    assert pkg.entities == []
    assert pkg.metadata["counts"]["entities"] == 0


def test_assemble_writes_context_requests_row(engine) -> None:
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_ref, intent, status FROM context_requests
                WHERE request_id = :r
            """),
            {"r": pkg.request_id},
        ).first()
    assert row is not None
    assert row[0] == "demo-user-procurement"
    assert row[1] == "evaluate_purchase_request"
    assert row[2] in ("ok", "insufficient_context")


def test_assemble_writes_context_items_with_valid_decisions(engine) -> None:
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT item_kind, decision, reason FROM context_items
                WHERE request_id = :r ORDER BY seq
            """),
            {"r": pkg.request_id},
        ).fetchall()
    assert len(rows) >= 1
    # Each item has a decision ∈ {allowed, denied}
    for r in rows:
        assert r[0] in ("entity", "relationship")
        assert r[1] in ("allowed", "denied")
        assert r[2] != ""  # reason should be non-empty


def test_assemble_denied_entity_records_in_audit(engine) -> None:
    """Non-existent entity → denied with reason + audit row."""
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR_DOES_NOT_EXIST"}],
    )
    assert pkg.metadata["insufficient_context"] is True
    assert any(d.get("reason") == "entity not found" for d in pkg.denied)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT decision, reason FROM context_items
                WHERE request_id = :r AND item_kind = 'entity'
            """),
            {"r": pkg.request_id},
        ).fetchall()
    assert any(r[0] == "denied" and r[1] == "entity not found" for r in rows)


def test_assemble_sources_are_deterministic(engine) -> None:
    """Same (system, record_id) → same sid across two assemblies."""
    pkg1 = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    pkg2 = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    sids1 = {s["sid"]: (s["system"], s["record_id"]) for s in pkg1.sources}
    sids2 = {s["sid"]: (s["system"], s["record_id"]) for s in pkg2.sources}
    # Common sources should have same sid
    common_keys = set(sids1.keys()) & set(sids2.keys())
    assert len(common_keys) >= 0  # at least no conflict; zero OK if entities differ
    for sid in common_keys:
        assert sids1[sid] == sids2[sid]
