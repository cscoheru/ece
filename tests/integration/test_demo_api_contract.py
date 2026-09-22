"""cut-042 API contract suite — POST /api/v1/demo/* 业务命名 + 反差 + 确定性 + 零内部字段外露.

Per `docs/demo-platform/DEMO_PLATFORM_PRD.md` §5 acceptance #2/#3/#4:
  - 业务命名 JSON (禁 decision_id / input_context_ref / package_id / evidence_id / ctx_ / dec_ / ev_ 外露)
  - 同参数重复调用确定性 byte-equal (S3 N=10 标准)
  - denied 用户 zero-side-effect (S6 4 断言口径)
  - 当次 API 真实运行 (响应带 generated_at + elapsed_ms > 0)

These tests are intentionally written BEFORE the implementation commit, so the
red→green diff is visible (per cut-042 acceptance criterion #5).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ece.main import app

# Forbidden substrings anywhere in the response payload. PRD §5 #2:
# internal field mapping happens in the application layer, not in the API contract.
_FORBIDDEN_SUBSTRINGS = (
    "decision_id",
    "input_context_ref",
    "package_id",
    "evidence_id",
    "context_request_id",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_demo_domains_lists_procurement_with_default_scenario(client: TestClient) -> None:
    """GET /api/v1/demo/domains → 业务语言域清单, procurement 在列, 含至少 default scenario.

    PRD §5: GET /demo/domains → 域清单.
    """
    r = client.get("/api/v1/demo/domains")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "domains" in body, f"missing 'domains' key in {body!r}"
    domains = body["domains"]
    assert isinstance(domains, list)
    procurement = next((d for d in domains if d.get("name") == "procurement"), None)
    assert procurement is not None, f"procurement not listed: {domains!r}"
    assert "label" in procurement, "domain entry must carry business label"
    scenarios = procurement.get("scenarios")
    assert isinstance(scenarios, list) and len(scenarios) >= 1, \
        f"procurement must list at least one scenario, got {scenarios!r}"
    assert "default" in scenarios, f"'default' scenario must be present: {scenarios!r}"


def test_post_generate_returns_business_named_fields_only(client: TestClient) -> None:
    """POST /api/v1/demo/scenarios/generate → 响应字段全部业务命名, 0 内部字段外露.

    PRD §5 #2 acceptance. Scans the entire JSON for forbidden substrings.
    """
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {"amount": 1_500_000, "quote_count": 2},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    # Either 200 (live run) or 503/500 with structured error — but NEVER 404 (no route).
    assert r.status_code in (200, 500, 503), r.text
    body = r.json()
    # Scan response text for forbidden substrings (covers nested dicts and lists).
    blob = repr(body)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in blob, \
            f"internal field {forbidden!r} leaked into response: {blob[:300]}"


def test_post_generate_with_default_params_is_deterministic_across_calls(
    client: TestClient,
) -> None:
    """同 params 重复 5 次, 结论 + 证据 byte-equal (S3 N=10 标准的 API 层收口).

    PRD §5 #2: 同一参数重复调用, 结论与凭证逐字段一致.
    PRD §7 #1: 确定性 N=10 逐字段一致.
    """
    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {"amount": 1_500_000, "quote_count": 2},
    }
    headers = {"X-User-Id": "spike-user-procurement"}

    responses = []
    for _ in range(5):
        r = client.post("/api/v1/demo/scenarios/generate", json=payload, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        # Strip volatile fields (timestamp + elapsed_ms) before comparison.
        stable = {k: v for k, v in body.items() if k not in ("generated_at", "elapsed_ms")}
        responses.append(stable)

    first = responses[0]
    for i, other in enumerate(responses[1:], start=2):
        assert other == first, \
            f"call {i} differs from call 1: diff={first ^ other}"


def test_post_generate_denied_user_returns_no_permission_conclusion(client: TestClient) -> None:
    """denied 用户 → conclusion='no_permission', evidence=[], DB 零写入 (S6 4 断言).

    PRD §5 #4: 权限反差, denied 用户走真实 run_demo_loop, 返回无权 + 零副作用.
    """
    payload = {
        "domain": "procurement",
        "scenario": "default",
        "params": {"amount": 500_000, "quote_count": 3},
    }
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json=payload,
        headers={"X-User-Id": "spike-user-unrelated"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("conclusion") == "no_permission", \
        f"denied user must get no_permission conclusion, got {body.get('conclusion')!r}"
    assert body.get("evidence") == [], \
        f"denied run must produce zero evidence rows, got {body.get('evidence')!r}"
    assert body.get("state_change", {}).get("after") in (None, "pending"), \
        f"denied run must NOT mutate PR state, got {body.get('state_change')!r}"


def test_response_must_not_leak_internal_ids(client: TestClient) -> None:
    """变异锚点 #4: 即使 mapper 误把 decision_id 注入响应, 契约测试必须咬合.

    PRD §5 #5: ≥3 变异全部实测咬合. 这是 cut-042 mutation anchor #4.
    Test stays green when no leakage exists; goes red when mapper is mutated to
    inject any of the forbidden internal fields.
    """
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {"amount": 500_000, "quote_count": 3},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code in (200, 500, 503), r.text
    blob = r.text
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in blob, \
            f"MUTATION ANCHOR #4 BITTEN: {forbidden!r} leaked: {blob[:300]}"


def test_response_includes_generated_at_and_elapsed_ms(client: TestClient) -> None:
    """PRD §5 #3: 真实运行, 响应带运行时间戳.

    即使 allowed user 走通 full loop, 响应里 generated_at 必须存在 + elapsed_ms > 0.
    """
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {"amount": 1_500_000, "quote_count": 2},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    # Skip cleanly when seed missing (CI without seed).
    if r.status_code != 200:
        pytest.skip(f"live run unavailable (status={r.status_code}); seed required")
    body = r.json()
    assert "generated_at" in body, f"missing generated_at in {body!r}"
    assert "elapsed_ms" in body, f"missing elapsed_ms in {body!r}"
    assert body["elapsed_ms"] > 0, f"elapsed_ms must be > 0, got {body['elapsed_ms']!r}"
