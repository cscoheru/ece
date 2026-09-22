"""cut-042R F6 — SPA 骨架 smoke 测试.

Codex HOLD 2026-09-22 finding F6: cut-042 要求的 SPA 骨架未交付, 唯一 HTML 是
demos/procurement-review-demo.html (静态页, 不调 API). cut-042R 必须交付:

  - 零 CDN (无 <script src="https://..."> 或 <link href="https://...">)
  - 零 build (vanilla JS, 无 webpack/vite/require())
  - 视图 A 真实调用 /api/v1/demo/* (GET domains + POST scenarios/generate)
  - 视图 B/C 至少有可切换占位 (cut-043 / cut-044 待交付)

本测试是 RED — demos/spa/ 目录尚未存在, 测试 FAIL (FileNotFoundError).
GREEN 修法见 commit C.
"""
from __future__ import annotations

import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SPA_ROOT = REPO_ROOT / "demos" / "spa"


def test_spa_directory_exists() -> None:
    """F6: demos/spa/ 目录必须存在 (骨架就位)."""
    assert SPA_ROOT.is_dir(), f"F6: SPA root {SPA_ROOT} does not exist; cut-042R must deliver demos/spa/"


def test_spa_index_html_exists_and_calls_demo_api() -> None:
    """F6: index.html 必须存在, 且引用 /api/v1/demo/* (live 视图 A)."""
    index_path = SPA_ROOT / "index.html"
    assert index_path.is_file(), f"F6: {index_path} missing"
    html = index_path.read_text(encoding="utf-8")

    # 必须引用 demo API
    assert "/api/v1/demo/domains" in html, \
        "F6: SPA must reference GET /api/v1/demo/domains (视图 A live 调 API)"
    assert "/api/v1/demo/scenarios/generate" in html, \
        "F6: SPA must reference POST /api/v1/demo/scenarios/generate"


def test_spa_has_three_views() -> None:
    """F6: SPA 必须有 3 个视图 — A live + B/C 占位."""
    index_path = SPA_ROOT / "index.html"
    assert index_path.is_file(), f"F6: {index_path} missing"
    html = index_path.read_text(encoding="utf-8")

    # 视图 A: 采购场景 live
    has_view_a = ("view-a" in html) or ("采购" in html) or ("procurement" in html)
    assert has_view_a, "F6: 视图 A (采购场景 live) must be present"

    # 视图 B: 知识管理占位 (cut-043 待交付)
    has_view_b = ("view-b" in html) or ("知识管理" in html) or ("knowledge" in html)
    assert has_view_b, "F6: 视图 B (知识管理占位) must be present"

    # 视图 C: 企业合规占位 (cut-044 待交付)
    has_view_c = ("view-c" in html) or ("企业合规" in html) or ("compliance" in html)
    assert has_view_c, "F6: 视图 C (企业合规占位) must be present"


def test_spa_has_zero_external_cdn() -> None:
    """F6: SPA 必须零 CDN — 无 https:// 资源加载."""
    for fname in ("index.html", "app.js", "styles.css"):
        fpath = SPA_ROOT / fname
        if not fpath.is_file():
            continue
        content = fpath.read_text(encoding="utf-8")
        for pattern in (
            '<script src="http',
            '<script src="https',
            '<link href="http',
            '<link href="https',
            "@import url('http",
            "@import url('https",
        ):
            assert pattern not in content, (
                f"F6: {fname} contains external CDN reference {pattern!r}; "
                f"cut-042R mandate: zero CDN."
            )


def test_spa_uses_real_fetch_not_mock() -> None:
    """F6: app.js 必须真实 fetch /api/v1/demo/* (不是 mock data)."""
    app_js = SPA_ROOT / "app.js"
    if not app_js.is_file():
        # some SPAs inline JS into HTML — accept that shape too
        index_html = (SPA_ROOT / "index.html").read_text(encoding="utf-8") if (SPA_ROOT / "index.html").is_file() else ""
        combined = index_html
    else:
        combined = app_js.read_text(encoding="utf-8")

    assert "fetch(" in combined, "F6: app.js must use fetch() to call /api/v1/demo/*"
    assert "/api/v1/demo/" in combined, "F6: app.js must call /api/v1/demo/* endpoints"


def test_spa_zero_build_artifact() -> None:
    """F6: 零 build — vanilla JS only, no require()/import..from 'webpack' etc."""
    for fname in ("index.html", "app.js"):
        fpath = SPA_ROOT / fname
        if not fpath.is_file():
            continue
        content = fpath.read_text(encoding="utf-8")
        # 禁 build artifact
        assert "require(" not in content, f"F6: {fname} contains require() — zero build mandate"
        # 禁 webpack chunk 注释
        assert "webpackChunkName" not in content, f"F6: {fname} contains webpackChunkName — zero build mandate"


def test_spa_does_not_break_existing_static_demo() -> None:
    """F6: 既有静态页 demos/procurement-review-demo.html 必须保留 (PRD AC6 fallback)."""
    existing = REPO_ROOT / "demos" / "procurement-review-demo.html"
    assert existing.is_file(), (
        f"F6: existing static demo {existing} must be preserved (PRD AC6 fallback). "
        f"Do not delete it."
    )
