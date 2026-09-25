"""OEI-010 A2 — `subject_type='org'` in `_subject_matches`.

DB-free. The org dimension is what makes an org-scoped memory visible to
exactly "everyone in the same org"; before this cut an `org` ACL row could
never fire (`_subject_matches` stopped at `department`), so a row written with
`subject_type='org'` was silently dead.

What these tests pin:

1. the four org states (same org / other org / no org / empty-string org),
2. that an org row is subject to the OEI-009 time-box like any other row,
3. that the four PRE-EXISTING subject kinds behave exactly as before — this is
   the regression guard for "adding a subject kind must not perturb the others".
"""
from __future__ import annotations

from datetime import date

from ece.identity.parser import Identity
from ece.permissions.engine import check_permission

# `restricted` maps to default-deny in DEFAULT_CLASSIFICATION_MATRIX, so a
# non-matching subject produces `default-deny` rather than an accidental allow.
# Using it here means a passing test can only come from the org rule firing.
CLASSIFICATION = "restricted"


def _ident(**kwargs) -> Identity:
    return Identity(
        user_ref=kwargs.pop("user_ref", "someone"),
        department=kwargs.pop("department", ""),
        roles=kwargs.pop("roles", []),
        is_management=kwargs.pop("is_management", False),
        org_id=kwargs.pop("org_id", None),
    )


def _acl(
    subject_type: str,
    subject_ref: str,
    effect: str = "allow",
    valid_from: date | None = None,
    valid_to: date | None = None,
) -> dict:
    return {
        "subject_type": subject_type,
        "subject_ref": subject_ref,
        "effect": effect,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_system": "test",
    }


def _check(identity: Identity, acl: list[dict], **kwargs):
    return check_permission(
        identity=identity,
        object_type="memory",
        object_ref="memory:1",
        classification=CLASSIFICATION,
        acl_entries=acl,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. The four org states
# ---------------------------------------------------------------------------


def test_same_org_matches() -> None:
    """Caller in org-A + allow row for org-A -> allowed by the org rule."""
    decision = _check(_ident(org_id="org-A"), [_acl("org", "org-A")])
    assert decision.allowed is True
    assert decision.matched_rule == "allow-org"


def test_other_org_does_not_match() -> None:
    """Caller in org-B must not be reached by an org-A row."""
    decision = _check(_ident(org_id="org-B"), [_acl("org", "org-A")])
    assert decision.allowed is False
    assert decision.matched_rule == "default-deny"


def test_no_org_claim_does_not_match() -> None:
    """`org_id=None` -> "no org claim" -> an org row must never fire."""
    decision = _check(_ident(org_id=None), [_acl("org", "org-A")])
    assert decision.allowed is False
    assert decision.matched_rule == "default-deny"


def test_empty_string_org_does_not_match() -> None:
    """`org_id=""` is the same as no claim — not a wildcard.

    This is the state that would be catastrophic to get wrong: `""` matching an
    org row would hand every org-less caller every org's memory.
    """
    decision = _check(_ident(org_id=""), [_acl("org", "org-A")])
    assert decision.allowed is False
    assert decision.matched_rule == "default-deny"


def test_empty_org_row_never_matches_an_orgless_caller() -> None:
    """Even a malformed row with `subject_ref=""` cannot match `org_id=""`.

    `_subject_matches` bails on an empty `subject_ref` before any comparison,
    so the pair ("", "") is not a match.
    """
    decision = _check(_ident(org_id=""), [_acl("org", "")])
    assert decision.allowed is False


# ---------------------------------------------------------------------------
# 2. Org rows obey the deny rule and the time-box
# ---------------------------------------------------------------------------


def test_org_deny_row_fires_for_same_org() -> None:
    """The deny pass calls the same matcher — an org deny must beat an allow."""
    decision = _check(
        _ident(org_id="org-A"),
        [_acl("org", "org-A", effect="deny"), _acl("org", "org-A", effect="allow")],
    )
    assert decision.allowed is False
    assert decision.matched_rule == "deny"


def test_org_row_outside_time_window_does_not_match() -> None:
    """OEI-009 time-box applies to org rows: an expired grant grants nothing.

    `valid_to` is exclusive (half-open `[valid_from, valid_to)`), so a row that
    closed yesterday is inactive at `now`.
    """
    acl = [_acl("org", "org-A", valid_from=date(2026, 1, 1), valid_to=date(2026, 1, 2))]
    decision = _check(_ident(org_id="org-A"), acl, now=date(2026, 6, 1))
    assert decision.allowed is False
    assert decision.matched_rule == "default-deny"


def test_org_row_inside_time_window_matches() -> None:
    acl = [_acl("org", "org-A", valid_from=date(2026, 1, 1), valid_to=date(2026, 6, 2))]
    decision = _check(_ident(org_id="org-A"), acl, now=date(2026, 6, 1))
    assert decision.allowed is True
    assert decision.matched_rule == "allow-org"


# ---------------------------------------------------------------------------
# 3. Regression: the pre-existing subject kinds are untouched
# ---------------------------------------------------------------------------


def test_user_role_department_still_match() -> None:
    """The three original subject kinds keep working, next to the new one.

    If adding the org branch had changed the matcher's control flow, one of
    these three would stop firing.
    """
    identity = _ident(user_ref="alice", department="procurement", roles=["buyer"])

    assert _check(identity, [_acl("user", "alice")]).matched_rule == "allow-user"
    assert _check(identity, [_acl("role", "buyer")]).matched_rule == "allow-role"
    assert (
        _check(identity, [_acl("department", "procurement")]).matched_rule
        == "allow-department"
    )


def test_non_matching_subject_kinds_still_deny() -> None:
    identity = _ident(user_ref="alice", department="procurement", roles=["buyer"])
    for subject_type, subject_ref in (
        ("user", "bob"),
        ("role", "cfo"),
        ("department", "finance"),
        ("org", "org-A"),
    ):
        decision = _check(identity, [_acl(subject_type, subject_ref)])
        assert decision.allowed is False, (subject_type, subject_ref)
        assert decision.matched_rule == "default-deny"


def test_classification_matrix_still_runs_when_no_acl_matches() -> None:
    """The tail of the engine is unchanged: no org row -> matrix decides."""
    decision = check_permission(
        identity=_ident(org_id="org-A"),
        object_type="entity",
        object_ref="SUP001",
        classification="public",
        acl_entries=[],
    )
    assert decision.allowed is True
    assert decision.matched_rule == "classification-public"
