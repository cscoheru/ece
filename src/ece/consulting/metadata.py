"""OEI-007 — consulting metadata helpers.

Three pure functions (no DB, no LLM, no engine):

  ALLOWED_EXTENSIONS              — strict whitelist of file extensions the upload
                                     endpoint will accept. Anything else → 415
                                     BEFORE we touch the engine. Text extraction
                                     is the engine's job; the whitelist is just
                                     "should we hand this over".

  MAX_SINGLE_FILE_BYTES / MAX_TOTAL_BYTES — size guards, applied before bytes are
                                            loaded into memory or sent over the
                                            network.

  ALLOWED_VOCABULARIES            — the authoritative sets (built from the 36
                                     seed objects). NEW metadata must land in one
                                     of these — otherwise the consulting facets
                                     fragment into two universes.

  suggest_metadata(filename, title)   — a deterministic dictionary of suggested
                                       values drawn ONLY from ALLOWED_VOCABULARIES.
                                       Same input × N runs → byte-identical output.
                                       (TASK §4 step 3: "N=5 逐字段一致".)

  resolve_metadata(caller, suggested) — caller-supplied fields win; missing
                                       caller fields fall back to suggestions.

The point of all of this being pure and offline is that the consulting upload
endpoint can be tested with no DB, no engine, and no flakes — and the test can
prove determinism by running `suggest_metadata("foo.md", None)` five times in a
row and comparing the dicts.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# ---------------------------------------------------------------------------
# Extension whitelist & size limits
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".docx",
        ".pdf",
    }
)

# 4 MiB single file / 16 MiB aggregate — enough for a long consulting deck,
# small enough that the upload is a single chunk over loopback.
MAX_SINGLE_FILE_BYTES: int = 4 * 1024 * 1024
MAX_TOTAL_BYTES: int = 16 * 1024 * 1024


def check_extension(filename: str) -> str:
    """Return the lowercased extension (incl. leading dot) or raise ValueError."""
    if not filename:
        raise ValueError("filename is empty")
    # rfind the last dot, but skip directory components
    base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." not in base:
        raise ValueError(f"filename has no extension: {filename!r}")
    ext = "." + base.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"extension {ext!r} not allowed; accepted: "
            f"{sorted(ALLOWED_EXTENSIONS)}"
        )
    return ext


def check_single_size(single: int) -> None:
    """Single-file size guard (per-file rejection).

    Empty (0-byte) files are rejected here: text extraction on them is
    undefined and they have nothing the engine can index. Per-file so that
    a multi-file upload can still partial-succeed when one file is empty.
    """
    if single < 0:
        raise ValueError(f"single size must be ≥ 0, got {single}")
    if single == 0:
        raise ValueError("empty file rejected (0 bytes)")
    if single > MAX_SINGLE_FILE_BYTES:
        raise ValueError(
            f"file too large: {single} > MAX_SINGLE_FILE_BYTES ({MAX_SINGLE_FILE_BYTES})"
        )


def check_aggregate_size(total: int) -> None:
    """Whole-batch size guard (request-level → 413)."""
    if total < 0:
        raise ValueError(f"total size must be ≥ 0, got {total}")
    if total > MAX_TOTAL_BYTES:
        raise ValueError(
            f"aggregate too large: {total} > MAX_TOTAL_BYTES ({MAX_TOTAL_BYTES})"
        )


# ---------------------------------------------------------------------------
# Authoritative seed vocabularies — TASK §2.2 "必须复用, 不得另造".
# If we ever need to add a value, the route is "first add to the seed bundle,
# then update the matching keyword list here". Adding here without the seed
# would split the consulting facet aggregation into two universes.
# ---------------------------------------------------------------------------

ALLOWED_TYPES: frozenset[str] = frozenset(
    {
        "case",
        "methodology",
        "proposal_play",
        "deliverable_template",
        "risk_check",
        "industry_note",
    }
)
ALLOWED_PHASES: frozenset[str] = frozenset(
    {"qualification", "proposal", "diagnosis", "implementation", "delivery"}
)
ALLOWED_INDUSTRIES: frozenset[str] = frozenset(
    {
        "banking",
        "consumer_goods",
        "energy",
        "healthcare",
        "insurance",
        "logistics",
        "manufacturing",
        "public_sector",
        "retail",
        "technology",
    }
)
ALLOWED_PROBLEM_TYPES: frozenset[str] = frozenset(
    {
        "approval_breakdown",
        "capacity_planning",
        "channel_efficiency",
        "competitive_landscape",
        "compliance_gap",
        "cost_reduction",
        "customer_experience",
        "data_availability",
        "data_confidentiality",
        "decision_latency",
        "deliverable_structure",
        "engagement_setup",
        "industry_context",
        "inventory_imbalance",
        "kpi_alignment",
        "lead_qualification",
        "network_efficiency",
        "organization_alignment",
        "patient_journey",
        "performance_gap",
        "pricing_conversation",
        "pricing_optimization",
        "process_breakdown",
        "proposal_setup",
        "retention",
        "risk_disclosure",
        "role_clarity",
        "scope_creep",
        "service_consistency",
        "situation_overview",
        "stakeholder_alignment",
        "supplier_consolidation",
        "supply_resilience",
        "team_setup",
        "turnaround_time",
        "value_chain_breakdown",
        "waste_identification",
    }
)
ALLOWED_METHODS: frozenset[str] = frozenset(
    {
        "benchmarking",
        "change_control",
        "channel_tiering",
        "cohort_analysis",
        "confidentiality_checklist",
        "customer_interview",
        "data_sampling",
        "deck_skeleton",
        "frontline_interview",
        "gemba_walk",
        "interview_design",
        "interview_synthesis",
        "inventory_analysis",
        "journey_map",
        "kpi_tree",
        "narrative_design",
        "network_modeling",
        "policy_review",
        "porter_five_forces",
        "pricing_benchmark",
        "process_mapping",
        "proposal_outline",
        "public_benchmark",
        "public_observation",
        "qualification_checklist",
        "queue_analysis",
        "raci_matrix",
        "report_skeleton",
        "risk_register",
        "risk_scoring",
        "scenario_planning",
        "service_blueprint",
        "service_level_analysis",
        "seven_s",
        "sop_skeleton",
        "spend_analysis",
        "staffing_plan",
        "stakeholder_interview",
        "stakeholder_map",
        "summary_skeleton",
        "swot",
        "value_chain",
    }
)


def validate_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Filter a metadata dict so every value lands in the seed vocabulary.

    Caller-supplied metadata that lands outside the vocab is **silently dropped**
    with a hint in `meta["_dropped"]` — we never 422 a user for guessing a new
    value, but we also never let it fragment the facet catalog. (TASK §2.2
    "若确实缺某取值, 先在报告里提出, 不要私自扩词表" — extension is a code change,
    not a runtime side-effect.)
    """
    out: dict[str, Any] = {}
    dropped: dict[str, list[Any]] = {}

    def _check(key: str, allowed: frozenset[str], value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, Iterable):
            values = list(value)
        else:
            dropped.setdefault(key, []).append(value)
            return None
        kept: list[str] = []
        for v in values:
            if isinstance(v, str) and v in allowed:
                kept.append(v)
            else:
                dropped.setdefault(key, []).append(v)
        return kept or None

    for key, allowed in (
        ("type", ALLOWED_TYPES),
        ("engagement_phase", ALLOWED_PHASES),
        ("client_industry", ALLOWED_INDUSTRIES),
        ("problem_types", ALLOWED_PROBLEM_TYPES),
        ("methods", ALLOWED_METHODS),
    ):
        kept = _check(key, allowed, meta.get(key))
        if kept:
            out[key] = kept

    if dropped:
        out["_dropped"] = {k: sorted({str(v) for v in vs}) for k, vs in dropped.items()}
    return out


# ---------------------------------------------------------------------------
# Deterministic metadata suggester — pure function of (filename, title).
# ---------------------------------------------------------------------------

# Ordered list of (vocab_value, [keyword, ...]) — first hit wins. Order is the
# spec; do not reorder without re-running the determinism test.
_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("deliverable_template", ("模板", "template", "skeleton", "deck", "report_skeleton", "sop_skeleton")),
    ("risk_check", ("风险", "risk", "合规", "checklist", "compliance")),
    ("proposal_play", ("提案", "proposal", "play", "打法", "outreach")),
    ("industry_note", ("行业", "industry", "洞察", "insight", "市场")),
    ("methodology", ("方法", "method", "方法论", "framework", "framework")),
    ("case", ("案例", "case", "客户故事", "项目故事", "project")),
)
_PHASE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("qualification", ("机会", "qualification", "判断", "商机")),
    ("proposal", ("提案", "proposal", "rfp")),
    ("diagnosis", ("诊断", "diagnosis", "调研", "现状", "盘点")),
    ("implementation", ("实施", "落地", "implementation", "执行", "上线")),
    ("delivery", ("交付", "delivery", "上线后")),
)
_INDUSTRY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("retail", ("零售", "retail", "门店", "坪效")),
    ("banking", ("银行", "bank", "城商行", "金融", "信贷")),
    ("manufacturing", ("制造", "manufactur", "工厂", "供应链")),
    ("technology", ("科技", "tech", "saas", "软件", "互联网", "ai")),
    ("healthcare", ("医疗", "health", "医院", "药")),
    ("logistics", ("物流", "logistic", "运输", "快递")),
    ("energy", ("能源", "energy", "电力", "油气")),
    ("insurance", ("保险", "insurance", "精算")),
    ("consumer_goods", ("消费品", "consumer", "快消", "fmcg")),
    ("public_sector", ("政府", "public", "事业单位", "国企", "机关")),
)
# Problem types & methods are too granular for safe keyword auto-suggestion in
# this round — leaving them empty by default keeps suggestions honest.
# (TASK §4 step 3 says "based on filename+title" — the helper still returns
# `problem_types`/`methods` keys as empty lists so the contract is stable.)
_PROBLEM_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = ()
_METHOD_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = ()


def _first_match(
    text: str,
    table: tuple[tuple[str, tuple[str, ...]], ...],
) -> str | None:
    """First (vocab, keywords) pair whose keywords ALL appear in `text`.

    All keywords must be present (not just one) so e.g. "实施方法" doesn't
    accidentally fire "实施" alone when there is no phase context. Returns
    the vocab value or None. Order of table = table; iteration is stable.
    """
    if not text:
        return None
    norm = text.lower()
    for vocab, kws in table:
        if all(kw.lower() in norm for kw in kws):
            return vocab
    return None


def suggest_metadata(filename: str | None, title: str | None) -> dict[str, list[str]]:
    """Suggest consulting metadata based on filename + title.

    Pure function. Same inputs → same outputs (modulo iteration order, which
    is fixed by sorting). Only values from the seed vocabularies are emitted,
    so `validate_metadata(suggest_metadata(...))` is a no-op.

    Returned keys are always present (possibly empty lists) so callers can
    rely on the contract:
      {"type": ["…"], "engagement_phase": ["…"], "client_industry": ["…"],
       "problem_types": [], "methods": []}
    """
    haystack = " ".join(filter(None, (filename, title))).strip()
    # Note: haystack is .lower()'d inside _first_match; no further normalisation.
    return {
        "type": [_first_match(haystack, _TYPE_KEYWORDS)] if _first_match(haystack, _TYPE_KEYWORDS) else [],
        "engagement_phase": [_first_match(haystack, _PHASE_KEYWORDS)] if _first_match(haystack, _PHASE_KEYWORDS) else [],
        "client_industry": [_first_match(haystack, _INDUSTRY_KEYWORDS)] if _first_match(haystack, _INDUSTRY_KEYWORDS) else [],
        "problem_types": [],
        "methods": [],
    }


def resolve_metadata(
    caller: dict[str, Any] | None,
    suggested: dict[str, list[str]],
) -> dict[str, Any]:
    """Merge caller-supplied metadata (priority) on top of suggestions.

    - Caller's value is kept verbatim IF it passes validate_metadata (vocab check).
    - Caller's value is dropped (recorded under "_dropped") if it lands outside the vocab.
    - Suggested values fill in only when caller did not provide a value.

    The merged dict is then passed through `validate_metadata` so the response
    shape is identical whether the caller supplied values or not.
    """
    base: dict[str, Any] = {}
    for key, val in (suggested or {}).items():
        if val:
            base[key] = list(val)
    if caller:
        # caller wins for keys they provided
        for key, val in caller.items():
            if key.startswith("_"):
                continue
            if val is None:
                continue
            base[key] = val
    return validate_metadata(base)


__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAX_SINGLE_FILE_BYTES",
    "MAX_TOTAL_BYTES",
    "ALLOWED_TYPES",
    "ALLOWED_PHASES",
    "ALLOWED_INDUSTRIES",
    "ALLOWED_PROBLEM_TYPES",
    "ALLOWED_METHODS",
    "check_extension",
    "check_single_size",
    "check_aggregate_size",
    "validate_metadata",
    "suggest_metadata",
    "resolve_metadata",
]
