"""cut-042 API contract suite — POST /api/v1/demo/* 业务命名 + 反差 + 确定性 + 零内部字段外露.

Per `docs/demo-platform/DEMO_PLATFORM_PRD.md` §5 acceptance #2/#3/#4:
  - 业务命名 JSON (禁 decision_id / input_context_ref / package_id / evidence_id / ctx_ / dec_ / ev_ 外露)
  - 同参数重复调用确定性 byte-equal (S3 N=10 标准)
  - denied 用户 zero-side-effect (S6 4 断言口径)
  - 当次 API 真实运行 (响应带 generated_at + elapsed_ms > 0)

cut-042R additions (Codex HOLD 2026-09-22, F1/F4/F5/F7):
  - F1: 权限不可伪造 — body.params.actor 不得覆盖 X-User-Id
  - F4: clean 路径不崩 — auto_approved 允许 0 evidence rows (但不能 500)
  - F5: 业务 reason — 顶层 reason 必须是决策的业务原因, 不是 "ok"
  - F5: 未知 domain/scenario 返回 422 (不是 500)
  - F5: 路径穿越 (../) 返回 422
  - F7: 严格 == 200;删除所有 (200, 500, 503) 接受 + 失败 skip
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

    cut-042R F7: 严格断言 == 200 (no 500/503 acceptance, no skip on miss).
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
    # cut-042R F7: 严格 == 200 (the previous (200, 500, 503) acceptance was Codex's F7 finding).
    assert r.status_code == 200, f"live run must succeed with strict 200, got {r.status_code}: {r.text}"
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
        assert r.status_code == 200, f"deterministic run must succeed; got {r.status_code}: {r.text}"
        body = r.json()
        # Strip volatile fields (top-level timestamp + elapsed_ms) before comparison.
        stable = {k: v for k, v in body.items() if k not in ("generated_at", "elapsed_ms")}
        # Evidence rows also carry a `recorded_at` timestamp (microsecond precision);
        # strip per-row so byte-equality compares decision-logic fields only.
        stable["evidence"] = [
            {k: v for k, v in row.items() if k != "recorded_at"}
            for row in stable.get("evidence", [])
        ]
        responses.append(stable)

    first = responses[0]
    for i, other in enumerate(responses[1:], start=2):
        assert other == first, \
            f"call {i} differs from call 1: diff_keys={set(first) ^ set(other)}; " \
            f"first_only={set(first) - set(other)}; other_only={set(other) - set(first)}"


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
    assert r.status_code == 200, f"denied path returns 200 with conclusion=no_permission, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("conclusion") == "no_permission", \
        f"denied user must get no_permission conclusion, got {body.get('conclusion')!r}"
    assert body.get("evidence") == [], \
        f"denied run must produce zero evidence rows, got {body.get('evidence')!r}"
    assert body.get("state_change", {}).get("after") in (None, "pending"), \
        f"denied run must NOT mutate PR state, got {body.get('state_change')!r}"


def test_response_must_not_leak_internal_ids(client: TestClient) -> None:
    """变异锚点 #4: 即使 mapper 误把 decision_id 注入响应, 契约测试必须咬合.

    cut-042R F7: 严格 == 200 (no skip, no (200, 500, 503) acceptance).
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
    assert r.status_code == 200, f"strict 200; got {r.status_code}: {r.text}"
    blob = r.text
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in blob, \
            f"MUTATION ANCHOR #4 BITTEN: {forbidden!r} leaked: {blob[:300]}"


def test_response_includes_generated_at_and_elapsed_ms(client: TestClient) -> None:
    """PRD §5 #3: 真实运行, 响应带运行时间戳.

    cut-042R F7: 删除 skip on non-200;改为严格断言.
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
    # cut-042R F7: 严格断言 — 不允许 skip;若 seed 未运行则测试失败
    assert r.status_code == 200, \
        f"live run must succeed (seed required); got {r.status_code}: {r.text}"
    body = r.json()
    assert "generated_at" in body, f"missing generated_at in {body!r}"
    assert "elapsed_ms" in body, f"missing elapsed_ms in {body!r}"
    assert body["elapsed_ms"] > 0, f"elapsed_ms must be > 0, got {body['elapsed_ms']!r}"


# ---------------------------------------------------------------------------
# cut-042R additions — F1 / F4 / F5 / F7
# ---------------------------------------------------------------------------


def test_denied_user_with_body_actor_override_returns_no_permission(client: TestClient) -> None:
    """cut-042R F1: 权限不可伪造.

    客户端在 body params.actor 中塞入允许用户名, 试图冒充, 但 X-User-Id 是 denied.
    API 必须返回 no_permission (200 + conclusion), 不能被 body 覆盖.

    黑盒复现: header X-User-Id=spike-user-unrelated (denied), body params.actor=spike-user-procurement
    → 200 no_permission.
    """
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {
                "actor": "spike-user-procurement",   # 试图冒充
                "amount": 1_500_000,
                "quote_count": 2,
            },
        },
        headers={"X-User-Id": "spike-user-unrelated"},  # 真实身份: denied
    )
    assert r.status_code == 200, f"F1: must succeed with no_permission conclusion, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("conclusion") == "no_permission", \
        f"F1: body.actor override must NOT bypass denied X-User-Id; got conclusion={body.get('conclusion')!r}"
    assert body.get("actor") == "spike-user-unrelated", \
        f"F1: response.actor must reflect the authenticated X-User-Id, not body.actor; got {body.get('actor')!r}"


def test_auto_approved_clean_path_returns_200_and_no_indexerror(client: TestClient) -> None:
    """cut-042R F4: clean 路径不崩.

    amount=500_000 (< 阈值 1_000_000) + quote_count=3 (= REQUIRED) → 全部条件 fail →
    0 evidence rows. 修复前 evidence_ids[0] IndexError → 500.
    修复后: review_evidence_id 可为 NULL (auto_approved 路径), 返回 200 + auto_approved.
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
    assert r.status_code == 200, \
        f"F4: clean path must NOT crash (IndexError); got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("conclusion") == "auto_approved", \
        f"F4: clean path must conclude auto_approved, got {body.get('conclusion')!r}"
    # auto_approved 路径允许 evidence 为空 (no passed conditions)
    assert body.get("evidence") == [], \
        f"F4: auto_approved may have zero evidence; got {body.get('evidence')!r}"


def test_top_level_reason_is_business_language_not_loop_state(client: TestClient) -> None:
    """cut-042R F5: 业务 reason.

    修复前 mapper.to_business 返回 "reason": result.reason (loop 状态 "ok").
    修复后 allowed 路径返回 decision["reason"] (业务语言); denied 路径返回业务字符串.
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
    assert r.status_code == 200, f"F5: must succeed; got {r.status_code}: {r.text}"
    body = r.json()
    reason = body.get("reason", "")
    assert reason != "ok", \
        f"F5: top-level reason must be business language, NOT loop state 'ok'; got {reason!r}"
    # 业务语言至少包含:金额/报价/复核/通过 中之一 (procurement 业务术语)
    assert any(kw in reason for kw in ("金额", "报价", "复核", "通过", "免比价")), \
        f"F5: reason must contain business keyword; got {reason!r}"


def test_top_level_reason_for_denied_user_is_business_language(client: TestClient) -> None:
    """cut-042R F5: denied 路径业务 reason (不是 loop state 'no permitted context')."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "default",
            "params": {"amount": 1_500_000, "quote_count": 2},
        },
        headers={"X-User-Id": "spike-user-unrelated"},
    )
    assert r.status_code == 200, f"F5 denied: must succeed; got {r.status_code}: {r.text}"
    body = r.json()
    reason = body.get("reason", "")
    # denied 路径 reason 不能是 "no permitted context" (loop 状态)
    assert "no permitted" not in reason.lower(), \
        f"F5: denied reason must be business language; got {reason!r}"


def test_unknown_domain_returns_422_not_500(client: TestClient) -> None:
    """cut-042R F5: 未知 domain → 422 (不是 500 FileNotFoundError)."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "nonexistent-pack",
            "scenario": "default",
            "params": {},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 422, \
        f"F5: unknown domain must return 422; got {r.status_code}: {r.text}"


def test_unknown_scenario_returns_422_not_500(client: TestClient) -> None:
    """cut-042R F5: 未知 scenario → 422."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "nonexistent-scenario",
            "params": {},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 422, \
        f"F5: unknown scenario must return 422; got {r.status_code}: {r.text}"


def test_path_traversal_in_domain_returns_422(client: TestClient) -> None:
    """cut-042R F5: 路径穿越 → 422 (拒绝 ../, /etc/passwd 等)."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "../../etc",
            "scenario": "default",
            "params": {},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 422, \
        f"F5: path traversal in domain must return 422; got {r.status_code}: {r.text}"


def test_path_traversal_in_scenario_returns_422(client: TestClient) -> None:
    """cut-042R F5: scenario 路径穿越 → 422."""
    r = client.post(
        "/api/v1/demo/scenarios/generate",
        json={
            "domain": "procurement",
            "scenario": "../passwd",
            "params": {},
        },
        headers={"X-User-Id": "spike-user-procurement"},
    )
    assert r.status_code == 422, \
        f"F5: path traversal in scenario must return 422; got {r.status_code}: {r.text}"
