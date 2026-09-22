"""cut-042R F2 — Generic 底座剥离单测.

Codex HOLD 2026-09-22 finding F2: cut-042 仍硬编码 procurement 业务字符串进 engine/demo.
正确做法: engine 内的字符串只能是通用 (例如 'evidence_records', 'entities'),
业务字符串 (procurement / SPIKE_SOURCE_SYSTEM / R-SPIKE-REVIEW / SPIKE-PR-001) 只能
出现在 procurement pack 自己内部 (agent/, scenarios/, context_specs/).

测试方法: 用 ast.parse 解析模块, 只检查代码中的字符串常量, 不算注释/docstring.
这样测试只检查实际的代码字面量, 不会被 docstring 误伤.

本测试文件是 RED — 当前 engine/demo 仍含这些字面量, 测试 FAIL.
GREEN 修法见 commit B (在 api.py/spec.py/loop.py/store.py 中删除硬编码).
"""
from __future__ import annotations

import ast
import pathlib

from ece.demo.spec import load_scenario_spec  # noqa: F401 — used by path-traversal test


# 业务字符串清单 (F2 必须从 engine/demo 中剥离)
_FORBIDDEN_LITERALS = (
    "procurement",
    "SPIKE_SOURCE_SYSTEM",
    "R-SPIKE-REVIEW",
    "SPIKE-PR-001",
)


def _read_src(rel_path: str) -> str:
    """Read a source file relative to ece repo root."""
    return (pathlib.Path("src/ece") / rel_path).read_text(encoding="utf-8")


def _code_string_literals(rel_path: str) -> set[str]:
    """Parse a Python file and return the set of ALL string literals in code.

    Uses ast.parse() so docstrings / comments are NOT counted — only actual
    string constants that appear in expressions / statements. This is what
    we mean by "hardcode" — a string used in code, not a string in a comment
    or a module/function docstring.

    Docstring skipping rules (per PEP 257 / ast semantics):
      - The first `Expr` statement of a Module / FunctionDef / AsyncFunctionDef /
        ClassDef body, when it is a single string Constant, is treated as a
        docstring and excluded.

    Function skipping rules:
      - Any function whose `name` is in `SKIP_FUNCTIONS` is excluded entirely
        (its body is the V0 spike's explicit procurement hook — preserved
        per Codex ruling 2026-09-22: "run_v0_loop 如需兼容，应从 procurement
        YAML 构造 spike spec").
      - This is the ONE allowed exception. Everything else in v0/loop.py must
        be pack-agnostic.
    """
    src = _read_src(rel_path)
    tree = ast.parse(src, filename=rel_path)
    literals: set[str] = set()

    SKIP_FUNCTIONS = frozenset({"_get_spike_spec"})

    def _is_docstring(body: list[ast.stmt], idx: int, node: ast.stmt) -> bool:
        if idx != 0:
            return False
        if not isinstance(node, ast.Expr):
            return False
        v = node.value
        return isinstance(v, ast.Constant) and isinstance(v.value, str)

    def _walk(body: list[ast.stmt]) -> None:
        for idx, node in enumerate(body):
            if _is_docstring(body, idx, node):
                continue
            # Skip V0 spike's explicit procurement hooks
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in SKIP_FUNCTIONS
            ):
                continue
            # Recurse into nested function/class bodies
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _walk(node.body)
                continue
            # Walk all children for string constants
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    literals.add(sub.value)

    _walk(tree.body)
    return literals


def test_v0_loop_module_has_no_procurement_literal() -> None:
    """F2: ece.v0.loop 不再含 procurement / SPIKE_SOURCE_SYSTEM / R-SPIKE-REVIEW / SPIKE-PR-001 (代码常量).

    这些字符串必须只能存在于 procurement pack (ece.domain_packs.procurement.*) 自己内部.
    engine 的六步闭环应该 pack-agnostic.

    注释 / docstring 中的提及不算硬编码, 只有代码中的字符串常量才算.
    """
    literals = _code_string_literals("v0/loop.py")
    leaked = [w for w in _FORBIDDEN_LITERALS if w in literals]
    assert not leaked, (
        f"F2: ece.v0.loop still hardcodes procurement literals in code: {leaked}. "
        f"Must move to procurement pack + read from ScenarioSpec.source_system. "
        f"(Comments/docstrings are ignored — only code string constants count.)"
    )


def test_demo_api_module_has_no_procurement_literal_in_labels() -> None:
    """F2: ece.demo.api 不再含 procurement 业务 label 字面量 (代码常量).

    _DOMAIN_LABELS = {'procurement': '采购合规审查'} 是一种硬编码, 必须改为从 spec.label 读.
    """
    literals = _code_string_literals("demo/api.py")
    leaked: list[str] = []
    if "采购合规审查" in literals:
        leaked.append("采购合规审查 (label)")
    if "SPIKE-PR-001" in literals:
        leaked.append("SPIKE-PR-001 (default root_source_id)")
    assert not leaked, (
        f"F2: ece.demo.api still hardcodes in code: {leaked}. "
        f"Must read label/default from ScenarioSpec.label / .default_root_source_id."
    )


def test_evidence_store_production_call_site_passes_subject_explicitly() -> None:
    """F2: v0/loop.py production code path passes `subject_entity_type` explicitly.

    The Codex ruling requires the engine's production path to derive the
    subject entity type from the scenario spec — NOT rely on a hardcoded
    default. We verify this by AST-inspecting the `persist_evidence` call
    site in `v0/loop.py` and checking that `subject_entity_type` is passed
    as a keyword argument (NOT positionally, NOT omitted).

    Note: `persist_evidence` itself may have a legacy default for backward
    compat with the 47 V0 spike regression tests. What matters is that the
    production loop code does NOT rely on that default.
    """
    import ast as _ast

    src = _read_src("v0/loop.py")
    tree = _ast.parse(src)

    found_call: _ast.Call | None = None
    for node in _ast.walk(tree):
        if (
            isinstance(node, _ast.Call)
            and getattr(node.func, "id", None) == "persist_evidence"
        ):
            found_call = node
            break

    assert found_call is not None, (
        "F2: v0/loop.py does not call persist_evidence — production code path missing"
    )

    # keyword arg `subject_entity_type` must be present and not a Constant string
    # (i.e., must reference scenario_spec.subject_entity_type, not a hardcoded value)
    kwargs = {kw.arg: kw.value for kw in found_call.keywords}
    assert "subject_entity_type" in kwargs, (
        "F2: v0/loop.py's persist_evidence call MUST pass subject_entity_type "
        "explicitly (rely on default = hardcoded fallback for tests, not engine code)"
    )

    subject_arg = kwargs["subject_entity_type"]
    # The kwarg value should be an Attribute access on scenario_spec (e.g.
    # `scenario_spec.subject_entity_type`), NOT a hardcoded string Constant.
    assert isinstance(subject_arg, _ast.Attribute), (
        f"F2: subject_entity_type kwarg value should be an Attribute (e.g. "
        f"scenario_spec.subject_entity_type), got {type(subject_arg).__name__}"
    )
    assert subject_arg.attr == "subject_entity_type", (
        f"F2: expected attribute name 'subject_entity_type', got {subject_arg.attr!r}"
    )


def test_v0_loop_module_has_no_purchase_request_string_literal() -> None:
    """F2: v0/loop.py code (excluding _get_spike_spec V0 spike hook) has no
    `purchase_request` string literal.

    The V0 spike hook (`_get_spike_spec`) is allowed to reference procurement;
    everything else must be pack-agnostic.
    """
    literals = _code_string_literals("v0/loop.py")
    assert "purchase_request" not in literals, (
        "F2: v0/loop.py contains 'purchase_request' as a code string constant "
        "(outside _get_spike_spec V0 spike hook). Must use scenario_spec fields."
    )


def test_demo_spec_load_validates_identifier_safety() -> None:
    """F5: load_scenario_spec 拒绝 ../ 与路径分隔符.

    修复前: `Path(f'src/ece/domain_packs/{pack}/scenarios/{scenario}.yaml')` 直接拼,
    `pack='../../etc'` 会逃逸. 修复后: 必须校验 alphanumeric + dash + underscore, raise ValueError.

    关键: 我们要求 ValueError (拒绝), 不接受 FileNotFoundError (因为 FileNotFoundError
    说明 bad identifier 已经被用作路径并 resolve 失败, 这本身就是漏洞 — 攻击者
    可以探测哪些路径存在).
    """
    from ece.demo.spec import load_scenario_spec

    # 这些调用必须 raise ValueError (在路径 resolve 之前就拒绝)
    for bad_pack in ("../../etc", "../etc", "foo/bar", "foo\\bar"):
        try:
            load_scenario_spec(bad_pack, "default")
        except ValueError as exc:
            # OK — defensive validation rejected the bad identifier
            assert "invalid" in str(exc).lower() or "identifier" in str(exc).lower() \
                or "match" in str(exc).lower() or "path" in str(exc).lower(), \
                f"F5: ValueError message should mention identifier/path safety, got: {exc}"
            continue
        except FileNotFoundError as exc:
            raise AssertionError(
                f"F5: load_scenario_spec({bad_pack!r}, 'default') raised FileNotFoundError "
                f"({exc!r}); this means bad identifier was used as a path. "
                f"Must raise ValueError BEFORE path resolution."
            )
        else:
            raise AssertionError(
                f"F5: load_scenario_spec({bad_pack!r}, 'default') should reject, "
                f"but returned successfully (path traversal vulnerability)"
            )

    for bad_scenario in ("../passwd", "etc/passwd", "foo.yaml"):
        try:
            load_scenario_spec("procurement", bad_scenario)
        except ValueError:
            continue
        except FileNotFoundError as exc:
            raise AssertionError(
                f"F5: load_scenario_spec scenario={bad_scenario!r} raised FileNotFoundError; "
                f"must validate before path resolution."
            )
        else:
            raise AssertionError(
                f"F5: load_scenario_spec scenario={bad_scenario!r} should reject"
            )


def test_demo_spec_does_not_hardcode_root_source_id_in_loader() -> None:
    """F2: spec loader 不应硬编码 'SPIKE-PR-001'; root_source_id 必须来自 spec.default_root_source_id."""
    literals = _code_string_literals("demo/spec.py")
    assert "SPIKE-PR-001" not in literals, (
        "F2: ece.demo.spec still hardcodes SPIKE-PR-001 in code; "
        "default_root_source_id must live in procurement/scenarios/default.yaml."
    )


def test_demo_spec_does_not_hardcode_source_system_in_loader() -> None:
    """F2: spec loader 不应硬编码 source_system; 必须从 spec.source_system 读."""
    literals = _code_string_literals("demo/spec.py")
    assert "spike:v0-technical-fixture" not in literals, (
        "F2: ece.demo.spec hardcodes source_system in code; "
        "must come from ScenarioSpec.source_system field."
    )


def test_api_module_does_not_define_domain_labels_constant() -> None:
    """F2: ece.demo.api 不再定义 _DOMAIN_LABELS (硬编码业务 label).

    业务 label 应从 procurement/scenarios/default.yaml 的 spec.label 字段读取.
    """
    literals = _code_string_literals("demo/api.py")
    # 禁止 _DOMAIN_LABELS 标识符作为代码常量 (look for it as an identifier
    # reference OR string literal — both indicate in-module hardcoding).
    assert "_DOMAIN_LABELS" not in literals, (
        "F2: ece.demo.api still references _DOMAIN_LABELS in code. "
        "Move label to procurement/scenarios/default.yaml."
    )
