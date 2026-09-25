"""OEI-009 — DB-free unit tests for `consulting/registry.py`.

Covers:
  - `compute_controlled_filename` determinism (N=5)  → A1′
  - `slugify_for_filename` edge cases
  - `compute_controlled_filename` rejects missing extension
  - Empty / None user_ref is handled (substitutes "anon")

The DB-backed helpers (`lookup_by_engine_filename`, `register`,
`backfill_demo_files`) live in integration tests because they need a real
PG; here we cover only the pure-function layer that the route uses on
*every* upload.
"""
from __future__ import annotations

import pytest

from ece.consulting.registry import (
    compute_controlled_filename,
    slugify_for_filename,
)


# ---------------------------------------------------------------------------
# slugify_for_filename — pure edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("case-management-consulting", "case-management-consulting"),
        ("Case_Management Consulting!", "case-management-consulting"),
        ("中文方法论", "doc"),  # all non-[a-z0-9] -> "doc" fallback
        ("   ", "doc"),
        ("", "doc"),
        ("...$$$...", "doc"),
        ("a" * 200, "a" * 200),  # long but valid
    ],
)
def test_slugify_for_filename(raw: str, expected: str) -> None:
    assert slugify_for_filename(raw) == expected


def test_slugify_collapse_runs() -> None:
    """Multiple non-alphanumeric runs collapse into a single '-'."""
    assert slugify_for_filename("foo   bar---baz!!") == "foo-bar-baz"


# ---------------------------------------------------------------------------
# compute_controlled_filename — deterministic, N=5 same input → same output
# ---------------------------------------------------------------------------


def test_deterministic_n5() -> None:
    """A1′ acceptance: same input × N=5 calls → byte-identical output."""
    n = [compute_controlled_filename("fisher", "play-sales-delivery.md") for _ in range(5)]
    assert len(set(n)) == 1, f"non-deterministic: {n}"


def test_format_ece_docref_slug_ext() -> None:
    name = compute_controlled_filename("alice", "play-sales-delivery.md")
    assert name.startswith("ece-")
    parts = name.split(".")
    assert len(parts) == 2
    stem, ext = parts
    assert ext == "md"
    # stem = ece-<12 hex>-<slug>
    stem_parts = stem.split("-")
    # ['ece', '<docref 12 hex>', '<slug pieces>...']
    assert stem_parts[0] == "ece"
    assert len(stem_parts[1]) == 12
    int(stem_parts[1], 16)  # raises if not hex
    assert "-".join(stem_parts[2:]) == "play-sales-delivery"


def test_different_users_get_different_docref() -> None:
    """Same filename, different user → different docref."""
    a = compute_controlled_filename("alice", "report.md")
    b = compute_controlled_filename("bob", "report.md")
    # docref part differs (12 hex chars)
    a_docref = a.split("-")[1]
    b_docref = b.split("-")[1]
    assert a_docref != b_docref


def test_same_user_same_file_stable_across_calls() -> None:
    """Two completely separate calls → same output."""
    a = compute_controlled_filename("alice", "play-sales-delivery.md")
    b = compute_controlled_filename("alice", "play-sales-delivery.md")
    assert a == b


def test_extension_lowercased() -> None:
    """`.MD` and `.md` produce the same engine filename (extension lowercased)."""
    a = compute_controlled_filename("alice", "play-sales-delivery.MD")
    b = compute_controlled_filename("alice", "play-sales-delivery.md")
    assert a.endswith(".md")
    assert b.endswith(".md")
    # NOTE: full equality is NOT expected because `original_filename` is part
    # of the docref hash. The contract is "extension lowercased in the
    # returned filename", which is what A1′ cares about for engine-side
    # filename consistency.


def test_unknown_user_substituted_anon() -> None:
    """None user_ref → "anon" sentinel; still deterministic."""
    a = compute_controlled_filename(None, "play-sales-delivery.md")
    b = compute_controlled_filename(None, "play-sales-delivery.md")
    assert a == b
    assert a.startswith("ece-")


def test_empty_user_ref_substituted_anon() -> None:
    a = compute_controlled_filename("", "play-sales-delivery.md")
    b = compute_controlled_filename("", "play-sales-delivery.md")
    assert a == b


def test_missing_extension_rejected() -> None:
    with pytest.raises(ValueError, match="no extension"):
        compute_controlled_filename("alice", "play-sales-delivery")


def test_empty_filename_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        compute_controlled_filename("alice", "")


def test_unicode_filename_handled() -> None:
    """Chinese / non-ASCII characters in filename work; slug collapses them."""
    # 中文方法论 is not [a-z0-9] so it becomes "-" per slugify
    name = compute_controlled_filename("alice", "中文方法论.md")
    assert name.endswith(".md")
    assert name.startswith("ece-")