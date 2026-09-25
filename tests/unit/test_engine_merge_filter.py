"""OEI-009 — DB-free-ish unit tests for the per-result permission filter.

The filter itself is DB-touching (registry lookup + ACL load). To keep these
tests fast and CI-safe, we use a minimal in-memory fake SQL engine that
satisfies the exact `engine.connect() / execute(text, params)` interface the
filter uses. No real PG; no network.

Coverage:
  - anonymous → public only (A6)
  - anonymous → restricted denied (anonymous_restricted)
  - identified with allow ACL → allowed (A4 first half)
  - identified with allow ACL on a different user → denied (A4 second half)
  - dedup by `engine_filename` (A6)
  - non-`user_file` source_type → dropped (hidden_by_reason)
  - un-registered engine doc → fail-closed (no_registry, A5)
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from ece.connectors.onyx.port import EngineDocument
from ece.consulting.permissions_filter import filter_engine_items
from ece.identity.parser import Identity


# ---------------------------------------------------------------------------
# Fake SQL engine — the smallest possible surface the filter touches.
# ---------------------------------------------------------------------------


@dataclass
class _Row:
    """A row like SQLAlchemy would return — indexable tuple."""

    data: tuple[Any, ...]

    def __getitem__(self, i: int) -> Any:
        return self.data[i]

    def __iter__(self):
        return iter(self.data)


class _FakeConnection:
    def __init__(self, engine: "_FakeSqlEngine") -> None:
        self._engine = engine

    def execute(self, statement: Any, params: dict | None = None) -> "_FakeResult":
        text = str(statement)
        return _FakeResult(self._engine._dispatch(text, params or {}))


class _FakeResult:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def first(self) -> _Row | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[_Row]:
        return list(self._rows)

    def scalar(self) -> Any:
        return self._rows[0][0] if self._rows else None


class _FakeSqlEngine:
    """In-memory fake SQL engine with two tables: engine_documents, acl_entries."""

    def __init__(
        self,
        *,
        engine_documents: list[dict] | None = None,
        acl_entries: list[dict] | None = None,
    ) -> None:
        self._engine_documents = list(engine_documents or [])
        self._acl_entries = list(acl_entries or [])

    @contextmanager
    def connect(self):
        yield _FakeConnection(self)

    def _dispatch(self, text: str, params: dict) -> list[_Row]:
        if "FROM engine_documents" in text and "engine_filename" in text:
            row = self._lookup_engine_doc(params)
            return [_Row(row)] if row else []
        if "FROM acl_entries" in text:
            rows = self._lookup_acl(params)
            return [_Row(r) for r in rows]
        if "COUNT(*) FROM engine_documents" in text:
            ename = params.get("ename", "onyx")
            n = sum(1 for r in self._engine_documents if r.get("engine_name") == ename)
            return [_Row((n,))]
        return []

    def _lookup_engine_doc(self, params: dict) -> tuple | None:
        ename = params["ename"]
        fname = params["fname"]
        for r in self._engine_documents:
            if r["engine_name"] == ename and r["engine_filename"] == fname:
                return (
                    r["id"],
                    r["engine_name"],
                    r["engine_project_id"],
                    r["engine_filename"],
                    r["original_filename"],
                    r.get("engine_document_id"),
                    r.get("title"),
                    r["classification"],
                    r["uploaded_by"],
                    r.get("department", ""),
                    r.get("org_id"),
                    datetime(2026, 9, 25, tzinfo=timezone.utc),
                )
        return None

    def _lookup_acl(self, params: dict) -> list[tuple]:
        otype = params["otype"]
        oref = params["oref"]
        out = []
        for r in self._acl_entries:
            if r["object_type"] == otype and r["object_ref"] == oref:
                out.append(
                    (
                        r["subject_type"],
                        r["subject_ref"],
                        r["effect"],
                        r.get("valid_from"),
                        r.get("valid_to"),
                        r.get("source_system", "test"),
                    )
                )
        return out


# ---------------------------------------------------------------------------
# Helpers — build inputs cheaply.
# ---------------------------------------------------------------------------


def _doc(title: str, *, snippet: str = "...", source_type: str = "user_file") -> EngineDocument:
    return EngineDocument(
        engine_doc_id=f"citation_{title}",
        title=title,
        snippet=snippet,
        source_type=source_type,
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        raw={},
    )


def _registry_row(
    *,
    id: int,
    engine_filename: str,
    classification: str = "public",
    uploaded_by: str = "alice",
    org_id: str | None = None,
) -> dict:
    return {
        "id": id,
        "engine_name": "onyx",
        "engine_project_id": 1,
        "engine_filename": engine_filename,
        "original_filename": engine_filename,
        "engine_document_id": f"uuid-{id}",
        "title": engine_filename,
        "classification": classification,
        "uploaded_by": uploaded_by,
        "department": "",
        "org_id": org_id,
    }


def _allow_acl(
    *,
    subject_ref: str = "alice",
    valid_from: date | None = None,
    valid_to: date | None = None,
    for_id: int = 1,
) -> dict:
    return {
        "object_type": "engine_document",
        "object_ref": f"engine_document:{for_id}",
        "subject_type": "user",
        "subject_ref": subject_ref,
        "effect": "allow",
        "valid_from": valid_from,
        "valid_to": valid_to,
        "source_system": "test",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


# A6: anonymous → public only
def test_anonymous_public_allowed() -> None:
    sql = _FakeSqlEngine(engine_documents=[_registry_row(id=1, engine_filename="public.md")])
    result = filter_engine_items(
        [_doc("public.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    assert len(result.allowed_items) == 1
    assert result.hidden_count == 0


def test_anonymous_internal_denied() -> None:
    """A6 verbatim: anonymous only sees `public`. `internal` defaults allow in
    the matrix, but the filter narrows further for anonymous callers."""
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="internal.md", classification="internal"),
        ]
    )
    result = filter_engine_items(
        [_doc("internal.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("anonymous_restricted") == 1


def test_anonymous_restricted_denied() -> None:
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="secret.md", classification="restricted"),
        ]
    )
    result = filter_engine_items(
        [_doc("secret.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("anonymous_restricted") == 1


# A5: not in registry → fail-closed (never expose existence)
def test_unregistered_fail_closed() -> None:
    """A5 verbatim: engine has it, ECE has no registry row → not surfaced."""
    sql = _FakeSqlEngine(engine_documents=[])  # nothing registered
    result = filter_engine_items(
        [_doc("ghost.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity(user_ref="alice"),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("no_registry") == 1
    assert result.hidden_count == 1


# A4 (first half): identified user with allow ACL → allowed
def test_identified_with_allow_acl_allowed() -> None:
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="restricted.md", classification="restricted"),
        ],
        acl_entries=[_allow_acl(subject_ref="alice")],
    )
    result = filter_engine_items(
        [_doc("restricted.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity(user_ref="alice"),
    )
    assert len(result.allowed_items) == 1
    assert result.allowed_items[0].title == "restricted.md"


# A4 (second half): a different user without allow → denied
def test_other_user_without_acl_denied() -> None:
    """Same registry row, ACL allows alice, caller is bob → denied."""
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="restricted.md", classification="restricted"),
        ],
        acl_entries=[_allow_acl(subject_ref="alice")],
    )
    result = filter_engine_items(
        [_doc("restricted.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity(user_ref="bob"),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("denied") == 1


# A6: dedup by engine_filename — multiple chunks → one card
def test_dedup_same_filename() -> None:
    """Multiple EngineDocuments with the same `title` collapse to ONE EngineItem.

    Keeps the first occurrence (its snippet wins for the card face).
    """
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="multi-chunk.md", classification="public"),
        ]
    )
    docs = [
        _doc("multi-chunk.md", snippet="chunk-1"),
        _doc("multi-chunk.md", snippet="chunk-2"),
        _doc("multi-chunk.md", snippet="chunk-3"),
    ]
    result = filter_engine_items(
        docs,
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    assert len(result.allowed_items) == 1
    assert result.allowed_items[0].snippet == "chunk-1"  # first wins
    assert result.hidden_count == 0  # NOT counted as hidden — collapsed


# source_type != "user_file" → dropped (hidden, not surfaced)
def test_non_user_file_dropped() -> None:
    sql = _FakeSqlEngine(engine_documents=[])  # even if registered, source_type is the gate
    doc = _doc("web-result.md", source_type="web")
    result = filter_engine_items(
        [doc],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("non_user_file") == 1


# Time-box on allow rule: allow expires → falls through to classification default
def test_allow_expires_falls_through_to_classification() -> None:
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="expiring.md", classification="restricted"),
        ],
        acl_entries=[
            _allow_acl(subject_ref="alice", valid_to=date(2026, 9, 24)),
        ],
    )
    result = filter_engine_items(
        [_doc("expiring.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity(user_ref="alice"),
    )
    assert result.allowed_items == []
    assert result.hidden_by_reason.get("denied") == 1


# Org scope (A9 minimum): Identity.org_id is read but doesn't filter
def test_org_id_carried_not_used() -> None:
    """A9: org dimension is on Identity; per-result filter does NOT use it yet.

    Different org_id between caller and registry row → still allowed when
    classification is public. This is the OEI-010 hook point.
    """
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(
                id=1,
                engine_filename="cross-org.md",
                classification="public",
                org_id="org-A",
            ),
        ],
    )
    result = filter_engine_items(
        [_doc("cross-org.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity(user_ref="bob", org_id="org-B"),
    )
    assert len(result.allowed_items) == 1


# Side-channel sanity: hidden_count is computed but the response doesn't
# reflect it — we already return only allowed_items to merge_engine.
def test_hidden_breakdown() -> None:
    """The breakdown dict is for audit only; merge_engine ignores it."""
    sql = _FakeSqlEngine(
        engine_documents=[
            _registry_row(id=1, engine_filename="public.md", classification="public"),
            _registry_row(id=2, engine_filename="secret.md", classification="restricted"),
        ],
        acl_entries=[],
    )
    result = filter_engine_items(
        [_doc("public.md"), _doc("secret.md"), _doc("ghost.md")],
        sql_engine=sql,
        content_engine_name="onyx",
        identity=Identity.anonymous(),
    )
    # public.md → allowed; secret.md → anonymous_restricted; ghost.md → no_registry
    assert len(result.allowed_items) == 1
    assert result.hidden_by_reason == {
        "anonymous_restricted": 1,
        "no_registry": 1,
    }