# S1.2 ontology — Compliance 领域包声明的合法关系三元组
#
# Format: {src_entity_type: [(relation, dst_entity_type), ...]}
# 来源: PRD §6 row 3 企业合规 — 控制项 / 系统
#
# cut-044 设计决策: evidence_packages 内嵌在 control.attrs.evidence_packages
# (而非独立 entity + 关系), 因为 R-COMP-AUDIT 的语义是 "一个 root control 下聚合
# N 个证据包", 不存在跨 control 共享或独立查询需求. 因此 ontology 只声明
# control -REQUIRES_SYSTEM-> system 这一个出边.

allowed_relations = {
    # ─── Compliance ───
    "control": [
        ("REQUIRES_SYSTEM", "system"),
    ],
    "system": [],
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
