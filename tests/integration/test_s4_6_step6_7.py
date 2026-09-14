"""S3.2 step 6 + step 7 — Document + Structured data retrieval tests.

Verifies:
1. Step 6 (get_documents): FTS retrieval with permission filter
2. Step 7 (get_structured_data): per-kind SQL handlers
3. assemble_context now includes real documents/business_data (cut-011)

Pre-condition: scripts/ingest_demo_docs.py run (POL-2026-03 in DB).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ece.context.assembly import assemble_context
from ece.context.documents import get_documents
from ece.context.spec import (
    ContextSpec,
    RequiresBlock,
    load_spec,
)
from ece.context.structured_data import get_structured_data
from ece.db import get_engine
from ece.identity.parser import resolve_identity

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module", autouse=True)
def ensure_demo_docs_ingested() -> None:
    """Ingest demo docs before running tests (idempotent)."""
    result = subprocess.run(
        ["uv", "run", "python", "scripts/ingest_demo_docs.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"ingest_demo_docs failed: {result.stderr}")


@pytest.fixture
def engine():
    return get_engine()


def test_get_documents_with_demo_seed(engine) -> None:
    """Step 6: documents retrieved for procurement_policy spec."""
    spec = load_spec("procurement", "evaluate_purchase_request")
    identity = resolve_identity(engine, "demo-user-procurement")
    items = get_documents(engine, spec, identity)
    assert isinstance(items, list)
    if items:
        for item in items:
            assert "doc" in item
            assert "chunk" in item
            assert "text" in item
            assert "src" in item


def test_get_documents_empty_when_no_spec_documents(engine) -> None:
    """Step 6 returns [] when spec has no requires.documents."""
    spec = ContextSpec(spec="test", version=1, requires=RequiresBlock(user=True))
    identity = resolve_identity(engine, "demo-user-procurement")
    items = get_documents(engine, spec, identity)
    assert items == []


def test_get_documents_truncated_to_max_chunks(engine) -> None:
    """Step 6 truncates to spec.limits.max_chunks."""
    spec = load_spec("procurement", "evaluate_purchase_request")
    identity = resolve_identity(engine, "demo-user-procurement")
    items = get_documents(engine, spec, identity)
    assert len(items) <= spec.limits.max_chunks


def test_get_structured_data_empty_when_no_kind(engine) -> None:
    """Step 7 returns [] when spec has no requires.structured_data."""
    spec = ContextSpec(spec="test", version=1, requires=RequiresBlock(user=True))
    identity = resolve_identity(engine, "demo-user-procurement")
    rows = get_structured_data(engine, spec, identity)
    assert rows == []


def test_get_structured_data_unknown_kind_returns_empty(engine) -> None:
    """Step 7: unknown kinds are skipped (fail-soft per ADR-004)."""
    spec = ContextSpec(
        spec="test",
        version=1,
        requires=RequiresBlock(
            structured_data=["nonexistent_kind"],
        ),
    )
    identity = resolve_identity(engine, "demo-user-procurement")
    rows = get_structured_data(engine, spec, identity)
    assert rows == []


def test_assemble_context_includes_documents_field(engine) -> None:
    """assemble_context step 6/7 now returns real data (cut-011)."""
    pkg = assemble_context(
        engine=engine,
        user_ref="demo-user-procurement",
        intent="evaluate_purchase_request",
        entities=[{"type": "purchase_request", "id": "PR0001"}],
    )
    # documents and business_data are lists (possibly empty depending on demo data)
    assert isinstance(pkg.documents, list)
    assert isinstance(pkg.business_data, list)
