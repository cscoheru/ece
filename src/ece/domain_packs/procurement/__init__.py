# S1.2 ontology loader -- reads domain pack ontology.yaml and exposes is_allowed().

# Per ece/TASKS.md S1.2:
# - ontology.yaml 三元组校验:relation 不在 ontology 白名单 -> 拒绝该条并记录
# - 领域包放 src/ece/domain_packs/(铁律 4: engine 零领域 import)
#
# 该模块故意"导出一个 dict-like object",无 YAML lib 依赖(避免 dev-deps 膨胀);
# 实际配置在 sibling __init__.py.导入时即注册.

from .ontology import allowed_relations, allowed_targets, is_allowed

__all__ = ["allowed_relations", "allowed_targets", "is_allowed"]
