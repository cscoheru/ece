"""S3.2 Context Assembly Pipeline (PRD §29 12 steps, ARCHITECTURE §3).

Order is fixed (per ADR-004 + PRD §29); any step failure → fail-closed.

Steps implemented in cut-007 (S3.2):
  1  Identify user (X-User-Id)
  2  Resolve identity (Person + roles + dept + aliases)
  3  Determine permissions (implicit via check_permission per object)
  4  Resolve requested entities (entities table lookup by display_id)
  5  Retrieve relevant relationships (with permission filter on dst)
  8  Apply temporal constraints (via get_relationships as_of param)
  9  Rank + truncate (per spec.limits.max_entities)
 10  Build Context Package (denied list)
 11  Build sources (via build_sources from items_for_audit)
 12  Return to caller + write context_requests/context_items

Steps STUBBED for cut-008 (Sprint 4 territory):
  6  Retrieve authorized documents (FTS/vector + classification+ACL)
  7  Retrieve structured data (per-spec kinds, row-level permissions)
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ece.api.org import get_user_org
from ece.context.documents import get_documents
from ece.context.provenance import build_sources, record_package
from ece.context.relationships import get_relationships
from ece.context.spec import load_spec
from ece.context.structured_data import get_structured_data
from ece.identity.parser import resolve_identity
from ece.permissions.engine import check_permission


@dataclass
class ContextPackage:
    """Structured Context Package returned to Agent (per ARCHITECTURE §2.2).

    Fields:
      package_id: ctx_<uuid24> for human reference
      request_id: uuid for audit /debugger lookup
      task: {intent, spec_version}
      user: {id, display_id, name, department, roles, is_management}
      entities: [{ref, type, name, attrs, src}]
      relationships: [{from, rel, to, valid, src}]
      documents: [] (stubbed; Sprint 4)
      business_data: [] (stubbed; Sprint 4)
      denied: [{ref, reason}] — anti-probing: existence + reason only
      sources: [{sid, system, record_id}]
      metadata: {generated_at, as_of, counts, insufficient_context?}
    """

    package_id: str
    request_id: str
    task: dict[str, Any]
    user: dict[str, Any]
    entities: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    business_data: list[dict[str, Any]] = field(default_factory=list)
    denied: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "request_id": self.request_id,
            "task": self.task,
            "user": self.user,
            "entities": self.entities,
            "relationships": self.relationships,
            "documents": self.documents,
            "business_data": self.business_data,
            "denied": self.denied,
            "sources": self.sources,
            "metadata": self.metadata,
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_acl_for(engine: Engine, object_ref: str) -> list[dict]:
    """Load acl_entries for a given object_ref (display_id)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT subject_type, subject_ref, effect
                FROM acl_entries
                WHERE object_type = 'entity' AND object_ref = :oref
            """),
            {"oref": object_ref},
        ).fetchall()
    return [
        {
            "subject_type": r[0],
            "subject_ref": r[1],
            "effect": r[2],
            "valid_from": None,
            "valid_to": None,
            "source_system": "test",
        }
        for r in rows
    ]


def assemble_context(
    engine: Engine,
    user_ref: str,
    intent: str,
    entities: list[dict[str, Any]],
    as_of: date | None = None,
    pack: str = "procurement",
) -> ContextPackage:
    """Run the 12-step Context Assembly Pipeline.

    Per ADR-004: fail-closed. Any unexpected error → status='error' returned
    via audit (callers can also catch exceptions and re-call).

    Args:
        engine: SQLAlchemy Engine (DB connection)
        user_ref: X-User-Id value
        intent: spec name (e.g., "evaluate_purchase_request")
        entities: list of {type, id} root entities (empty → insufficient_context)
        as_of: optional temporal anchor (None = current)
        pack: domain pack name (default "procurement")

    Returns:
        ContextPackage with task, user, entities, relationships, denied,
        sources, metadata + audit written to context_requests/context_items.
    """
    request_id = uuid.uuid4()
    package_id = f"ctx_{request_id.hex[:24]}"
    t0 = time.monotonic()

    # Step 1 + 2: Identify user + Resolve identity
    identity = resolve_identity(engine, user_ref)
    user_dict: dict[str, Any] = {
        "id": identity.user_ref,
        "display_id": identity.display_id,
        "name": identity.name,
        "department": identity.department,
        "roles": list(identity.roles),
        "is_management": identity.is_management,
    }

    # Load spec (raises FileNotFoundError if missing)
    spec = load_spec(pack, intent)

    # Step 4: Resolve requested entities (by display_id → entity rows)
    resolved_entities: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    items_for_audit: list[dict[str, Any]] = []
    src_display_ids: list[str] = []

    if not entities:
        # No root entities → insufficient_context per API.md §1
        return _finalize(
            engine=engine,
            package_id=package_id,
            request_id=request_id,
            user_dict=user_dict,
            intent=intent,
            spec_version=spec.version,
            root_entities=entities,
            as_of=as_of,
            resolved_entities=resolved_entities,
            relationships=[],
            denied=denied,
            items_for_audit=items_for_audit,
            t0=t0,
            insufficient=True,
        )

    for ent in entities:
        if not isinstance(ent, dict):
            continue
        ent_id = str(ent.get("id", ""))

        if not ent_id:
            denied.append({"ref": "", "reason": "missing entity.id"})
            items_for_audit.append({
                "kind": "entity", "ref": "", "source": {},
                "decision": "denied", "reason": "missing entity.id",
            })
            continue

        # Look up entity row
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT display_id, entity_type, name, attributes,
                           source_system, source_id
                    FROM entities WHERE display_id = :d
                """),
                {"d": ent_id},
            ).first()

        if row is None:
            denied.append({"ref": ent_id, "reason": "entity not found"})
            items_for_audit.append({
                "kind": "entity", "ref": ent_id, "source": {},
                "decision": "denied", "reason": "entity not found",
            })
            continue

        # Step 3 (implicit): permission check on this entity
        acl_entries = _load_acl_for(engine, ent_id)
        decision = check_permission(
            identity=identity,
            object_type="entity",
            object_ref=ent_id,
            classification="public",
            acl_entries=acl_entries,
        )
        if not decision.allowed:
            denied.append({"ref": ent_id, "reason": f"acl:{decision.matched_rule}"})
            items_for_audit.append({
                "kind": "entity", "ref": ent_id, "source": {},
                "decision": "denied", "reason": f"acl:{decision.matched_rule}",
            })
            continue

        attrs = row[3] if isinstance(row[3], dict) else {}
        resolved_entities.append({
            "ref": row[0],
            "type": row[1],
            "name": row[2],
            "attrs": attrs,
            "src": {"system": row[4] or "", "record_id": row[5] or ""},
        })
        items_for_audit.append({
            "kind": "entity", "ref": row[0],
            "source": {"system": row[4] or "", "record_id": row[5] or ""},
            "decision": "allowed", "reason": "spec:root",
        })
        src_display_ids.append(row[0])

    # Step 5: Retrieve relevant relationships (with permission filter on dst)
    relationships: list[dict[str, Any]] = []
    if spec.requires.relationships and src_display_ids:
        rels = get_relationships(
            engine,
            src_display_ids=src_display_ids,
            relations=spec.requires.relationships or None,
            as_of=as_of,
            max_rows=spec.limits.max_relationships,
        )
        for rel in rels:
            dst_id = rel["to_display_id"]
            dst_acls = _load_acl_for(engine, dst_id)
            decision = check_permission(
                identity=identity,
                object_type="entity",
                object_ref=dst_id,
                classification="public",
                acl_entries=dst_acls,
            )
            if not decision.allowed:
                denied.append({
                    "ref": dst_id,
                    "reason": f"acl:rel_dst:{decision.matched_rule}",
                })
                items_for_audit.append({
                    "kind": "relationship", "ref": dst_id,
                    "source": {"system": rel["source_system"], "record_id": rel["source_ref"]},
                    "decision": "denied", "reason": f"acl:{decision.matched_rule}",
                })
                continue
            relationships.append({
                "from": rel["from_display_id"],
                "rel": rel["relation"],
                "to": rel["to_display_id"],
                "valid": [
                    rel["valid_from"].isoformat() if rel["valid_from"] else None,
                    rel["valid_to"].isoformat() if rel["valid_to"] else None,
                ],
                "src": {
                    "system": rel["source_system"],
                    "record_id": rel["source_ref"],
                },
            })
            items_for_audit.append({
                "kind": "relationship",
                "ref": f"{rel['from_display_id']}-{rel['relation']}->{rel['to_display_id']}",
                "source": {"system": rel["source_system"], "record_id": rel["source_ref"]},
                "decision": "allowed", "reason": "spec:relationship",
            })

    # Step 6: Document retrieval (FTS keyword route; vector deferred to cut-012)
    # Step 7: Structured data (per-spec.kind SQL; per-kind handlers in
    # context/structured_data.py)
    documents = get_documents(engine, spec, identity, as_of=as_of)
    business_data = get_structured_data(engine, spec, identity, as_of=as_of)

    # Step 8 already applied (as_of in get_relationships).
    # Step 9: rank + truncate per spec.limits.
    if len(resolved_entities) > spec.limits.max_entities:
        resolved_entities = resolved_entities[: spec.limits.max_entities]
    if len(relationships) > spec.limits.max_relationships:
        relationships = relationships[: spec.limits.max_relationships]

    # Step 10 + 11: build package + sources
    sources = build_sources(items_for_audit)

    insufficient = len(resolved_entities) == 0

    return _finalize(
        engine=engine,
        package_id=package_id,
        request_id=request_id,
        user_dict=user_dict,
        intent=intent,
        spec_version=spec.version,
        root_entities=entities,
        as_of=as_of,
        resolved_entities=resolved_entities,
        relationships=relationships,
        denied=denied,
        items_for_audit=items_for_audit,
        t0=t0,
        insufficient=insufficient,
        documents=documents,
        business_data=business_data,
        sources=sources,
    )


def _finalize(
    *,
    engine: Engine,
    package_id: str,
    request_id: uuid.UUID,
    user_dict: dict[str, Any],
    intent: str,
    spec_version: int,
    root_entities: list[dict[str, Any]],
    as_of: date | None,
    resolved_entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    denied: list[dict[str, Any]],
    items_for_audit: list[dict[str, Any]],
    t0: float,
    insufficient: bool,
    documents: list[dict[str, Any]] | None = None,
    business_data: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> ContextPackage:
    """Build ContextPackage + write context_requests/context_items (step 11-12)."""
    documents = documents or []
    business_data = business_data or []
    sources = sources if sources is not None else build_sources(items_for_audit)

    pkg = ContextPackage(
        package_id=package_id,
        request_id=str(request_id),
        task={"intent": intent, "spec_version": spec_version},
        user=user_dict,
        entities=resolved_entities,
        relationships=relationships,
        documents=documents,
        business_data=business_data,
        denied=denied,
        sources=sources,
        metadata={
            "generated_at": _now_iso(),
            "as_of": as_of.isoformat() if as_of else None,
            "counts": {
                "entities": len(resolved_entities),
                "relationships": len(relationships),
                "documents": len(documents),
                "rows": len(business_data),
                "denied": len(denied),
            },
            "insufficient_context": insufficient,
        },
    )

    latency_ms = int((time.monotonic() - t0) * 1000)
    root_entities_json = [
        {"type": str(e.get("type", "")), "id": str(e.get("id", ""))}
        for e in root_entities if isinstance(e, dict)
    ]
    record_package(
        engine=engine,
        request_id=request_id,
        user_ref=user_dict["id"],
        intent=intent,
        spec_version=spec_version,
        root_entities=root_entities_json,
        as_of=as_of.isoformat() if as_of else None,
        counts=pkg.metadata["counts"],
        latency_ms=latency_ms,
        items=items_for_audit,
        status="insufficient_context" if insufficient else "ok",
        user_org=get_user_org(user_dict["id"]),
    )

    return pkg
