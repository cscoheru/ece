"""S3.3 Provenance — sources tracking + context_requests/context_items writes.

Per ARCHITECTURE §2.2 (Context Package structure):
  Each item carries source {system, record_id}; sources[] aggregates unique sids.

Per DATA_MODEL §5:
  context_requests: per-call row (user_ref, intent, counts, status, latency).
  context_items: per-included/denied row (request_id, item_kind, ref, source,
                 decision, reason).

sid generation: uuid uuid5 with NAMESPACE_OID derived from
"{system}:{record_id}" — deterministic so re-assembly yields same sid.
"""
from __future__ import annotations

import json
import uuid


def _sid(system: str, record_id: str) -> str:
    """Derive a 4-char hex sid from (system, record_id).

    Uses uuid5(NAMESPACE_OID, ...) for determinism (re-assembly yields same sid).
    Truncated to 4 hex chars for readability (16 bits = 65k unique sources).
    """
    raw = f"{system}:{record_id}"
    return f"s{uuid.uuid5(uuid.NAMESPACE_OID, raw).int & 0xFFFF:04x}"


def build_sources(items: list[dict]) -> list[dict]:
    """Build sources[] from list of items, each with `source: {system, record_id}`.

    Dedupes by (system, record_id); first occurrence wins; sid is stable per source.

    Args:
        items: list of dicts with `source` field (any item missing source is skipped)

    Returns:
        list of {sid, system, record_id}
    """
    seen: dict[tuple[str, str], str] = {}
    sources: list[dict] = []
    for item in items:
        src = item.get("source", {})
        if not isinstance(src, dict):
            continue
        system = str(src.get("system", ""))
        record_id = str(src.get("record_id", ""))
        if not system and not record_id:
            continue
        key = (system, record_id)
        if key in seen:
            continue
        seen[key] = _sid(system, record_id)
        sources.append({"sid": seen[key], "system": system, "record_id": record_id})
    return sources


def record_package(
    engine,
    request_id: uuid.UUID,
    user_ref: str,
    intent: str,
    spec_version: int,
    root_entities: list[dict],
    as_of: str | None,
    counts: dict[str, int],
    latency_ms: int,
    items: list[dict],
    status: str = "ok",
    llm_model: str | None = None,
    user_org: str | None = None,
) -> None:
    """Write context_requests + context_items rows in one transaction.

    Args:
        engine: SQLAlchemy Engine
        request_id: uuid.UUID of this assembly
        user_ref: X-User-Id value (for context_requests.user_ref)
        intent: spec intent name
        spec_version: spec.version
        root_entities: [{type, id}] root entities from caller
        as_of: ISO date string or None
        counts: {entities, relationships, documents, rows, denied}
        latency_ms: assembly wall-clock time in ms
        items: list of {kind, ref, source, decision, reason, score?}
                decision in ('allowed', 'denied')
        status: 'ok' | 'insufficient_context' | 'error'
        llm_model: optional, agent phase may fill later (post-S3)
        user_org: optional org_id (per cut-019 multi-tenant); NULL when
                  ECE_USER_ORGS is unset or user_ref is not in the map.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO context_requests
                    (request_id, user_ref, intent, spec_version,
                     root_entities, as_of, counts, latency_ms, llm_model,
                     status, org_id)
                VALUES (:rid, :user, :intent, :sv,
                        CAST(:root AS jsonb), :as_of,
                        CAST(:counts AS jsonb), :lat, :llm, :status, :org)
            """),
            {
                "rid": str(request_id),
                "user": user_ref,
                "intent": intent,
                "sv": spec_version,
                "root": json.dumps(root_entities, ensure_ascii=False),
                "as_of": as_of,
                "counts": json.dumps(counts, ensure_ascii=False),
                "lat": latency_ms,
                "llm": llm_model,
                "status": status,
                "org": user_org,
            },
        )
        for seq, item in enumerate(items):
            conn.execute(
                text("""
                    INSERT INTO context_items
                        (request_id, seq, item_kind, ref, source,
                         decision, reason, score)
                    VALUES (:rid, :seq, :kind, :ref, CAST(:src AS jsonb),
                            :dec, :reason, :score)
                """),
                {
                    "rid": str(request_id),
                    "seq": seq,
                    "kind": str(item.get("kind", "entity")),
                    "ref": str(item.get("ref", "")),
                    "src": json.dumps(item.get("source", {}), ensure_ascii=False),
                    "dec": str(item.get("decision", "allowed")),
                    "reason": str(item.get("reason", "")),
                    "score": item.get("score"),
                },
            )
