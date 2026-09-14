# S1.2 domain_packs 包 marker -- import-linter 双向隔离契约需要此目录存在

# Per ADR-010 (root仓) / ECE ADR-010 (ece仓):
# src/ece/** 不得 import src/ece/domain_packs/** (Engine core isolation)
# src/ece/domain_packs/** 不得 import src/ece/** (Domain pack isolation)
#
# Sprint 1 起逐 Sprint 填充 procurement / audit 等领域包内容;
# 当前 S1.2 仅 procurement/ontology.yaml 白名单.

__all__ = []
