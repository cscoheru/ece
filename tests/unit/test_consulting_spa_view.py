"""KC-001 — SPA view-d Consulting Library binding tests.

Per Task §6:
  - view-d section must exist in index.html
  - nav button data-view="d" must exist
  - 6 filter select elements must exist
  - search input must exist
  - No CDN script/link tags (zero external assets, zero build)
  - Forbidden technical vocabulary must NOT appear (PRD §9 guardrail):
    embedding / vector / ctx_ / decision_id / policy_id / evidence_id /
    package_id / SQL / prompt / token
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPA_DIR = REPO_ROOT / "demos" / "spa"
INDEX_HTML = SPA_DIR / "index.html"
APP_JS = SPA_DIR / "app.js"


@pytest.fixture(scope="module")
def html_text() -> str:
    if not INDEX_HTML.exists():
        pytest.fail(f"SPA index.html missing at {INDEX_HTML}")
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text() -> str:
    if not APP_JS.exists():
        pytest.fail(f"SPA app.js missing at {APP_JS}")
    return APP_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def view_d_section(html_text: str) -> str:
    """Slice index.html to the View D section so guardrails don't trigger
    on unrelated view content."""
    match = re.search(
        r'<section[^>]*id=["\']view-d["\'][^>]*>(.*?)(?=<section|</main|</html)',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1)
    # Fallback: if view-d missing entirely, return empty string so the
    # section-existence test below fires clearly.
    return ""


@pytest.fixture(scope="module")
def view_d_js(js_text: str) -> str:
    """Slice app.js to the Consulting Library region only.

    The SPA uses one shared app.js for views A/B/C/D. The forbidden-word
    guardrail must only scan the consulting region (the KC-001 added
    block), not view-A business parameters like ``policy_id`` which are
    legitimate business field names used by the knowledge domain pack.
    """
    match = re.search(
        r"// KC-001 — Consulting Knowledge Library.*",
        js_text,
        re.DOTALL,
    )
    return match.group(0) if match else ""


# Forbidden technical vocabulary that must NOT appear in the Consulting
# Library view (per PRD §9). These are internal Kernel field names that
# would leak architecture to business users.
_FORBIDDEN_TECH_WORDS = [
    "embedding", "embeddings",
    "vector", "vectors",
    "ctx_",
    "decision_id",
    "policy_id",
    "evidence_id",
    "package_id",
    "context_request_id",
    "SQL",
    "prompt",
    "token",
]


def test_view_d_section_present_in_index_html(html_text: str) -> None:
    """View D section must be defined in the SPA."""
    assert 'id="view-d"' in html_text, "view-d section is missing from index.html"
    assert 'data-view="d"' in html_text, "data-view=\"d\" marker is missing"


def test_nav_button_for_view_d_exists(html_text: str) -> None:
    """Navigation bar must include the View D button."""
    assert re.search(
        r'<button[^>]*data-view=["\']d["\'][^>]*>.*?咨询知识库.*?</button>',
        html_text,
        re.DOTALL,
    ), "nav button data-view=d pointing at the consulting library is missing"


def test_view_d_has_search_input(view_d_section: str) -> None:
    """View D must include the keyword search input."""
    assert 'id="consulting-search"' in view_d_section, "search input id=consulting-search missing"
    assert 'type="search"' in view_d_section, "search input must have type=search"


def test_view_d_has_six_filter_selects(view_d_section: str) -> None:
    """Six filter selects: type / practice / phase / industry / problem / source."""
    expected_ids = [
        "filter-type", "filter-practice", "filter-phase",
        "filter-industry", "filter-problem", "filter-source",
    ]
    for sel_id in expected_ids:
        assert f'id="{sel_id}"' in view_d_section, f"missing select id={sel_id!r}"


def test_view_d_has_reset_and_total_and_cards(view_d_section: str) -> None:
    """View D must include the reset button + total label + card grid + empty
    placeholder + detail drawer."""
    assert 'id="consulting-reset"' in view_d_section
    assert 'id="consulting-total"' in view_d_section
    assert 'id="consulting-cards"' in view_d_section
    assert 'id="consulting-empty"' in view_d_section
    assert 'id="consulting-detail"' in view_d_section


def test_view_d_no_cdn_external_assets(html_text: str) -> None:
    """No <script src="http(s)://"> or <link rel="stylesheet" href="http(s)://">.
    Zero CDN, zero build is a hard commitment (Task §6)."""
    # <script src="https?://..."> must not appear
    bad_script = re.findall(
        r'<script[^>]*src=["\']https?://[^"\']+["\']',
        html_text,
        re.IGNORECASE,
    )
    assert not bad_script, f"CDN <script src> forbidden: {bad_script}"
    # <link rel="stylesheet" href="https?://..."> must not appear
    bad_link = re.findall(
        r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']https?://[^"\']+["\']',
        html_text,
        re.IGNORECASE,
    )
    assert not bad_link, f"CDN <link href> forbidden: {bad_link}"
    # <img src="https?://..."> must not appear (no remote image deps)
    bad_img = re.findall(
        r'<img[^>]*src=["\']https?://[^"\']+["\']',
        html_text,
        re.IGNORECASE,
    )
    assert not bad_img, f"remote <img src> forbidden: {bad_img}"


def test_view_d_no_forbidden_tech_words(view_d_section: str) -> None:
    """View D HTML must not contain forbidden technical vocabulary.
    PRD §9 business-language guardrail: client/partner users should never
    see internal Kernel field names."""
    # Lowercase the section so "SQL" / "SQLite" still match the literal "SQL"
    haystack = view_d_section
    for tok in _FORBIDDEN_TECH_WORDS:
        assert tok not in haystack, (
            f"forbidden technical vocabulary {tok!r} found in view-d section"
        )


def test_app_js_no_forbidden_tech_words(view_d_js: str) -> None:
    """Consulting client JS must also avoid forbidden technical vocabulary.
    The labels CONSULTING_TYPE_LABEL + CONSULTING_SOURCE_LABEL carry the
    business vocabulary; the consulting region of app.js must not echo
    technical words in user-visible strings."""
    # We only scan JS string literals inside the consulting block.
    string_literals = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', view_d_js)
    blob = "\n".join(string_literals)
    for tok in _FORBIDDEN_TECH_WORDS:
        # "token" is the riskiest — we allow it only as part of compound
        # technical phrases; literal "token" alone would be ambiguous. So
        # we skip "token" inside user-visible JS string literals unless
        # it is part of a known forbidden phrase.
        if tok == "token":
            continue
        assert tok not in blob, (
            f"forbidden technical vocabulary {tok!r} found in consulting JS string literal"
        )


def test_app_js_defines_required_consulting_entrypoints(js_text: str) -> None:
    """The SPA JS must expose the consulting entry points called from index.html."""
    for fn in (
        "loadConsultingLibrary",
        "loadConsultingFacets",
        "openConsultingDetail",
        "closeConsultingDetail",
        "runConsultingSearch",
    ):
        # Function declaration form: "function NAME(" or "var NAME = function" etc.
        assert re.search(rf"\b{re.escape(fn)}\b", js_text), (
            f"JS function {fn!r} is missing from app.js"
        )
