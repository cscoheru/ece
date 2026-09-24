"""OEI-003: Content Engine Port — abstract interface to a content+search engine.

Per OEI-003 task v1 §0 架构红线:ECE 拥有身份/权限/来源/审计/领域对象/工作流;
Onyx (or any other engine) 只是可替换的内容与检索引擎。ECE 的领域层不得
直接 import Onyx 专有内容 — 本目录是 Engine Core 内的 Connector 实现,合规。
"""
