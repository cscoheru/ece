"""OEI-009 — DB-free unit tests for `permissions/engine.py:check_permission`.

Focus: the ACL `valid_from` / `valid_to` time-box semantics added in OEI-009.

  - `valid_from IS NULL → -∞`      (always active from the past)
  - `valid_to   IS NULL → +∞`      (always active into the future)
  - `valid_from <= now < valid_to`  (half-open interval)
  - boundary cases: `valid_to == today` → INACTIVE;
                    `valid_from == today` → ACTIVE
  - "未生效" (not yet effective) — valid_from in the future → INACTIVE
  - "已过期" (expired) — valid_to in the past → INACTIVE

Test strategy: build a minimal `Identity` (stub dataclass), feed it the
pre-existing acl_entries row shape (the same shape `api/identity.py` and
`consulting/permissions_filter.py` load), drive `now` deterministically.

Constraints (per TASK §7 / OEI-008 VERDICT §5):
  - do NOT modify the 判定顺序 (deny > user > role > dept > classification > default deny)
  - do NOT modify the existing classification matrix
  - we ARE allowed to pass a new `now=` kwarg (it's a parameterisation, not
    a reordering)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from ece.permissions.engine import check_permission


# Minimal Identity stub matching the real dataclass shape; using a real
# `Identity` would pull in SQLAlchemy + DB tables for no test benefit.
@dataclass
class _IdentityStub:
    user_ref: str
    entity_id: str | None = None
    display_id: str | None = None
    name: str = ""
    department: str = ""
    roles: list[str] = None  # type: ignore[assignment]
    aliases: list[str] = None  # type: ignore[assignment]
    source_system: str = "test"
    is_management: bool = False
    org_id: str | None = None

    def __post_init__(self) -> None:
        self.roles = self.roles or []
        self.aliases = self.aliases or []


def _allow_acl(*, valid_from=None, valid_to=None) -> dict:
    return {
        "subject_type": "user",
        "subject_ref": "alice",
        "effect": "allow",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_system": "test",
    }


def _today() -> date:
    return date(2026, 9, 25)


# ---------------------------------------------------------------------------
# valid_from NULL  (-∞)  +  valid_to NULL  (+∞)  → always active
# ---------------------------------------------------------------------------


def test_no_window_allow_active() -> None:
    acl = [_allow_acl()]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=date(2020, 1, 1),
    )
    assert dec.allowed is True
    assert dec.matched_rule == "allow-user"


# ---------------------------------------------------------------------------
# valid_to = today  → INACTIVE (boundary exclusive on the right)
# ---------------------------------------------------------------------------


def test_valid_to_today_is_inactive() -> None:
    """A8 verbatim: 'valid_to = 今天 → 无效'."""
    acl = [_allow_acl(valid_to=_today())]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=_today(),
    )
    # Allow expired; fall through to classification=restricted → default deny
    assert dec.allowed is False
    assert dec.matched_rule == "default-deny"


# ---------------------------------------------------------------------------
# valid_to = tomorrow  → ACTIVE
# ---------------------------------------------------------------------------


def test_valid_to_tomorrow_is_active() -> None:
    """A8 verbatim: 'valid_to = 明天 → 有效'."""
    acl = [_allow_acl(valid_to=date(2026, 9, 26))]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=_today(),
    )
    assert dec.allowed is True
    assert dec.matched_rule == "allow-user"


# ---------------------------------------------------------------------------
# valid_from = tomorrow  → INACTIVE (not yet effective)
# ---------------------------------------------------------------------------


def test_valid_from_tomorrow_is_inactive() -> None:
    """A8 verbatim: 'valid_from = 明天 → 无效（未生效）'."""
    acl = [_allow_acl(valid_from=date(2026, 9, 26))]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=_today(),
    )
    assert dec.allowed is False
    assert dec.matched_rule == "default-deny"


# ---------------------------------------------------------------------------
# valid_from = today  → ACTIVE (boundary inclusive on the left)
# ---------------------------------------------------------------------------


def test_valid_from_today_is_active() -> None:
    acl = [_allow_acl(valid_from=_today(), valid_to=date(2026, 9, 26))]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=_today(),
    )
    assert dec.allowed is True
    assert dec.matched_rule == "allow-user"


# ---------------------------------------------------------------------------
# datetime input — tz-aware conversion to UTC date
# ---------------------------------------------------------------------------


def test_datetime_input_uses_utc_date() -> None:
    """A tz-aware `datetime` is converted to its UTC date before comparison."""
    # Same UTC instant; one before midnight (active) and one after (inactive).
    acl = [_allow_acl(valid_to=date(2026, 9, 26))]

    dec_pre = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=datetime(2026, 9, 25, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert dec_pre.allowed is True

    dec_post = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=datetime(2026, 9, 26, 0, 0, 1, tzinfo=timezone.utc),
    )
    assert dec_post.allowed is False


# ---------------------------------------------------------------------------
# Deny with time-box — deny still beats allow when active
# ---------------------------------------------------------------------------


def test_deny_in_window_blocks_even_when_allow_in_window() -> None:
    """Both in window: deny wins (判定順序 frozen)."""
    acl = [
        _allow_acl(valid_from=date(2026, 1, 1), valid_to=date(2027, 1, 1)),
        {
            "subject_type": "user",
            "subject_ref": "alice",
            "effect": "deny",
            "valid_from": date(2026, 1, 1),
            "valid_to": date(2027, 1, 1),
            "source_system": "test",
        },
    ]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="public",
        acl_entries=acl,
        now=_today(),
    )
    assert dec.allowed is False
    assert dec.matched_rule == "deny"


def test_deny_expired_falls_through_to_allow() -> None:
    """Deny expired → falls through to the (in-window) allow."""
    acl = [
        _allow_acl(valid_from=date(2026, 1, 1), valid_to=date(2027, 1, 1)),
        {
            "subject_type": "user",
            "subject_ref": "alice",
            "effect": "deny",
            "valid_from": date(2025, 1, 1),
            "valid_to": date(2025, 12, 31),  # expired
            "source_system": "test",
        },
    ]
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=_today(),
    )
    assert dec.allowed is True
    assert dec.matched_rule == "allow-user"


# ---------------------------------------------------------------------------
# None / out-of-range `now` — defensive defaults
# ---------------------------------------------------------------------------


def test_now_none_defaults_to_utc_today() -> None:
    """`now=None` (the production path) must not crash; it falls back to UTC today."""
    acl = [_allow_acl()]  # no time-box → always active
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=acl,
        now=None,
    )
    assert dec.allowed is True


# ---------------------------------------------------------------------------
# Empty ACL — classification matrix still applies (frozen since cut-040R)
# ---------------------------------------------------------------------------


def test_empty_acl_public_allows() -> None:
    """Public classification → allowed for any caller (incl. anonymous)."""
    dec = check_permission(
        _IdentityStub(user_ref=""),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="public",
        acl_entries=[],
        now=_today(),
    )
    assert dec.allowed is True


def test_empty_acl_restricted_denies() -> None:
    """Restricted + no ACL → default deny (cut-040R-2 R40R2.5 invariant)."""
    dec = check_permission(
        _IdentityStub(user_ref="alice"),
        object_type="engine_document",
        object_ref="engine_document:1",
        classification="restricted",
        acl_entries=[],
        now=_today(),
    )
    assert dec.allowed is False
    assert dec.matched_rule == "default-deny"