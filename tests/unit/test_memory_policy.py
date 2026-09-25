"""OEI-010 — DB-free unit tests for the memory policy.

Everything here is pure: plain dicts, an `Identity`, and stub ACL rows. No
Postgres, no FastAPI client. The integration evidence (HTTP + SQL) lives in
`onyx-lab/OEI-010/evidence/`; this file is the part that must stay green on a
laptop with no database.

Covers:
  A4  the write matrix (both gates) — authorization on the scope object, and
      the "the body may not name a principal you don't own" rule,
  A6  expiry / soft-delete filtering,
  A7  deterministic ordering and the 10-item budget,
  A10 the injected shape, the audit shape, and `ContextPackage.to_dict()`
      staying backward-compatible.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from ece.api.memory import (
    MEMORY_CLASSIFICATION,
    WRITE_SCOPE_OBJECT_TYPE,
    _check_owner_matches_credential,
    _scope_object_ref,
)
from ece.context.assembly import ContextPackage
from ece.context.memory import (
    AUDIT_SYSTEM,
    MEMORY_LIMIT,
    audit_items,
    authorize,
    is_active,
    matches_scope,
    order_and_truncate,
    order_candidates,
    to_item,
)
from ece.identity.parser import Identity
from ece.permissions.engine import check_permission

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _ident(**kwargs) -> Identity:
    return Identity(
        user_ref=kwargs.pop("user_ref", "alice"),
        department=kwargs.pop("department", ""),
        roles=kwargs.pop("roles", []),
        org_id=kwargs.pop("org_id", None),
    )


def _scope_acl(subject_type: str, subject_ref: str, effect: str = "allow") -> dict:
    return {
        "subject_type": subject_type,
        "subject_ref": subject_ref,
        "effect": effect,
        "valid_from": None,
        "valid_to": None,
        "source_system": "test",
    }


def _write_allowed(identity: Identity, scope: str, owner_ref: str, acl: list[dict]) -> bool:
    """Exactly what `api/memory.py::_authorize_write` asks the engine."""
    object_ref = _scope_object_ref(scope, owner_ref)
    return check_permission(
        identity=identity,
        object_type=WRITE_SCOPE_OBJECT_TYPE,
        object_ref=object_ref,
        classification=MEMORY_CLASSIFICATION,
        acl_entries=acl,
    ).allowed


def _row(
    memory_id: int,
    *,
    scope: str = "user",
    owner_ref: str = "alice",
    statement: str = "s",
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    deleted_at: datetime | None = None,
    classification: str = MEMORY_CLASSIFICATION,
) -> dict:
    return {
        "id": memory_id,
        "scope": scope,
        "owner_ref": owner_ref,
        "statement": statement,
        "classification": classification,
        "source": "explicit:api",
        "source_ref": None,
        "confidence": None,
        "created_at": created_at or NOW,
        "updated_at": NOW,
        "expires_at": expires_at,
        "deleted_at": deleted_at,
    }


def _memory_acl(subject_type: str, subject_ref: str) -> dict:
    return {
        "subject_type": subject_type,
        "subject_ref": subject_ref,
        "effect": "allow",
        "valid_from": None,
        "valid_to": None,
        "source_system": "memory:create",
    }


# ═══════════════════════════════════════════════════════════════════════════
# A4 — write matrix
# ═══════════════════════════════════════════════════════════════════════════


def test_own_user_scope_is_writable() -> None:
    """Seed row `subject_type='user', subject_ref=<me>, object_ref='user:<me>'`."""
    acl = [_scope_acl("user", "alice")]
    assert _write_allowed(_ident(user_ref="alice"), "user", "alice", acl) is True


def test_another_users_scope_is_not_writable() -> None:
    """bob is not reached by the grant that names alice."""
    acl = [_scope_acl("user", "alice")]
    assert _write_allowed(_ident(user_ref="bob"), "user", "alice", acl) is False


def test_org_scope_is_denied_without_the_org_admin_role() -> None:
    acl = [_scope_acl("role", "org_admin")]
    assert (
        _write_allowed(
            _ident(user_ref="u", roles=["buyer"], org_id="org-A"),
            "org",
            "org-A",
            acl,
        )
        is False
    )


def test_org_scope_is_allowed_for_org_admin() -> None:
    """Candidate A (admins) is expressed purely as an ACL row."""
    acl = [_scope_acl("role", "org_admin")]
    assert (
        _write_allowed(
            _ident(user_ref="u", roles=["admin", "org_admin"], org_id="org-A"),
            "org",
            "org-A",
            acl,
        )
        is True
    )


def test_missing_scope_row_means_deny() -> None:
    """Fail-closed: no ACL row at all -> the caller cannot write, whoever it is.

    This is the property that makes the write policy *data*: forgetting to
    provision a scope denies the write instead of allowing it.
    """
    assert _write_allowed(_ident(user_ref="alice"), "user", "alice", []) is False
    assert (
        _write_allowed(
            _ident(user_ref="a", roles=["admin", "org_admin"], org_id="org-A"),
            "org",
            "org-A",
            [],
        )
        is False
    )


# --- gate 1: the body may not name a principal the credential doesn't own ----


def test_body_claiming_another_user_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        _check_owner_matches_credential(_ident(user_ref="bob"), "user", "alice")
    assert exc.value.status_code == 403


def test_body_claiming_another_org_is_rejected() -> None:
    """An org-A admin may not write org-B's memory by naming it.

    This is what bounds candidate A to "your OWN org": the ACL row is keyed on
    the `org_admin` ROLE (which does not carry an org), so without this gate a
    role holder in any org could write any org's scope.
    """
    with pytest.raises(HTTPException) as exc:
        _check_owner_matches_credential(
            _ident(user_ref="a", roles=["org_admin"], org_id="org-A"), "org", "org-B"
        )
    assert exc.value.status_code == 403


def test_org_write_without_any_org_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        _check_owner_matches_credential(_ident(user_ref="a", org_id=None), "org", "org-A")
    assert exc.value.status_code == 403


def test_matching_claims_pass_gate_one() -> None:
    """The happy paths must not raise — a gate that always fires is not a gate."""
    _check_owner_matches_credential(_ident(user_ref="alice"), "user", "alice")
    _check_owner_matches_credential(_ident(user_ref="a", org_id="org-A"), "org", "org-A")


# ═══════════════════════════════════════════════════════════════════════════
# A6 — expiry / soft delete
# ═══════════════════════════════════════════════════════════════════════════


def test_live_memory_is_active() -> None:
    assert is_active(_row(1), now=NOW) is True


def test_soft_deleted_memory_is_inactive() -> None:
    assert is_active(_row(1, deleted_at=NOW - timedelta(days=1)), now=NOW) is False


def test_expired_memory_is_inactive() -> None:
    assert is_active(_row(1, expires_at=NOW - timedelta(seconds=1)), now=NOW) is False


def test_future_expiry_is_active() -> None:
    assert is_active(_row(1, expires_at=NOW + timedelta(days=7)), now=NOW) is True


def test_expiry_boundary_is_half_open() -> None:
    """`expires_at == now` is EXPIRED, matching the ACL window convention."""
    assert is_active(_row(1, expires_at=NOW), now=NOW) is False


# ═══════════════════════════════════════════════════════════════════════════
# scope candidate filter
# ═══════════════════════════════════════════════════════════════════════════


def test_scope_filter_four_states() -> None:
    alice_user_row = _row(1, scope="user", owner_ref="alice")
    org_a_row = _row(2, scope="org", owner_ref="org-A")
    org_b_row = _row(3, scope="org", owner_ref="org-B")

    # same org -> sees the org row + own user row
    assert matches_scope(org_a_row, user_ref="alice", org_id="org-A") is True
    assert matches_scope(alice_user_row, user_ref="alice", org_id="org-A") is True
    # other org -> sees neither the other org's row nor someone else's user row
    assert matches_scope(org_a_row, user_ref="bob", org_id="org-B") is False
    assert matches_scope(alice_user_row, user_ref="bob", org_id="org-B") is False
    # no org -> never sees an org row
    assert matches_scope(org_a_row, user_ref="carol", org_id=None) is False
    assert matches_scope(org_b_row, user_ref="carol", org_id="") is False


def test_unknown_scope_value_matches_nothing() -> None:
    """A row with an out-of-vocabulary scope is not a candidate for anyone.

    The CHECK constraint makes this unreachable in the DB; the guard is here so
    a future scope value cannot silently fall through to "visible".
    """
    weird = _row(1, scope="team", owner_ref="alice")
    assert matches_scope(weird, user_ref="alice", org_id="org-A") is False


# ═══════════════════════════════════════════════════════════════════════════
# A7 — deterministic order + budget
# ═══════════════════════════════════════════════════════════════════════════


def test_org_scope_comes_first_then_newest() -> None:
    rows = [
        _row(1, scope="user", owner_ref="alice", created_at=NOW),
        _row(2, scope="org", owner_ref="org-A", created_at=NOW - timedelta(hours=5)),
        _row(3, scope="org", owner_ref="org-A", created_at=NOW - timedelta(hours=1)),
        _row(4, scope="user", owner_ref="alice", created_at=NOW + timedelta(hours=1)),
    ]
    assert [r["id"] for r in order_candidates(rows)] == [3, 2, 4, 1]


def test_same_timestamp_breaks_ties_by_descending_id() -> None:
    rows = [_row(1, created_at=NOW), _row(9, created_at=NOW), _row(5, created_at=NOW)]
    assert [r["id"] for r in order_candidates(rows)] == [9, 5, 1]


def test_order_is_stable_across_shuffles() -> None:
    """A7: N runs must be byte-identical — order may not depend on input order."""
    rows = [
        _row(1, scope="org", owner_ref="org-A", created_at=NOW),
        _row(2, scope="user", owner_ref="alice", created_at=NOW),
        _row(3, scope="org", owner_ref="org-A", created_at=NOW - timedelta(days=1)),
        _row(4, scope="user", owner_ref="alice", created_at=NOW),
    ]
    expected = [r["id"] for r in order_candidates(rows)]
    for rotation in range(len(rows)):
        rotated = rows[rotation:] + rows[:rotation]
        assert [r["id"] for r in order_candidates(rotated)] == expected


def test_budget_truncates_and_counts_dropped() -> None:
    rows = [_row(i, created_at=NOW - timedelta(minutes=i)) for i in range(1, 15)]
    kept, dropped = order_and_truncate(rows, limit=MEMORY_LIMIT)
    assert len(kept) == MEMORY_LIMIT == 10
    assert dropped == 4
    # and the kept ones are the 10 newest
    assert [r["id"] for r in kept] == list(range(1, 11))


def test_budget_does_not_report_a_shortfall_when_under_limit() -> None:
    kept, dropped = order_and_truncate([_row(1), _row(2)], limit=MEMORY_LIMIT)
    assert len(kept) == 2
    assert dropped == 0


# ═══════════════════════════════════════════════════════════════════════════
# per-row authorization (the read step's gate)
# ═══════════════════════════════════════════════════════════════════════════


def test_authorize_keeps_only_rows_with_an_explicit_allow() -> None:
    rows = [_row(1, scope="user", owner_ref="alice"), _row(2, scope="user", owner_ref="alice")]
    acl = {"memory:1": [_memory_acl("user", "alice")]}
    kept = authorize(rows, _ident(user_ref="alice"), acl, now=NOW)
    assert [r["id"] for r in kept] == [1]
    assert kept[0]["_matched_rule"] == "allow-user"


def test_a_memory_with_no_acl_row_is_invisible_even_to_its_owner() -> None:
    """THE fail-closed property. Merely existing is not visibility.

    A row whose `owner_ref` is the caller still needs an explicit ACL allow —
    `classification='restricted'` is default-deny. If this ever returns the row,
    the whole "writes go through the permission engine" claim is void.
    """
    rows = [_row(1, scope="user", owner_ref="alice")]
    assert authorize(rows, _ident(user_ref="alice"), {}, now=NOW) == []


def test_org_memory_is_visible_to_the_org_and_only_the_org() -> None:
    rows = [_row(7, scope="org", owner_ref="org-A")]
    acl = {"memory:7": [_memory_acl("org", "org-A")]}
    assert len(authorize(rows, _ident(user_ref="a", org_id="org-A"), acl, now=NOW)) == 1
    assert authorize(rows, _ident(user_ref="b", org_id="org-B"), acl, now=NOW) == []
    assert authorize(rows, _ident(user_ref="c", org_id=None), acl, now=NOW) == []


def test_authorize_honours_the_acl_time_box() -> None:
    """A time-boxed grant on a memory expires (OEI-009 semantics, not re-implemented)."""
    rows = [_row(1, scope="user", owner_ref="alice")]
    expired = [{
        "subject_type": "user",
        "subject_ref": "alice",
        "effect": "allow",
        "valid_from": None,
        "valid_to": NOW.date() - timedelta(days=1),
        "source_system": "memory:create",
    }]
    assert authorize(rows, _ident(user_ref="alice"), {"memory:1": expired}, now=NOW) == []


# ═══════════════════════════════════════════════════════════════════════════
# A10 — injected shape, audit shape, package compatibility
# ═══════════════════════════════════════════════════════════════════════════


def test_injected_shape_is_exactly_the_contract() -> None:
    """TASK §3.5 fixes these 7 keys — an extra one is a contract change."""
    item = to_item(_row(42, scope="org", owner_ref="org-A"))
    assert set(item) == {
        "ref",
        "scope",
        "statement",
        "source",
        "confidence",
        "created_at",
        "expires_at",
    }
    # `owner_ref` and `classification` are deliberately absent.
    assert item["ref"] == "memory:42"
    assert item["created_at"] == NOW.isoformat()


def test_confidence_is_a_float_not_a_decimal() -> None:
    """`numeric(3,2)` arrives as `Decimal`; the package must stay JSON-safe."""
    from decimal import Decimal

    row = _row(1)
    row["confidence"] = Decimal("0.75")
    item = to_item(row)
    assert isinstance(item["confidence"], float)
    assert item["confidence"] == 0.75
    assert to_item(_row(2))["confidence"] is None


def test_audit_items_never_contain_the_statement() -> None:
    """Traceability records THAT a memory was injected, never its content."""
    rows = [_row(1, statement="SECRET-ORG-STANCE")]
    rows[0]["_matched_rule"] = "allow-user"
    entries = audit_items(rows)
    assert len(entries) == 1
    assert entries[0]["kind"] == "memory"
    assert entries[0]["decision"] == "allowed"
    assert entries[0]["ref"] == "memory:1"
    assert entries[0]["reason"] == "acl:allow-user"
    assert entries[0]["source"] == {"system": AUDIT_SYSTEM, "record_id": "memory:1"}
    assert "SECRET-ORG-STANCE" not in repr(entries)


def test_context_package_keys_are_backward_compatible() -> None:
    """A10: the 11 original keys keep their names AND order; `memory` is appended."""
    keys = list(ContextPackage(
        package_id="p", request_id="r", task={}, user={}
    ).to_dict().keys())
    assert keys == [
        "package_id",
        "request_id",
        "task",
        "user",
        "entities",
        "relationships",
        "documents",
        "business_data",
        "denied",
        "sources",
        "metadata",
        "memory",
    ]


def test_context_package_is_constructible_without_memory() -> None:
    """`memory` must be optional — existing hand-built packages keep working."""
    pkg = ContextPackage(
        package_id="p", request_id="r", task={}, user={}, metadata={"counts": {}}
    )
    assert pkg.memory == []
    assert pkg.to_dict()["memory"] == []
