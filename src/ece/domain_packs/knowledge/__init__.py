"""S1.2 ontology loader for Knowledge Management pack.

Per ece/TASKS.md S1.2:
- ontology.py 三元组校验: relation 不在 ontology 白名单 → 拒绝该条并记录
- 领域包放 src/ece/domain_packs/ (铁律 4: engine 零领域 import)

导出 dict-like object, 无 YAML lib 依赖; 实际配置在 sibling ontology.py 导入时即注册.

cut-043 — register this pack's ontology with `ece.entities.ontology_resolver`
so that `km:*` source_systems are routed to the KM ontology (not procurement's).
This satisfies 铁律 4 (no engine→pack import; the resolver is engine-side,
and the pack's `__init__.py` is the registration site).
"""
# Side-effect: register this pack's ontology with the engine-side resolver.
import ece.entities.ontology_resolver  # noqa: F401

from .ontology import allowed_relations, allowed_targets, is_allowed

__all__ = ["allowed_relations", "allowed_targets", "is_allowed"]
