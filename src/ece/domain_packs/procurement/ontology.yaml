# S1.2 ontology — Procurement 领域包声明的合法关系三元组

# Format: {src_entity_type: [(relation, dst_entity_type), ...]}
# 来源: DATA_MODEL.md §6 entity-relationship 图示例 + PRD §27 Demo Corporation 实体类型

allowed_relations = {
    # ─── Department / Role / User ───
    "person": [
        ("MEMBER_OF", "department"),
        ("HAS_ROLE", "role"),
    ],
    "department": [
        ("BELONGS_TO", "department"),  # hierarchy
    ],
    # ─── Procurement ───
    "purchase_request": [
        ("SUBMITTED_BY", "person"),
        ("BELONGS_TO", "department"),
        ("SELECTS", "supplier"),
        ("CONTAINS", "product"),
        ("REFERENCES", "contract"),
        ("HAS_APPROVAL", "approval"),
        ("SUBJECT_TO", "policy"),
    ],
    "purchase_order": [
        ("FULFILLS", "purchase_request"),
        ("ISSUED_TO", "supplier"),
    ],
    "approval": [
        ("APPROVED_BY", "person"),
    ],
    # ─── Supplier / Contract ───
    "supplier": [
        ("HAS_CONTRACT", "contract"),
    ],
    # ─── Document ───
    "document": [
        ("ATTACHED_TO", "purchase_request"),  # generic attachment
    ],
    # ─── Default fallback ───
    # Unknown (entity_type, relation) → reject per ece/TASKS.md S1.2:
    # "ontology 白名单校验;relation 不在 ontology → 拒绝该条并记录"
}


def is_allowed(src_type: str, relation: str, dst_type: str) -> bool:
    """Return True iff (src_type, relation, dst_type) is in the ontology."""
    if src_type not in allowed_relations:
        return False
    for rel, dst in allowed_relations[src_type]:
        if rel == relation and dst == dst_type:
            return True
    return False


def allowed_targets(src_type: str, relation: str) -> list[str]:
    """Return dst_type list for (src_type, relation), empty if unknown."""
    return [dst for rel, dst in allowed_relations.get(src_type, []) if rel == relation]
