# S1.2 ontology loader -- reads domain pack ontology.py and exposes is_allowed().

# Per ece/TASKS.md S1.2:
# - ontology.py 三元组校验:relation 不在 ontology 白名单 -> 拒绝该条并记录
# - 领域包放 src/ece/domain_packs/(铁律 4: engine 零领域 import)
#
# 该模块故意"导出一个 dict-like object",无 YAML lib 依赖(避免 dev-deps 膨胀);
# 实际配置在 sibling __init__.py.导入时即注册.

# cut-043R R5-B3 — INVERTED registration. Pack side imports the resolver and
# registers itself; the resolver NEVER imports this module. This is the only
# direction that satisfies 铁律 4 (engine 零领域 import).
from ece.entities.ontology_resolver import register_ontology_for_system

from .ontology import allowed_relations, allowed_targets, is_allowed

register_ontology_for_system(
    "spike",  # covers source_system="spike:v0-technical-fixture"
    is_allowed_fn=is_allowed,
    allowed_targets_fn=allowed_targets,
)
register_ontology_for_system(
    "demo",  # covers source_system="demo:demo-fixture" if used by any scenario
    is_allowed_fn=is_allowed,
    allowed_targets_fn=allowed_targets,
)

__all__ = ["allowed_relations", "allowed_targets", "is_allowed"]
