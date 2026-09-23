"""KC-001 — ConsultingCatalog service layer.

File-backed in-memory catalog. The catalog is loaded once from
``seed/consulting_objects.json`` at module import time and exposed as a
singleton via ``default_catalog()``. Filtering / search / facet aggregation
are pure functions over the in-memory list — no DB, no LLM, no embedding.

Design notes:
- Facets are always computed against the FULL corpus (not narrowed by the
  current filter). This is plan §8.1: facet search UX requires showing
  all possible choices so the user can switch filters without reloading.
- Sort by ``relevance``: items where ``q`` matches more text fields float
  up; ties broken by ``id`` (stable). Without ``q`` the default is also
  stable by id, which is what the SPA expects on first load.
- Source discipline (PRD §4.2): synthetic_variant MUST carry
  ``confidence="synthetic"``. The seed bundle is expected to obey this;
  ``KnowledgeObject`` itself does not enforce it (kept permissive so a
  human editor can fix a single mis-tagged record) but the discipline
  test in ``tests/unit/test_consulting_seed_discipline.py`` enforces it.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from ece.consulting.models import (
    FacetsResponse,
    KnowledgeObject,
    LibraryResponse,
)

# ---------------------------------------------------------------------------
# Path resolution — works both in src-tree (dev) and installed package.
# ---------------------------------------------------------------------------

_DEFAULT_SEED_PATH = Path(__file__).resolve().parent / "seed" / "consulting_objects.json"


# ---------------------------------------------------------------------------
# Facet axes — keys are stable strings used both by the JSON response and
# by tests / SPA code. DO NOT rename without bumping the API contract.
# ---------------------------------------------------------------------------

_FACET_KEYS: tuple[str, ...] = (
    "types",
    "practices",
    "engagement_phases",
    "client_industries",
    "problem_types",
    "source_origins",
)


# Map facet key → KnowledgeObject field name. Each is a list-valued field.
_FACET_FIELD_MAP: dict[str, str] = {
    "types": "type",                # type is a single-value field, treated as 1-element list
    "practices": "practice",
    "engagement_phases": "engagement_phase",
    "client_industries": "client_industry",
    "problem_types": "problem_types",
    "source_origins": "source_origin",
}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class ConsultingCatalog:
    """File-backed consulting knowledge catalog."""

    def __init__(self, objects: list[KnowledgeObject]) -> None:
        self._objects: list[KnowledgeObject] = list(objects)
        self._index: dict[str, KnowledgeObject] = {o.id: o for o in self._objects}

    # ----- factory --------------------------------------------------------

    @classmethod
    def from_seed_path(cls, path: Path | None = None) -> ConsultingCatalog:
        """Load a catalog from a JSON seed file (defaults to bundled seed)."""
        seed = path or _DEFAULT_SEED_PATH
        raw = json.loads(seed.read_text(encoding="utf-8"))
        objects = [KnowledgeObject(**item) for item in raw]
        return cls(objects)

    # ----- read accessors -------------------------------------------------

    @property
    def objects(self) -> tuple[KnowledgeObject, ...]:
        """Return all objects (read-only tuple view)."""
        return tuple(self._objects)

    def get(self, object_id: str) -> KnowledgeObject | None:
        """Return a single object by id, or None if not found."""
        return self._index.get(object_id)

    def facets(self) -> FacetsResponse:
        """Return full-set facets (independent of any current filter)."""
        return FacetsResponse(facets=self._compute_facets(), total=len(self._objects))

    # ----- search ---------------------------------------------------------

    def search(
        self,
        q: str | None = None,
        type: str | None = None,
        practice: Iterable[str] | None = None,
        engagement_phase: Iterable[str] | None = None,
        client_industry: Iterable[str] | None = None,
        problem_type: Iterable[str] | None = None,
        source_origin: str | None = None,
        review_state: str | None = None,
        sort: str = "relevance",
        limit: int = 24,
        offset: int = 0,
    ) -> LibraryResponse:
        """Run filter + search + sort + paginate and return a LibraryResponse.

        Facets in the response are ALWAYS the full corpus (see plan §8.1).
        """
        items = list(self._objects)
        items = self._apply_filters(
            items,
            q=q,
            type=type,
            practice=list(practice or []),
            engagement_phase=list(engagement_phase or []),
            client_industry=list(client_industry or []),
            problem_type=list(problem_type or []),
            source_origin=source_origin,
            review_state=review_state,
        )
        items = self._apply_sort(items, q=q, sort=sort)

        total = len(items)
        # Defensive clamping — caller may request beyond end
        limit = max(0, limit)
        offset = max(0, offset)
        page = items[offset : offset + limit]

        return LibraryResponse(
            items=page,
            total=total,
            limit=limit,
            offset=offset,
            facets=self._compute_facets(),
        )

    # ----- internal helpers -----------------------------------------------

    @staticmethod
    def _matches_q(obj: KnowledgeObject, q_lower: str) -> bool:
        """Return True if any free-text field contains q (case-insensitive)."""
        if not q_lower:
            return False
        haystack = " ".join(
            [
                obj.title,
                obj.summary,
                " ".join(obj.methods),
                " ".join(obj.problem_types),
                " ".join(obj.deliverables),
            ]
        ).lower()
        return q_lower in haystack

    def _apply_filters(
        self,
        items: list[KnowledgeObject],
        *,
        q: str | None,
        type: str | None,
        practice: list[str],
        engagement_phase: list[str],
        client_industry: list[str],
        problem_type: list[str],
        source_origin: str | None,
        review_state: str | None,
    ) -> list[KnowledgeObject]:
        q_lower = (q or "").strip().lower()

        def keep(obj: KnowledgeObject) -> bool:
            if type and obj.type != type:
                return False
            if source_origin and obj.source_origin != source_origin:
                return False
            if review_state and obj.review_state != review_state:
                return False
            if practice and not (set(practice) & set(obj.practice)):
                return False
            if engagement_phase and not (set(engagement_phase) & set(obj.engagement_phase)):
                return False
            if client_industry and not (set(client_industry) & set(obj.client_industry)):
                return False
            if problem_type and not (set(problem_type) & set(obj.problem_types)):
                return False
            if q_lower and not self._matches_q(obj, q_lower):  # noqa: SIM103
                return False
            return True

        return [o for o in items if keep(o)]

    @staticmethod
    def _apply_sort(
        items: list[KnowledgeObject], *, q: str | None, sort: str
    ) -> list[KnowledgeObject]:
        if sort == "title":
            return sorted(items, key=lambda o: o.id)
        # default / relevance:
        # - If q is provided: score = number of times q appears across
        #   title/summary/methods/problem_types/deliverables (case-insensitive);
        #   ties broken by id (stable). Items with q absent are dropped
        #   (already filtered out by _apply_filters).
        # - If q is absent: stable id order.
        if not (q or "").strip():
            return sorted(items, key=lambda o: o.id)

        q_lower = (q or "").strip().lower()

        def score(obj: KnowledgeObject) -> tuple[int, str]:
            haystack = " ".join(
                [
                    obj.title,
                    obj.summary,
                    " ".join(obj.methods),
                    " ".join(obj.problem_types),
                    " ".join(obj.deliverables),
                ]
            ).lower()
            # Negative so higher match counts sort first when ascending; we
            # invert the negation by using (-count, id).
            count = haystack.count(q_lower)
            return (-count, obj.id)

        return sorted(items, key=score)

    def _compute_facets(self) -> dict[str, list[str]]:
        """Aggregate full-corpus facet values, sorted + de-duplicated."""
        out: dict[str, list[str]] = {}
        for facet_key in _FACET_KEYS:
            field = _FACET_FIELD_MAP[facet_key]
            values: set[str] = set()
            for o in self._objects:
                if field == "type":
                    values.add(o.type)
                elif field == "source_origin":
                    values.add(o.source_origin)
                else:
                    values.update(getattr(o, field))
            out[facet_key] = sorted(values)
        return out


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


_DEFAULT_CATALOG: ConsultingCatalog | None = None


def default_catalog() -> ConsultingCatalog:
    """Return the process-wide singleton catalog (loaded from bundled seed)."""
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = ConsultingCatalog.from_seed_path()
    return _DEFAULT_CATALOG


__all__ = ["ConsultingCatalog", "default_catalog", "_FACET_KEYS"]
