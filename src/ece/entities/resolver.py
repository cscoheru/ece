"""S2.3 Entity Resolution: 6-level progressive pipeline.

Per ece/TASKS.md S2.3 + ARCHITECTURE.md 6:
  exact(source_id) -> normalized_name -> alias table -> rule
  -> embedding similarity (>=0.92) -> LLM candidate

v0 S2.3 ships stages 1-3 (exact + normalized + alias table).
embedding + LLM stages deferred to later (depends on external model).

Per cut-005 §7.4: ambiguity example must return resolved:false (not guess).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ResolutionMethod(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    ALIAS = "alias"
    RULE = "rule"
    EMBEDDING = "embedding"
    LLM = "llm"


@dataclass
class ResolutionResult:
    """Per-mention resolution outcome."""

    mention: str
    candidates: list[dict]  # [{entity: display_id, name, method, confidence}, ...]
    resolved: bool
    chosen: str | None = None  # display_id, set only when resolved=True with 1 candidate
    method: ResolutionMethod | None = None


def resolve_mention(engine: Engine, mention: str, type_hint: str | None = None) -> ResolutionResult:
    """Resolve a free-text mention against the entity store.

    6-level pipeline (v0 stages 1-3):
      1. exact (source_id match)
      2. normalized (name or normalized_name lower/trim match)
      3. alias (entity_aliases alias match)
      4. rule (heuristics; e.g. "无限极" -> "无限极(中国)有限公司"; v0 stub: same as normalized)
      5. embedding (semantic similarity >= 0.92; deferred to embedding model)
      6. LLM candidate (LLM only produces candidates; never resolves directly)

    Ambiguity rule (per cut-005): if multiple candidates match, return
    resolved=False and let caller disambiguate. Never guess.
    """
    candidates: list[dict] = []

    # Stage 1: exact (source_id match)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT display_id, name, source_id, 1.0 AS confidence
                FROM entities
                WHERE source_id = :m
                LIMIT 5
            """),
            {"m": mention},
        ).fetchall()
    for r in rows:
        candidates.append({
            "entity": r[0],
            "name": r[1],
            "source_id": r[2],
            "method": ResolutionMethod.EXACT,
            "confidence": float(r[3]),
        })

    if len(candidates) == 1:
        return ResolutionResult(
            mention=mention, candidates=candidates, resolved=True,
            chosen=candidates[0]["entity"], method=ResolutionMethod.EXACT,
        )

    # Stage 2: normalized name (case-insensitive trim)
    if not candidates:
        norm = mention.lower().strip()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT display_id, name, source_id, 0.95 AS confidence
                    FROM entities
                    WHERE LOWER(TRIM(normalized_name)) = :n
                       OR LOWER(TRIM(name)) = :n
                    LIMIT 10
                """),
                {"n": norm},
            ).fetchall()
        for r in rows:
            candidates.append({
                "entity": r[0],
                "name": r[1],
                "source_id": r[2],
                "method": ResolutionMethod.NORMALIZED,
                "confidence": float(r[3]),
            })

    # Stage 3: alias table
    if not candidates:
        norm = mention.lower().strip()
        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT e.display_id, e.name, e.source_id, 0.85 AS confidence
                    FROM entity_aliases ea
                    JOIN entities e ON ea.entity_id = e.id
                    WHERE LOWER(TRIM(ea.norm_alias)) = :n
                    LIMIT 10
                """),
                {"n": norm},
            ).fetchall()
        for r in rows:
            candidates.append({
                "entity": r[0],
                "name": r[1],
                "source_id": r[2],
                "method": ResolutionMethod.ALIAS,
                "confidence": float(r[3]),
            })

    # Stage 4-6: deferred (embedding / LLM) for later Sprints.

    # Decision
    if len(candidates) == 1:
        return ResolutionResult(
            mention=mention, candidates=candidates, resolved=True,
            chosen=candidates[0]["entity"], method=candidates[0]["method"],
        )
    if len(candidates) > 1:
        # Ambiguity: never guess. Per cut-005 §7.4 R5 / ADR-004 'fail-closed'.
        return ResolutionResult(
            mention=mention, candidates=candidates, resolved=False,
        )
    # Zero candidates
    return ResolutionResult(mention=mention, candidates=[], resolved=False)
