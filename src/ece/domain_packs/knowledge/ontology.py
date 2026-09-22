# S1.2 ontology — Knowledge Management 领域包声明的合法关系三元组

# Format: {src_entity_type: [(relation, dst_entity_type), ...]}
# 来源: PRD §6 row 2 知识管理 — 政策文档 / 员工 / 角色 / 制度引用链

allowed_relations = {
    # ─── Knowledge Management ───
    "policy_document": [
        ("REQUIRES_ROLE", "role"),
        ("REFERENCES", "policy_document"),  # 引用链（同类型自引用）
        ("OWNS", "department"),  # 制度归口部门
    ],
    "person": [
        ("HAS_ROLE", "role"),
        ("BELONGS_TO", "department"),
    ],
    "department": [
        ("BELONGS_TO", "department"),
    ],
    # ─── Default fallback ───
    # Unknown (entity_type, relation) → reject per S1.2
}


def is_allowed(src_type: str, relation: str, dst_type: str) -> bool:
    """Return True iff (src_type, relation, dst_type) is in the ontology."""
    if src_type not in allowed_relations:
        return False
    return any(rel == relation and dst == dst_type for rel, dst in allowed_relations[src_type])


def allowed_targets(src_type: str, relation: str) -> list[str]:
    """Return dst_type list for (src_type, relation), empty if unknown."""
    return [dst for rel, dst in allowed_relations.get(src_type, []) if rel == relation]
