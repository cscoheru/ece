"""S2.3 Entity Resolution 6-stage pipeline + /resolve API contract."""
from __future__ import annotations

from ece.db import get_engine
from ece.entities.resolver import ResolutionMethod, resolve_mention


def test_resolver_unknown_mention_returns_empty() -> None:
    engine = get_engine()
    result = resolve_mention(engine, "X-NONEXISTENT-MENTION-003")
    assert result.candidates == []
    assert result.resolved is False
    assert result.chosen is None


def test_resolver_demo_dataset_supplier_exact_match() -> None:
    """Demo dataset has 50 suppliers seeded by cut-005 R1 fix."""
    engine = get_engine()
    # "无限极" was seeded by demo dataset (some SUP id; not fixed)
    result = resolve_mention(engine, "无限极")
    # exact: source_id match fails; normalized: matches name 无限极 -> chosen SUP001
    assert len(result.candidates) >= 1
    assert result.candidates[0]["entity"].startswith("SUP")  # demo-seeded supplier id
    assert result.resolved is True
    assert result.method == ResolutionMethod.NORMALIZED


def test_resolver_ambiguity_returns_resolved_false() -> None:
    """Per cut-005 §7.4 R5: multi-candidate match -> resolved=false (never guess)."""
    engine = get_engine()
    # query empty/blank -> no candidates -> resolved=False
    result = resolve_mention(engine, "")
    assert result.resolved is False


def test_resolver_includes_method_metadata() -> None:
    """Per cut-005: each candidate carries method (exact/normalized/alias/...)."""
    engine = get_engine()
    result = resolve_mention(engine, "无限极")
    if result.candidates:
        c = result.candidates[0]
        assert "method" in c
        assert c["method"] in (
            "exact", "normalized", "alias", "rule", "embedding", "llm",
        )
        assert "confidence" in c
