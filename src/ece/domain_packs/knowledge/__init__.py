"""S1.2 ontology loader for Knowledge Management pack.

Per ece/TASKS.md S1.2:
- ontology.py 三元组校验: relation 不在 ontology 白名单 → 拒绝该条并记录
- 领域包放 src/ece/domain_packs/ (铁律 4: engine 零领域 import)

导出 dict-like object, 无 YAML lib 依赖; 实际配置在 sibling ontology.py 导入时即注册.

cut-043R R5-B3 — INVERTED registration. Pack side imports the resolver and
registers itself for the `km` source-system prefix. The resolver does NOT
import this module (that would re-introduce the isolation violation).
"""
# Self-register with the engine-side resolver. This import direction is the
# only one allowed: pack → resolver (engine). Never the reverse.
from ece.entities.ontology_resolver import register_ontology_for_system

from .ontology import allowed_relations, allowed_targets, is_allowed

register_ontology_for_system(
    "km",  # covers source_system="km:v0-knowledge-fixture"
    is_allowed_fn=is_allowed,
    allowed_targets_fn=allowed_targets,
)

__all__ = ["allowed_relations", "allowed_targets", "is_allowed"]
