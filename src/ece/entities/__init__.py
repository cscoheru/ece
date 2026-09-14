# S1.2 entities package -- entity resolver + pipeline

# Pipeline is the main ingestion surface; resolver is a future Sprint 2 component.
# Per ece/TASKS.md S1.2: 渐进流水线 6 级 (exact -> normalized -> alias -> rule -> embedding -> LLM);
# v0 S1.2 only ships stages 1-2 (exact + normalized via display_id UNIQUE),
# subsequent stages add as separate modules.

from .pipeline import EntityInsertResult, upsert_entity, upsert_relationship

__all__ = ["EntityInsertResult", "upsert_entity", "upsert_relationship"]
