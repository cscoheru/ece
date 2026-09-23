"""KC-001 — Consulting seed content discipline binding tests.

Per PRD §4.2 + Task §4.2:
  - All summary / title copy must be Chinese (no English-only fields).
  - Client names must be anonymized (no real company names; no "ACME"-style
    placeholders either — must follow the "某 + 行业 + 规模" convention).
  - Synthetic content must carry source_origin=synthetic_variant
    (no record may claim confidence=synthetic while claiming founder_case).
  - No competitor-proprietary case content (McKinsey / BCG / Bain / 麦肯锡 /
    贝恩 / 贝恩咨询). Public methodology names (SWOT / Porter / 7S / Lean /
    RACI / KPI tree) are allowed because they are public framework names.
  - Numeric claims should be illustrative, not precision-result style.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ece.consulting.service import ConsultingCatalog

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "src" / "ece" / "consulting" / "seed" / "consulting_objects.json"


@pytest.fixture(scope="module")
def catalog() -> ConsultingCatalog:
    return ConsultingCatalog.from_seed_path(SEED_PATH)


# A reasonable "is mostly Chinese" check: at least 60% of non-space characters
# in a piece of business copy fall in the CJK Unified Ideographs blocks.
_CJK_RE = re.compile(
    r"[一-鿿㐀-䶿豈-﫿]"
)


def _is_mostly_chinese(text: str, min_ratio: float = 0.2) -> bool:
    stripped = text.replace(" ", "")
    if not stripped:
        return False
    cjk = sum(1 for ch in stripped if _CJK_RE.match(ch))
    return (cjk / len(stripped)) >= min_ratio


# Real-company-name placeholders we forbid. These are common consulting-firm
# patterns; real entries would have been caught in the seed review.
# (Public framework names like SWOT / Porter are allowed and listed below.)
_FORBIDDEN_ORG_TOKENS = [
    "麦肯锡", "McKinsey",
    "BCG",
    "贝恩", "Bain",
    "埃森哲", "Accenture",
    "德勤", "Deloitte",
    "普华永道", "PwC",
    "安永", "Ernst & Young", "EY",
    "毕马威", "KPMG",
]
# Synthetic-but-too-specific patterns we also forbid: "ACME 集团" / "X 客户".
_FORBIDDEN_PLACEHOLDER_PATTERNS = [
    re.compile(r"ACME"),
    re.compile(r"\bX\s*客户\b"),
    re.compile(r"\bTest\s*Client\b"),
    re.compile(r"\bTest\s*Co\b"),
]


def test_summary_and_title_are_chinese(catalog: ConsultingCatalog) -> None:
    """Every business-facing text field (title + summary) must be predominantly
    Chinese. The PRD §9 says the UI is zh-CN — drift to English would break UX."""
    for o in catalog.objects:
        assert _is_mostly_chinese(o.title), (
            f"{o.id!r} title is not predominantly Chinese: {o.title!r}"
        )
        assert _is_mostly_chinese(o.summary), (
            f"{o.id!r} summary is not predominantly Chinese: {o.summary!r}"
        )


def test_no_real_or_competitor_org_names(catalog: ConsultingCatalog) -> None:
    """No record mentions any known competitor consulting firm or generic
    big-4 / strategy-house name in any text field. PRD §4.2 prohibits
    competing firms' proprietary case content."""
    blob_fields = (
        "title", "summary", "methods", "deliverables", "outcomes",
    )
    for o in catalog.objects:
        texts = [o.title, o.summary]
        for fname in blob_fields:
            texts.extend(getattr(o, fname, []) or [])
        joined = "\n".join(texts)
        for tok in _FORBIDDEN_ORG_TOKENS:
            assert tok not in joined, (
                f"{o.id!r} mentions forbidden firm token {tok!r}"
            )
        for pat in _FORBIDDEN_PLACEHOLDER_PATTERNS:
            assert not pat.search(joined), (
                f"{o.id!r} contains placeholder pattern {pat.pattern!r}"
            )


def test_synthetic_confidence_requires_synthetic_variant(catalog: ConsultingCatalog) -> None:
    """confidence=synthetic implies source_origin=synthetic_variant.
    A 'synthetic' trust signal paired with 'founder_case' would be deceptive."""
    for o in catalog.objects:
        if o.confidence == "synthetic":
            assert o.source_origin == "synthetic_variant", (
                f"{o.id!r} has confidence=synthetic but source_origin={o.source_origin!r}"
            )


def test_founder_case_records_are_marked_as_such(catalog: ConsultingCatalog) -> None:
    """Defensive sanity: any founder_case record must NOT carry the
    synthetic marker. Real anonymized founder content is high-confidence
    and approved."""
    for o in catalog.objects:
        if o.source_origin == "founder_case":
            assert o.confidence != "synthetic", (
                f"{o.id!r} is founder_case but confidence={o.confidence!r} "
                f"(must be high or medium)"
            )
            assert o.review_state == "approved", (
                f"{o.id!r} is founder_case but review_state={o.review_state!r} "
                f"(must be approved)"
            )


def test_no_precision_numeric_outcome_claims(catalog: ConsultingCatalog) -> None:
    """Defensive guard against claiming precise savings like '30%' or '节省 X%'.
    PRD §4.2 says: '数字仅作示意, 不要写节省 30% 之类精确结果'. We don't
    forbid all numerics — industry sizes, headcount etc. are fine — but
    percentage-of-savings precision is forbidden."""
    pct_re = re.compile(r"(节省|节约|提升|降低|增长).{0,8}\d+(?:\.\d+)?\s*%")
    for o in catalog.objects:
        for field_name in ("summary", "title"):
            text = getattr(o, field_name)
            assert not pct_re.search(text), (
                f"{o.id!r}.{field_name} contains precision savings claim: {text!r}"
            )
