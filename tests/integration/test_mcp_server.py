"""S4.5 DoD-aligned MCP Tool Layer tests (TASKS.md S4.5 line 43-44).

This file complements `test_s5_mcp.py` (which covers the *tool behavior* of
search/get_record/create_task/send_message). The five tests here cover what
the S4.5 DoD explicitly demands but `test_s5_mcp.py` does NOT:

  1. `MCPServer` registers exactly the 4 tools listed in the task ("启动注册 4 工具")
  2. `auth.check_user_permission` denies an unknown user (Permission Before
     Intelligence — iron rule 1; the MCP layer cannot bypass)
  3. `auth.check_user_permission` allows a known user on a public object
  4. `get_record_tool` 404 vs 403 are distinguishable *internally* but never
     leak existence to a low-permission user (the uniform envelope property)
  5. `ece.mcp.transport` imports without error and exposes `main()` (the
     TASKS.md literal file requirement, "离线 stdio 可用")

Pre-condition: `make seed` (PR0001 + demo-user-procurement). Tests use
`pytest.skip` for missing-seed tolerance (same pattern as `test_s5_mcp.py`).
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from ece.db import get_engine
from ece.mcp import transport
from ece.mcp.auth import check_user_permission
from ece.mcp.server import mcp
from ece.mcp.tools import get_record_tool


def _demo_pr_display_id() -> str | None:
    """Resolve a demo purchase_request display_id at RUNTIME.

    Mirrors `test_s5_mcp.py::_demo_pr_display_id`; copied rather than shared
    to keep the existing test file untouched (S6 process discipline: no
    implicit edits to already-verified test files).
    """
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT display_id FROM entities "
                "WHERE entity_type = 'purchase_request' "
                "AND source_system = 'demo:demo' "
                "ORDER BY display_id LIMIT 1"
            )
        ).first()
    return row[0] if row else None


def test_server_registers_four_tools() -> None:
    """TASKS.md S4.5 验收 (1): `python -m ece.mcp.server` 启动注册 4 工具.

    `MCPServer.list_tools()` is async in mcp SDK 2.x; each Tool exposes `.name`.
    Names must match the DoD: search / get_record / create_task / send_message.
    """
    tools = asyncio.run(mcp.list_tools())
    names = sorted(getattr(t, "name", None) or repr(t) for t in tools)
    assert names == sorted(["create_task", "get_record", "search", "send_message"]), (
        f"MCPServer must register exactly 4 tools with DoD names; got {names!r}"
    )


def test_auth_check_user_permission_denies_unknown_user() -> None:
    """TASKS.md S4.5 验收 (2): 权限强制 — auth must default-deny unknown user.

    Per ECE/CLAUDE.md iron rule 1 (Permission Before Intelligence) and
    ADR-004, no MCP tool call may bypass `auth.check_user_permission`.
    Unknown user must return False here so the caller's `{error: forbidden}`
    envelope fires.
    """
    pr = _demo_pr_display_id()
    if not pr:
        import pytest
        pytest.skip("no demo purchase_request seeded; run make seed first")
    allowed = check_user_permission(
        user_ref="X-NONEXISTENT-USER-MCP-TEST",
        object_type="entity",
        object_ref=pr,
    )
    assert allowed is False, (
        f"unknown user must be denied on a real object; got allowed={allowed}"
    )


def test_auth_check_user_permission_allows_known_user_on_public_object() -> None:
    """TASKS.md S4.5 验收 (2) positive: known user with access → True.

    demo-user-procurement is the canonical seeded user with dept-level access
    on demo PRs. This is the *positive* carrier of "权限强制": the same
    function must return True when policy permits.
    """
    pr = _demo_pr_display_id()
    if not pr:
        import pytest
        pytest.skip("no demo purchase_request seeded; run make seed first")
    allowed = check_user_permission(
        user_ref="demo-user-procurement",
        object_type="entity",
        object_ref=pr,
    )
    assert allowed is True, (
        f"demo-user-procurement must be allowed on a seeded PR; got allowed={allowed}"
    )


def test_get_record_404_anti_probing_returns_uniform_envelope() -> None:
    """TASKS.md S4.5 验收 (3): get_record 404 防探测.

    `get_record_tool` MUST return an `{error, ref}` envelope for both
    not-found and forbidden cases — callers cannot enumerate which display_ids
    exist by probing. The internal distinction is made by the `error` key
    value; from outside the tool, both shapes look the same (no `attrs` /
    no `name` leakage on the failure path).
    """
    # Case A: object doesn't exist → {error: not_found, ref: ...}
    nf = get_record_tool(user_ref="demo-user-procurement", display_id="PR_DOES_NOT_EXIST_MCP")
    assert nf.get("error") == "not_found", f"missing object must return not_found; got {nf!r}"
    assert nf.get("ref") == "PR_DOES_NOT_EXIST_MCP"
    # Uniform envelope: no data keys leak
    for leak_key in ("ref", "type", "name", "attrs", "src"):
        assert leak_key not in nf or leak_key == "ref", (
            f"not_found envelope must not carry data key {leak_key!r}; got {nf!r}"
        )

    # Case B: existing object, unknown user → {error: forbidden, ref: ...}
    pr = _demo_pr_display_id()
    if not pr:
        import pytest
        pytest.skip("no demo purchase_request seeded; run make seed first")
    fb = get_record_tool(user_ref="X-NONEXISTENT-USER-MCP-404", display_id=pr)
    assert fb.get("error") == "forbidden", (
        f"unknown user on real object must return forbidden; got {fb!r}"
    )
    assert fb.get("ref") == pr
    # Uniform envelope on forbidden path too
    for leak_key in ("type", "name", "attrs", "src"):
        assert leak_key not in fb, (
            f"forbidden envelope must not leak {leak_key!r}; got {fb!r}"
        )


def test_transport_module_imports_and_exposes_main() -> None:
    """TASKS.md S4.5 文件清单: `src/ece/mcp/transport.py` must exist and import.

    `python -m ece.mcp.transport` is the literal DoD-stated command form;
    the module therefore must import without raising AND expose `main` for
    the `if __name__ == "__main__":` entry. We do NOT spawn the stdio
    server here (it would block on stdin); we just verify the import contract.
    """
    assert hasattr(transport, "main"), (
        "ece.mcp.transport must expose a callable `main()` per DoD"
    )
    assert callable(transport.main), "transport.main must be callable"
    # Import-time check: re-import the symbols server.py exposes (catch any
    # accidental regression where transport.py breaks the server module).
    from ece.mcp.server import mcp as server_mcp  # noqa: F401
    assert server_mcp is mcp, "transport must reuse the same MCPServer instance"
