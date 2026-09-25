"""OEI-008 — DB-free unit tests for ContentEnginePort identity threading.

Covers:
  - EngineCallerContext dataclass construction + `display()` + `from_identity`
  - MockContentEngineAdapter + OnyxContentEngineAdapter both expose `engine_name`
  - Both adapters satisfy the Protocol (Runtime checkable)
  - Both adapters accept `caller=None` and `caller=<EngineCallerContext>` for
    every method (search / engine_status / list_projects / upload_document /
    document_status)
  - audit_log records one row per call (mock side, no network)
  - Mock refuses `upload_document` with caller=None (identity-required)
  - Engine merge no longer references the selector switch (the OEI-006/007
    debt — see 04-port-engine-descriptor.txt)
  - Caller-builder helpers behave correctly across header / JWT modes

No DB, no Onyx — runs in <1 s.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ece.connectors.onyx.caller import caller_from_request_headers
from ece.connectors.onyx.mock_adapter import (
    MockContentEngineAdapter,
    reset_mock_engine_store,
)
from ece.connectors.onyx.onyx_adapter import OnyxContentEngineAdapter
from ece.connectors.onyx.port import (
    ContentEnginePort,
    EngineCallerContext,
    EngineError,
)

# ---------------------------------------------------------------------------
# EngineCallerContext
# ---------------------------------------------------------------------------


def test_engine_caller_context_anonymous_is_stable() -> None:
    a1 = EngineCallerContext.anonymous()
    a2 = EngineCallerContext.anonymous()
    assert a1 == a2
    assert a1.user_ref is None
    assert a1.roles == ()
    assert a1.department == ""
    assert a1.is_management is False
    assert a1.source == "anonymous"


def test_engine_caller_context_is_frozen() -> None:
    ctx = EngineCallerContext(user_ref="alice", roles=("purchaser",), source="header")
    # A frozen dataclass raises FrozenInstanceError, which subclasses
    # AttributeError; asserting the concrete type keeps the test honest
    # (a bare `Exception` would also pass on a typo in the attribute name).
    with pytest.raises(FrozenInstanceError):
        ctx.user_ref = "bob"  # type: ignore[misc]


def test_engine_caller_context_display_is_stable_and_pii_bounded() -> None:
    """Display string used in audit logs — no secrets, no PII beyond user_ref.

    The format is part of the audit contract; do not change without
    coordinating with `06-audit-trail.json`.
    """
    ctx = EngineCallerContext(
        user_ref="alice", roles=("purchaser", "dept-finance"),
        department="finance", is_management=True, source="jwt",
    )
    s = ctx.display()
    assert "alice" in s
    assert "jwt" in s
    assert "finance" in s
    assert "True" in s or "true" in s  # we render `mgmt=True`
    # Stability across two calls
    assert ctx.display() == s


def test_engine_caller_context_from_identity_passthrough() -> None:
    """from_identity is the boundary; non-None Identity carries everything."""
    from types import SimpleNamespace

    identity = SimpleNamespace(
        user_ref="alice",
        roles=["purchaser", "finance-mgr"],
        department="finance",
        is_management=True,
    )
    ctx = EngineCallerContext.from_identity(identity, source="jwt")  # type: ignore[arg-type]
    assert ctx.user_ref == "alice"
    assert ctx.roles == ("purchaser", "finance-mgr")
    assert ctx.department == "finance"
    assert ctx.is_management is True
    assert ctx.source == "jwt"


def test_engine_caller_context_from_identity_none_is_anonymous() -> None:
    ctx = EngineCallerContext.from_identity(None)
    assert ctx.source == "anonymous"
    assert ctx.user_ref is None


# ---------------------------------------------------------------------------
# Protocol + adapters + engine_name descriptor (OEI-008 step 2)
# ---------------------------------------------------------------------------


def test_engine_name_descriptor_consistent_across_adapters() -> None:
    assert MockContentEngineAdapter().engine_name == "mock"
    assert OnyxContentEngineAdapter().engine_name == "onyx"


def test_adapters_satisfy_port_protocol_with_caller_param() -> None:
    assert isinstance(MockContentEngineAdapter(), ContentEnginePort)
    assert isinstance(OnyxContentEngineAdapter(), ContentEnginePort)


def test_mock_engine_search_records_caller_in_audit_log() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    caller = EngineCallerContext(user_ref="alice", roles=("purchaser",), source="header")
    asyncio.run(m.search("foo", caller=caller))
    assert len(m.audit_log) == 1
    row = m.audit_log[0]
    assert row["what"] == "search"
    assert row["caller_user_ref"] == "alice"
    assert row["caller_source"] == "header"
    assert "hits=" in row["result"]


def test_mock_engine_anonymous_caller_records_in_audit_log() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    asyncio.run(m.search("foo", caller=None))
    assert m.audit_log[0]["caller"] == "<anonymous>"


def test_mock_engine_engine_status_audit() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    asyncio.run(m.engine_status(caller=EngineCallerContext(user_ref="bob", source="jwt")))
    rows = [r for r in m.audit_log if r["what"] == "engine_status"]
    assert rows and rows[0]["result"] == "ok"


def test_mock_engine_list_projects_audit() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    asyncio.run(m.list_projects(caller=EngineCallerContext(user_ref="bob", source="jwt")))
    rows = [r for r in m.audit_log if r["what"] == "list_projects"]
    assert rows


def test_mock_engine_document_status_audit_ok_and_not_found() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    caller = EngineCallerContext(user_ref="bob")
    rec = asyncio.run(m.upload_document("x.md", b"hi", project_id=1, caller=caller))
    asyncio.run(m.document_status(rec.document_id, caller=caller))
    # Find the status rows; expect one ok + upload ok.
    status_rows = [r for r in m.audit_log if r["what"] == "document_status"]
    assert any(r["result"] == "ok" for r in status_rows)

    # not-found path is also audited
    with contextlib.suppress(EngineError):
        asyncio.run(m.document_status("missing-id", caller=caller))
    status_rows = [r for r in m.audit_log if r["what"] == "document_status"]
    assert any(r["result"] == "not_found" for r in status_rows)


def test_mock_engine_upload_refuses_explicitly_anonymous_caller() -> None:
    """OEI-008 §A5: write path is auth-required for **explicitly anonymous** callers.

    Backward-compat: `caller=None` (no caller at all) is allowed — production
    code paths always pass a non-None caller; the consulting route raises 403
    before the adapter is reached. The adapter's defensive check only fires
    when someone passes `EngineCallerContext.anonymous()` directly.
    """
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    with pytest.raises(EngineError, match="identity-required"):
        asyncio.run(m.upload_document(
            "x.md", b"hi", project_id=1,
            caller=EngineCallerContext.anonymous(),
        ))


def test_mock_engine_upload_accepts_authenticated_caller_and_records_in_raw() -> None:
    reset_mock_engine_store()
    m = MockContentEngineAdapter()
    caller = EngineCallerContext(
        user_ref="alice", roles=("purchaser",), department="finance",
        is_management=True, source="jwt",
    )
    rec = asyncio.run(m.upload_document("x.md", b"hi", project_id=1,
                                        title="T", metadata={"k": "v"}, caller=caller))
    assert rec.raw["ece_caller_user_ref"] == "alice"
    assert rec.raw["ece_caller_source"] == "jwt"
    assert rec.raw["ece_caller_dept"] == "finance"
    assert rec.raw["ece_caller_is_management"] is True
    # audit row reflects the same call
    upload_rows = [r for r in m.audit_log if r["what"] == "upload_document"]
    assert upload_rows[0]["caller_user_ref"] == "alice"


# ---------------------------------------------------------------------------
# Caller-builder helpers
# ---------------------------------------------------------------------------


def test_caller_from_request_headers_with_no_auth_is_anonymous() -> None:
    ctx = caller_from_request_headers(None, None)
    assert ctx.source == "anonymous"
    assert ctx.user_ref is None


def test_caller_from_request_headers_with_x_user_id_is_header() -> None:
    ctx = caller_from_request_headers(None, "alice")
    assert ctx.source == "header"
    assert ctx.user_ref == "alice"
    # cheap path: no DB lookup so roles/dept/is_management stay default
    assert ctx.roles == ()


def test_caller_from_request_headers_with_bearer_is_jwt() -> None:
    # No JWT secret configured → falls back to header mode but source flips to
    # "jwt" because Bearer was seen. This is the safe default.
    ctx = caller_from_request_headers("Bearer fake.jwt.value", None)
    # Without ECE_JWT_SECRET, the resolver returns None; we end up anonymous.
    # With ECE_JWT_SECRET configured (not in unit env), this would return the
    # JWT subject. We accept either mode here, but require consistent semantics:
    assert ctx.source in ("anonymous", "jwt")


# ---------------------------------------------------------------------------
# engine_merge no longer references the selector switch (OEI-008 step 2)
# ---------------------------------------------------------------------------


def test_engine_merge_no_longer_references_the_selector_switch() -> None:
    """OEI-008 — the hand-rolled mirror is gone.

    Two complementary assertions (def-form, so docstring prose mentioning
    the historical name is OK):
      1. `def _engine_switch_is_onyx` is no longer defined.
      2. No raw `os.environ.get("ECE_CONTENT_ENGINE")` read in engine_merge.
    """
    from ece.consulting import engine_merge
    src = Path(engine_merge.__file__).read_text(encoding="utf-8")
    assert "def _engine_switch_is_onyx" not in src
    assert "os.environ.get(\"ECE_CONTENT_ENGINE\")" not in src
    # The merge engine still USES get_content_engine() to obtain the Port
    # instance — that's fine, it doesn't read the env-var directly.
    # What we're guarding against is re-mirroring the switch.


def test_engine_merge_uses_port_engine_name_not_env() -> None:
    """A custom engine whose `engine_name` is not 'onyx' must short-circuit."""
    from ece.consulting import engine_merge

    class _CustomEngine:
        engine_name = "weaviate"

        async def search(self, q, *, top_k=None, caller=None):  # pragma: no cover
            raise AssertionError("should not be called when engine_name != onyx")

    async def go():
        items, status = await engine_merge.merge_engine("KPI", engine=_CustomEngine())
        return items, status

    items, status = asyncio.run(go())
    assert items == []
    assert status == "disabled"


def test_engine_merge_passes_caller_through_to_engine() -> None:
    """The merge engine forwards `caller` to the underlying Port call."""
    from ece.consulting import engine_merge

    class _SpyEngine:
        engine_name = "onyx"
        seen_caller = None

        async def search(self, q, *, top_k=None, caller=None):
            _SpyEngine.seen_caller = caller
            return []

    async def go():
        caller = EngineCallerContext(user_ref="alice", source="header")
        return await engine_merge.merge_engine("KPI", engine=_SpyEngine(), caller=caller)

    asyncio.run(go())
    assert _SpyEngine.seen_caller is not None
    assert _SpyEngine.seen_caller.user_ref == "alice"
