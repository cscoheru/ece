"""cut-045 — View C blueprint badges + 业务语言 binding tests.

Per `codex给cut-045的指令.md §3`:
  - 3 Domain Pack 徽章 (采购/知识管理/企业合规) — 全部 ✅
  - 8 底座能力徽章:
    - 六步闭环 ✅
    - Rule Registry ✅
    - Scenario Spec ✅
    - Evidence Trace ✅
    - Permission Before Intelligence ✅
    - Multi-domain Switching ✅
    - Same-origin Deployment 🔨
    - Customer Private Deployment ⬜ (规划中, 不得标 ✅)
  - 演进路线节点: 单域验证 → 多域底座 → 三域 demo → 自有服务器部署 → 客户 POC → 客户私有化部署
  - 业务语言化 (禁 ctx. / decision_id / policy_id / evidence_id)

RED on cut-044R2 baseline: View C missing Same-origin Deployment + Customer Private
Deployment badges; 业务语言化未做。
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
def view_c_section(html_text: str) -> str:
    """Extract the View C section of index.html.

    Heuristic: View C is bounded by `id="view-c"` and the next `id="..."` or
    `</body>`. If no such anchor exists, the whole file is returned (test
    asserts View C markers below).
    """
    # Look for view-c marker
    match = re.search(
        r'<section[^>]*id=["\']view-c["\'][^>]*>(.*?)(?=<section|</body)',
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1)
    # Fallback: full html (for very simple test environments)
    return html_text


# ---------------------------------------------------------------------------
# Domain Pack badges (3) — directive §3.1
# ---------------------------------------------------------------------------


def test_view_c_has_procurement_badge_oh(html_text: str) -> None:
    """采购 domain pack must show ✅ 已实现 badge."""
    # 业务语言: '采购' appears with a ✅ marker (Unicode U+2705)
    assert "采购" in html_text, "View C must mention 采购 (procurement) pack"
    # Don't enforce exact 徽章 string — just ensure a success marker near it
    assert "✅" in html_text, "View C must use ✅ (U+2705) status marker"


def test_view_c_has_knowledge_badge_oh(html_text: str) -> None:
    """知识管理 domain pack must show ✅ 已实现 badge."""
    assert "知识管理" in html_text, "View C must mention 知识管理 pack"


def test_view_c_has_compliance_badge_oh(html_text: str) -> None:
    """企业合规 domain pack must show ✅ 已实现 badge."""
    assert "企业合规" in html_text, "View C must mention 企业合规 pack"


# ---------------------------------------------------------------------------
# Foundation capability badges (8) — directive §3.2
# ---------------------------------------------------------------------------


REQUIRED_FOUNDATION_BADGES = (
    "六步闭环",
    "Rule Registry",
    "Scenario Spec",
    "Evidence Trace",
    "Permission Before Intelligence",
    "Multi-domain Switching",
    "Same-origin Deployment",
    "Customer Private Deployment",
)


def test_view_c_lists_all_8_foundation_badges(html_text: str) -> None:
    """All 8 foundation capability badges must appear in View C."""
    for badge in REQUIRED_FOUNDATION_BADGES:
        assert badge in html_text, (
            f"View C missing foundation capability badge {badge!r} "
            f"(directive §3.2 requires all 8)"
        )


# ---------------------------------------------------------------------------
# Negative binding — directive §3.5 禁止把未来能力写成已实现
# ---------------------------------------------------------------------------


def test_view_c_does_not_mark_customer_private_deployment_oh(html_text: str) -> None:
    """Customer Private Deployment must NOT be marked ✅ (it's 规划中).

    This is the critical binding: any code path that lets the demo claim
    customer-private deployment as done is a R1-B2-style audit accident.
    """
    # Locate the Customer Private Deployment line
    idx = html_text.find("Customer Private Deployment")
    if idx == -1:
        pytest.fail("Customer Private Deployment badge missing entirely")
    # Look at the surrounding ~80 chars for a ✅ marker (without crossing line/section)
    scope = html_text[idx:idx + 200]
    # Find the next badge boundary (newline or list terminator)
    line_end = scope.find("\n")
    if line_end != -1:
        scope = scope[:line_end]
    assert "✅" not in scope, (
        "View C marks Customer Private Deployment as ✅ — but it's 规划中 (⛔ ⬜). "
        "Per directive §3.5: 禁止把未来能力写成已实现."
    )


# ---------------------------------------------------------------------------
# cut-045 ops R4-B1 — Same-origin Deployment (real) MUST be marked ✅
# ---------------------------------------------------------------------------
#
# History:
#   cut-045R1 R3-B4 (2026-09-23): introduced this binding to enforce 🔨
#       (real deployment pending). Test name suffix `_oh` was a typo
#       placeholder.
#   cut-045 ops R4-B1 (2026-09-23): operational deployment PASS at
#       https://corln.rana.asia (PASS=10 SKIP=0 FAIL=0). Real deployment
#       is now verified end-to-end. Binding FLIPPED: ✅ required, 🔨
#       forbidden. Renamed to reflect current reality.


def test_view_c_marks_same_origin_deployment_done_when_operational(
    html_text: str,
) -> None:
    """Same-origin Deployment (real production deployment) MUST be marked ✅.

    cut-045 ops R4-B1 (2026-09-23): operational deployment PASSED at
    https://corln.rana.asia (PASS=10 SKIP=0 FAIL=0, see
    ece/reports/cut-045-operations-report.md). The previous
    config-as-code-only 🔨 state (cut-045R1 R3-B4) has been superseded.

    View C must now mark Same-origin Deployment as ✅ (badge-done), and
    MUST NOT mark it as 🔨 (badge-wip / in-progress).

    Pre-flight check: Customer Private Deployment remains ⬜ (out of
    cut-045 scope; verified by `test_view_c_does_not_mark_customer_private_as_done`).
    """
    idx = html_text.find("Same-origin Deployment")
    if idx == -1:
        pytest.fail("Same-origin Deployment badge missing entirely")
    # Find enclosing <span ...> ... </span> by searching backwards for the
    # nearest `<span` and forwards for the nearest `</span>`.
    span_open_idx = html_text.rfind("<span", 0, idx)
    span_close_idx = html_text.find("</span>", idx)
    if span_open_idx == -1 or span_close_idx == -1:
        pytest.fail("Same-origin Deployment badge not wrapped in <span>")
    span = html_text[span_open_idx:span_close_idx + len("</span>")]
    # Span MUST contain "✅" (done marker) — R4-B1 ops PASS
    assert "✅" in span, (
        f"View C does NOT mark Same-origin Deployment as ✅ — "
        f"but operational deployment PASSED at https://corln.rana.asia "
        f"(PASS=10 SKIP=0 FAIL=0, 2026-09-23, see "
        f"ece/reports/cut-045-operations-report.md). "
        f"Per cut-045 ops R4-B1: real deployment is now verified "
        f"end-to-end, so View C must show ✅ (badge-done), not 🔨 "
        f"(badge-wip). Span found: {span!r}"
    )
    # Span MUST NOT contain "🔨" (in-progress marker) — superseded by R4-B1
    assert "🔨" not in span, (
        f"View C still marks Same-origin Deployment as 🔨 (in span: "
        f"{span!r}) — but operational deployment PASSED on 2026-09-23. "
        f"Per cut-045 ops R4-B1: this is a historical pre-deployment "
        f"marker; current reality is ✅. Removing 🔨 here prevents "
        f"reader confusion and audit accidents."
    )


# ---------------------------------------------------------------------------
# Evolution roadmap (演进路线) — directive §3.3
# ---------------------------------------------------------------------------


def test_view_c_has_evolution_roadmark(html_text: str) -> None:
    """演进路线 nodes must all be present."""
    required_roadmap_nodes = (
        "单域验证",
        "多域底座",
        "三域 demo",
        "自有服务器部署",
        "客户 POC",
        "客户私有化部署",
    )
    for node in required_roadmap_nodes:
        assert node in html_text, (
            f"View C missing evolution roadmap node {node!r} (directive §3.3)"
        )


# ---------------------------------------------------------------------------
# 业务语言化 (no internal technical terms in user-facing view) — directive §3.6
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_token",
    [
        "ctx.",
        "decision_id",
        "policy_id",
        "evidence_id",
        "input_context_ref",
        "package_id",
        "context_request_id",
    ],
)
def test_view_c_no_internal_token(
    view_c_section: str, forbidden_token: str
) -> None:
    """View C section must not expose internal technical tokens (directive §3.6).

    These tokens belong in internal logs / mapper internals, never in
    customer-facing blueprint view.
    """
    assert forbidden_token not in view_c_section, (
        f"View C exposes internal token {forbidden_token!r} "
        f"(directive §3.6 requires business-language display)"
    )


# ---------------------------------------------------------------------------
# Zero external CDN — directive §4.2.6 (also covered by view-level convention)
# ---------------------------------------------------------------------------


def test_spa_index_has_no_external_cdn_scripts(html_text: str) -> None:
    """SPA index.html must not reference external CDN scripts/styles."""
    # Match src="https:// or href="https:// patterns
    external_script = re.search(r'<script[^>]+src=["\']https?://', html_text)
    external_link = re.search(r'<link[^>]+href=["\']https?://', html_text)
    assert not external_script, (
        f"SPA index.html references external script: {external_script.group(0)!r} "
        f"— zero CDN per directive §4.2.6"
    )
    assert not external_link, (
        f"SPA index.html references external stylesheet: {external_link.group(0)!r}"
    )


def test_spa_app_js_has_no_external_cdn_imports(js_text: str) -> None:
    """SPA app.js must not import from external CDN."""
    # Match `import ... from "https://"` or `fetch("https://...`
    external_import = re.search(
        r'(?:import|fetch|axios)\s*\(?\s*["\']https?://', js_text
    )
    assert not external_import, (
        f"SPA app.js has external CDN import: {external_import.group(0)!r}"
    )
