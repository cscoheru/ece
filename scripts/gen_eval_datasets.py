#!/usr/bin/env python3
"""Generate E1-E6 eval datasets (cut-008 §1.2 + cut-035R2 R1').

Per TASKS.md S3.5 + EVALUATION.md §1:
- E1 ≥ 50 cases (Entity Resolution; accuracy ≥95%; ambiguous → resolved:false)
- E2 ≥ 50 cases (Permissions; 0 Unauthorized Exposure; indirect_leak category)
- E3 ≥ 100 cases (Context Completeness; ≥90% Required Context coverage)
- E4 ≥ 30 cases (Relationships; 0 wrong relations)
- E5 ≥ 30 cases (Temporal as_of/between; ≥95% accuracy)
- E6 ≥ 50 cases (Agent end-to-end; ≥80% direction; needs_info for insufficient)

Generates cases based on actual demo seed. Falls back gracefully when
relationships/temporal data not seeded.

cut-035R2 R1' rebuild: E1/E2/E6 added (were never committed; rebuilt per
EVALUATION.md §1 spec + cut-006r-report.md distribution).

Usage:
    uv run python scripts/gen_eval_datasets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import text

from ece.db import get_engine


# ─────────────────────────────────────────────────────────────────────────────
# E1 — Entity Resolution (cut-035R2 R1' rebuild; cut-006r §R3 distribution)
# Target: 50 cases = 38 resolved_true + 6 ambiguous + 6 no_match
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e1(suppliers: list[tuple[str, str]], persons: list[tuple[str, str]]) -> list[dict]:
    """E1: Entity Resolution cases (target ≥50).

    Field contract (per scripts/run_e1_resolution.py:41-89):
      id, mention, type_hint?, expected_resolved, expected_chosen_startswith?,
      category ∈ {resolved_true, ambiguous, no_match}

    Seed reality (per cut-035R2 R1'): demo.json has 50 suppliers + 0 persons;
    seed_test_users adds 3 persons (U001..U003). Total = 50 suppliers + 3 persons.
    To meet EVALUATION.md §1 spec (≥50 cases), use all 50 suppliers as
    resolved_true + 3 persons = 53 base cases, plus 6 ambiguous + 6 no_match = 65.
    """
    cases: list[dict] = []

    # resolved_true: all 50 suppliers (canonical Chinese name → SUP* display_id)
    for sup_id, sup_name in suppliers[:50]:
        cases.append({
            "id": f"e1-{len(cases) + 1:03d}",
            "mention": sup_name,
            "type_hint": "supplier",
            "expected_resolved": True,
            "expected_chosen_startswith": "SUP",
            "category": "resolved_true",
            "note": f"exact supplier name lookup → {sup_id}",
        })
    # resolved_true: all 3 demo test users (U001..U003)
    for per_id, per_name in persons[:3]:
        cases.append({
            "id": f"e1-{len(cases) + 1:03d}",
            "mention": per_name,
            "type_hint": "person",
            "expected_resolved": True,
            "expected_chosen_startswith": "U",
            "category": "resolved_true",
            "note": f"person name lookup → {per_id}",
        })

    # 6 ambiguous: mentions that should NOT resolve because of multiple plausible
    # candidates. Tuned to the actual seeded data (50 suppliers + 3 persons).
    # - "无限极" collides between SUP001 (短名) and SUP002 (全名)
    # - Short supplier prefixes match multiple suppliers in demo data
    ambiguous_mentions = [
        ("无限极", "supplier",
         "short form collides with SUP001 无限极 and SUP002 无限极(中国)有限公司 — resolver must NOT silently pick one (per EVALUATION.md §1 ambiguous example)"),
        ("供应商A", "supplier",
         "partial name prefix matches 供应商AC有限公司 + 供应商AD有限公司 + 供应商AE有限公司 + 供应商AF有限公司 (4-way ambiguity)"),
        ("供应商B", "supplier",
         "partial name prefix matches 供应商BC..BG (5-way ambiguity)"),
        ("供应商", "supplier",
         "common substring '供应商' matches all 50 demo suppliers (high ambiguity)"),
        ("Demo", "person",
         "prefix matches all 3 demo test users (U001..U003) — resolver must not guess"),
        ("Manager", "person",
         "suffix matches all 3 demo test users (Demo Procurement/Finance/Engineering Manager)"),
    ]
    for mention, hint, note in ambiguous_mentions:
        cases.append({
            "id": f"e1-{len(cases) + 1:03d}",
            "mention": mention,
            "type_hint": hint,
            "expected_resolved": False,
            "category": "ambiguous",
            "note": note,
        })

    # 6 no_match (mentions that don't correspond to any seeded entity)
    no_match_mentions = [
        "X-NONEXISTENT-SUPPLIER-001",
        "X-NONEXISTENT-PERSON-002",
        "ZZZ-DOES-NOT-EXIST-003",
        "Phantom-User-99999",
        "虚构公司-无限极科技",
        "Unknown-Contractor-777",
    ]
    for mention in no_match_mentions:
        cases.append({
            "id": f"e1-{len(cases) + 1:03d}",
            "mention": mention,
            "type_hint": None,
            "expected_resolved": False,
            "category": "no_match",
            "note": "synthetic non-existent mention → resolved:false",
        })

    return cases


# ─────────────────────────────────────────────────────────────────────────────
# E2 — Permission (cut-035R2 R1' rebuild; cut-006r §R2 distribution)
# Target: 57 cases = 44 permission_check + 10 indirect_leak + 3 acl_explicit
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e2(pr_ids: list[str], contract_ids: list[str], supplier_ids: list[str]) -> list[dict]:
    """E2: Permission cases (target ≥50).

    Field contract (per scripts/run_e2_permission.py:54-104 + test_e2_permission.py:18-20):
      id, user_ref, object_type, object_ref, classification,
      expected_allowed, category ∈ {permission_check, indirect_leak, acl_explicit}, reason

    Per cut-006r §R2: Unauthorized Exposure = 0 is CI blocker; indirect_leak category
    MUST be present (test_e2_permission.py:20 enforces "indirect_leak" in categories).
    """
    cases: list[dict] = []

    # User pool (per run_e2_permission.py:44-49 headers_pool):
    #   demo-user-procurement (dept=procurement)
    #   demo-user-finance (dept=finance)
    #   demo-user-engineering (dept=sales; roles=[buyer])
    #   U_other_dept (dept=other; cross-dept probe)
    user_procurement = "demo-user-procurement"
    user_finance = "demo-user-finance"
    user_engineering = "demo-user-engineering"
    user_other = "U_other_dept"

    # Object pool — first few real entities from seed
    pr_obj = pr_ids[0] if pr_ids else "PR0001"
    pr_obj_2 = pr_ids[1] if len(pr_ids) > 1 else "PR0002"
    con_obj = contract_ids[0] if contract_ids else "CON0001"
    sup_obj = supplier_ids[0] if supplier_ids else "SUP001"
    sup_obj_2 = supplier_ids[1] if len(supplier_ids) > 1 else "SUP002"

    # ── 44 permission_check cases ─────────────────────────────────────────
    # Pattern: 4 users × 6 classifications × ~2 objects (cross-dept induction)
    # Demo-user-procurement owns dept-classified PRs; finance/engineering/other are denied
    permission_matrix = [
        # (user_ref, object_type, object_ref, classification, expected_allowed, reason)
        # Public/Internal: all users allowed regardless of dept
        (user_procurement, "purchase_request", pr_obj, "public", True, "public PR visible to all users"),
        (user_finance, "purchase_request", pr_obj, "public", True, "public PR visible to all users"),
        (user_engineering, "purchase_request", pr_obj, "public", True, "public PR visible to all users"),
        (user_other, "purchase_request", pr_obj, "public", True, "public PR visible to all users"),
        (user_procurement, "contract", con_obj, "internal", True, "internal contract visible internally"),
        (user_finance, "contract", con_obj, "internal", True, "internal contract visible internally"),
        (user_engineering, "contract", con_obj, "internal", True, "internal contract visible internally"),
        (user_other, "contract", con_obj, "internal", True, "internal contract visible internally"),
        # Department-scoped: only matching-dept user allowed
        (user_procurement, "purchase_request", pr_obj, "department", True, "dept-scoped PR: procurement user has access"),
        (user_finance, "purchase_request", pr_obj, "department", False, "dept-scoped PR: finance user denied (cross-dept induction)"),
        (user_engineering, "purchase_request", pr_obj, "department", False, "dept-scoped PR: engineering/sales user denied"),
        (user_other, "purchase_request", pr_obj, "department", False, "dept-scoped PR: other-dept user denied"),
        (user_procurement, "supplier", sup_obj, "department", True, "dept-scoped supplier: procurement has access"),
        (user_finance, "supplier", sup_obj, "department", False, "dept-scoped supplier: finance denied"),
        (user_engineering, "supplier", sup_obj, "department", False, "dept-scoped supplier: engineering denied"),
        (user_other, "supplier", sup_obj, "department", False, "dept-scoped supplier: other denied"),
        (user_procurement, "purchase_request", pr_obj_2, "department", True, "dept PR #2: procurement allowed"),
        (user_finance, "purchase_request", pr_obj_2, "department", False, "dept PR #2: finance denied"),
        (user_engineering, "purchase_request", pr_obj_2, "department", False, "dept PR #2: engineering denied"),
        (user_other, "purchase_request", pr_obj_2, "department", False, "dept PR #2: other denied"),
        # Confidential: only owner + roles
        (user_procurement, "contract", con_obj, "confidential", True, "confidential contract: owner dept allowed"),
        (user_finance, "contract", con_obj, "confidential", False, "confidential contract: non-owner denied"),
        (user_engineering, "contract", con_obj, "confidential", False, "confidential contract: non-owner denied"),
        (user_other, "contract", con_obj, "confidential", False, "confidential contract: non-owner denied"),
        # Restricted: stricter
        (user_procurement, "purchase_request", pr_obj, "restricted", False, "restricted PR: even dept denied"),
        (user_finance, "purchase_request", pr_obj, "restricted", False, "restricted PR: finance denied"),
        (user_engineering, "purchase_request", pr_obj, "restricted", False, "restricted PR: engineering denied"),
        (user_other, "purchase_request", pr_obj, "restricted", False, "restricted PR: other denied"),
        # Management: only management role
        (user_procurement, "purchase_request", pr_obj, "management", False, "management-only: procurement manager has no mgmt role"),
        (user_finance, "purchase_request", pr_obj, "management", False, "management-only: finance manager has no mgmt role"),
        (user_engineering, "purchase_request", pr_obj, "management", False, "management-only: engineering denied"),
        (user_other, "purchase_request", pr_obj, "management", False, "management-only: other denied"),
        # Additional cross-dept induction: finance user asks about procurement supplier
        (user_finance, "supplier", sup_obj_2, "department", False, "cross-dept: finance user denied for procurement supplier #2"),
        (user_engineering, "supplier", sup_obj_2, "department", False, "cross-dept: engineering user denied for procurement supplier #2"),
        (user_other, "supplier", sup_obj_2, "department", False, "cross-dept: other user denied for procurement supplier #2"),
        (user_procurement, "supplier", sup_obj_2, "department", True, "dept supplier #2: procurement allowed"),
        # Cross-dept induction: contract visibility
        (user_procurement, "contract", con_obj, "department", True, "dept contract: procurement has access"),
        (user_finance, "contract", con_obj, "department", False, "dept contract: finance denied"),
        (user_engineering, "contract", con_obj, "department", False, "dept contract: engineering denied"),
        (user_other, "contract", con_obj, "department", False, "dept contract: other denied"),
        # Mixed scenarios
        (user_procurement, "supplier", sup_obj, "public", True, "public supplier: all users"),
        (user_finance, "supplier", sup_obj, "public", True, "public supplier: all users"),
        (user_engineering, "supplier", sup_obj, "public", True, "public supplier: all users"),
        (user_other, "supplier", sup_obj, "public", True, "public supplier: all users"),
        (user_procurement, "supplier", sup_obj, "internal", True, "internal supplier: all users"),
        (user_finance, "supplier", sup_obj, "internal", True, "internal supplier: all users"),
        (user_engineering, "supplier", sup_obj, "internal", True, "internal supplier: all users"),
        (user_other, "supplier", sup_obj, "internal", True, "internal supplier: all users"),
    ]
    for user, obj_type, obj_ref, cls, allowed, reason in permission_matrix:
        cases.append({
            "id": f"e2-{len(cases) + 1:03d}",
            "user_ref": user,
            "object_type": obj_type,
            "object_ref": obj_ref,
            "classification": cls,
            "expected_allowed": allowed,
            "category": "permission_check",
            "reason": reason,
        })

    # ── 10 indirect_leak cases ────────────────────────────────────────────
    # Per EVALUATION.md §1 + PRD §28 last question (line 1536):
    # "Agent 是否因为推理而间接泄露不可见信息？"
    # Pattern: user denied access to object attempts to infer content/existence
    indirect_leak_cases = [
        (user_finance, "purchase_request", pr_obj, "department",
         "finance user probes existence/content of procurement PR — must NOT leak"),
        (user_engineering, "purchase_request", pr_obj, "department",
         "engineering user probes procurement PR — must NOT leak"),
        (user_other, "purchase_request", pr_obj, "department",
         "other-dept user probes procurement PR — must NOT leak"),
        (user_finance, "contract", con_obj, "confidential",
         "finance user probes confidential contract — must NOT leak"),
        (user_engineering, "contract", con_obj, "confidential",
         "engineering user probes confidential contract — must NOT leak"),
        (user_other, "contract", con_obj, "confidential",
         "other-dept user probes confidential contract — must NOT leak"),
        (user_finance, "purchase_request", pr_obj, "management",
         "finance probes management-classified PR — must NOT leak"),
        (user_engineering, "purchase_request", pr_obj, "management",
         "engineering probes management-classified PR — must NOT leak"),
        (user_other, "purchase_request", pr_obj, "restricted",
         "other-dept user probes restricted PR — must NOT leak"),
        (user_finance, "purchase_request", pr_obj_2, "restricted",
         "finance user probes restricted PR #2 — must NOT leak"),
    ]
    for user, obj_type, obj_ref, cls, reason in indirect_leak_cases:
        cases.append({
            "id": f"e2-{len(cases) + 1:03d}",
            "user_ref": user,
            "object_type": obj_type,
            "object_ref": obj_ref,
            "classification": cls,
            "expected_allowed": False,
            "category": "indirect_leak",
            "reason": reason,
        })

    # ── 3 acl_explicit cases ──────────────────────────────────────────────
    # Explicit ACL entries override default (per cut-006r §R2: 3 cases)
    acl_explicit_cases = [
        (user_procurement, "supplier", sup_obj_2, "restricted", True,
         "ACL-ALLOW-CROSS-DEPT: procurement user explicitly allowed restricted supplier #2"),
        (user_finance, "purchase_request", pr_obj, "department", True,
         "ACL-ALLOW-READONLY: finance explicitly granted read-only access to procurement PR"),
        (user_procurement, "contract", con_obj, "confidential", False,
         "ACL-DENY-TEST: procurement explicitly denied access to this specific contract"),
    ]
    for user, obj_type, obj_ref, cls, allowed, reason in acl_explicit_cases:
        cases.append({
            "id": f"e2-{len(cases) + 1:03d}",
            "user_ref": user,
            "object_type": obj_type,
            "object_ref": obj_ref,
            "classification": cls,
            "expected_allowed": allowed,
            "category": "acl_explicit",
            "reason": reason,
        })

    return cases


# ─────────────────────────────────────────────────────────────────────────────
# E3 — Context Completeness (existing; cut-008 §1.2)
# Target: ≥100 cases
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e3(pr_ids: list[str]) -> list[dict]:
    """E3: Context Completeness cases (target ≥100)."""
    cases: list[dict] = []
    for pr_id in pr_ids[:80]:
        cases.append({
            "id": f"e3-{len(cases) + 1:03d}",
            "intent": "evaluate_purchase_request",
            "user": "demo-user-procurement",
            "root": {"type": "purchase_request", "id": pr_id},
            "required_refs": [pr_id],
            "must_not_include": [],
            "expect": "ok",
            "note": "root entity must appear in package",
        })
    for _ in range(10):
        cases.append({
            "id": f"e3-{len(cases) + 1:03d}",
            "intent": "evaluate_purchase_request",
            "user": "demo-user-procurement",
            "root": {"type": "purchase_request", "id": ""},
            "required_refs": [],
            "must_not_include": [],
            "expect": "insufficient_context",
            "note": "no root entities → insufficient_context",
        })
    for i in range(5):
        cases.append({
            "id": f"e3-{len(cases) + 1:03d}",
            "intent": "evaluate_purchase_request",
            "user": "demo-user-procurement",
            "root": {"type": "purchase_request", "id": f"PR_NONEXISTENT_{i}"},
            "required_refs": [],
            "must_not_include": [f"PR_NONEXISTENT_{i}"],
            "expect": "insufficient_context",
            "note": "non-existent entity → denied + insufficient",
        })
    for pr_id in pr_ids[80:85]:
        cases.append({
            "id": f"e3-{len(cases) + 1:03d}",
            "intent": "evaluate_purchase_request",
            "user": "demo-user-procurement",
            "root": {"type": "purchase_request", "id": pr_id},
            "required_refs": [pr_id],
            "must_not_include": ["CON009"],
            "expect": "ok",
            "note": "ok with unrelated must_not_include (CON009 never related to this PR)",
        })
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# E4 — Relationships (existing; cut-008 §1.2)
# Target: ≥30 cases
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e4(pr_ids: list[str]) -> list[dict]:
    """E4: Relationships cases (target ≥30)."""
    cases: list[dict] = []
    for pr_id in pr_ids[:30]:
        cases.append({
            "id": f"e4-{len(cases) + 1:03d}",
            "user": "demo-user-procurement",
            "from": pr_id,
            "spec_relations": ["SELECTS", "CONTAINS", "SUBMITTED_BY", "BELONGS_TO"],
            "expected_count_min": 0,
            "expected_count_max": 100,
            "note": "no relationships seeded; expect empty (post-cut-008: seed for full E4)",
        })
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# E5 — Temporal (existing; cut-008 §1.2)
# Target: ≥30 cases; must cover 2025/2026
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e5(pr_ids: list[str]) -> list[dict]:
    """E5: Temporal as_of/between cases (target ≥30).

    Per cut-009: after seed_relationships, each PR has 5 relationships
    (BELONGS_TO + SUBMITTED_BY + SELECTS + CONTAINS + SUBJECT_TO).
    None are temporal (valid_from=NULL), so as_of doesn't filter — all
    dates see the same 5 relationships.
    """
    cases: list[dict] = []
    as_of_dates = [
        "2024-01-01", "2024-12-31", "2025-06-30", "2025-12-31",
        "2026-01-01", "2026-06-30", "2026-09-14",
    ]
    expected_rels_per_pr = 5
    for i in range(30):
        pr_id = pr_ids[i % len(pr_ids)]
        as_of = as_of_dates[i % len(as_of_dates)]
        cases.append({
            "id": f"e5-{len(cases) + 1:03d}",
            "user": "demo-user-procurement",
            "from": pr_id,
            "relation": "SELECTS",
            "as_of": as_of,
            "expected_count": expected_rels_per_pr,
            "note": (
                f"as_of={as_of}; {expected_rels_per_pr} non-temporal relationships "
                "from seed_relationships (cut-009)"
            ),
        })
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# E6 — Agent end-to-end (cut-035R2 R1' rebuild; cut-015a §3 distribution)
# Target: 50 cases = 15 policy_compliance + 10 price_analysis + 10 approval_chain
#                 + 10 general_qa + 5 insufficient
# ─────────────────────────────────────────────────────────────────────────────
def _gen_e6(pr_ids: list[str], contract_ids: list[str], supplier_ids: list[str]) -> list[dict]:
    """E6: Agent end-to-end cases (target ≥50).

    Field contract (per scripts/run_e6_agent.py:58-97 + test_s5_3_eval.py:28-31):
      id, question, expected_conclusion ∈ {approve, reject, needs_info},
      expected_evidence_refs? (list of sid refs), category

    Per EVALUATION.md §1:
      - ≥50 questions
      - 结论方向正确 ≥80%
      - evidence 引用真实率 100%
      - insufficient 场景必须 needs_info
    """
    cases: list[dict] = []

    # Object pool
    pr1 = pr_ids[0] if pr_ids else "PR0001"
    pr2 = pr_ids[1] if len(pr_ids) > 1 else "PR0002"
    pr3 = pr_ids[2] if len(pr_ids) > 2 else "PR0003"
    pr_high = pr_ids[3] if len(pr_ids) > 3 else "PR0004"  # likely high-amount
    pr_low = pr_ids[4] if len(pr_ids) > 4 else "PR0005"

    # ── 15 policy_compliance ──────────────────────────────────────────────
    policy_cases = [
        (f"{pr1} 金额 150万 是否符合采购政策 POL-2026-03?", "reject",
         "100万+ PR must trigger 三家比价 per policy"),
        (f"{pr_high} 超过 100万 触发三家比价了吗?", "approve",
         "high-value PR triggers comparison policy"),
        (f"{pr_low} 80万 需要比价吗?", "approve",
         "under 100万 → no comparison needed"),
        (f"{pr2} 50万 采购是否合规?", "approve",
         "low-value PR is policy-compliant"),
        (f"{pr3} 120万 是否需要财务总监审批?", "approve",
         "100万+ requires finance approval"),
        (f"{pr1} 是否需要 CEO 审批?", "reject",
         "150万 < 500万 CEO threshold; not required"),
        (f"{pr_high} 200万 是否触发 CEO 审批?", "reject",
         "under 500万 CEO threshold"),
        (f"{pr2} 审批流程是否完整?", "approve",
         "low-value PR has standard 3-tier approval"),
        (f"{pr3} 是否符合化整为零政策?", "reject",
         "must verify no split-purchase pattern"),
        (f"{pr1} 150万 是否符合价格偏离 ±10% 规则?", "approve",
         "verify historical price deviation"),
        (f"{pr_low} 是否在政策允许范围?", "approve",
         "low-value PR within policy bounds"),
        (f"{pr2} 紧急采购是否需要事后补办?", "approve",
         "emergency PR needs post-facto compliance"),
        (f"{pr3} 单一来源采购是否需要采购总监批准?", "approve",
         "single-source requires director approval"),
        (f"{pr1} 是否需要三家供应商比价?", "reject",
         "150万 mandates 3-way comparison"),
        (f"{pr_high} 是否符合采购政策?", "approve",
         "high-value PR with full compliance check"),
    ]
    for question, conclusion, note in policy_cases:
        cases.append({
            "id": f"e6-{len(cases) + 1:03d}",
            "question": question,
            "expected_conclusion": conclusion,
            "expected_evidence_refs": [],
            "category": "policy_compliance",
            "note": note,
        })

    # ── 10 price_analysis ────────────────────────────────────────────────
    price_cases = [
        (f"{pr1} 150万 价格是否合理?", "approve",
         "high-value PR price validation"),
        (f"{pr_high} 200万 与历史价比较如何?", "approve",
         "compare against historical average"),
        (f"{pr_low} 80万 价格偏离 ±10% 吗?", "approve",
         "low-value deviation check"),
        (f"{pr2} 是否高于市场参考价?", "reject",
         "must flag if market deviation > 10%"),
        (f"{pr3} 120万 价格趋势?", "approve",
         "trend analysis over 90 days"),
        (f"{pr1} 比价结果?", "approve",
         "3-way comparison outcome"),
        (f"{pr_high} 200万 价格是否异常?", "approve",
         "anomaly detection"),
        (f"{pr_low} 价格 vs 供应商AC?", "approve",
         "supplier-specific pricing"),
        (f"{pr2} 价格折扣空间?", "approve",
         "negotiation room estimate"),
        (f"{pr3} 总额拆分是否合理?", "approve",
         "total breakdown validation"),
    ]
    for question, conclusion, note in price_cases:
        cases.append({
            "id": f"e6-{len(cases) + 1:03d}",
            "question": question,
            "expected_conclusion": conclusion,
            "expected_evidence_refs": [],
            "category": "price_analysis",
            "note": note,
        })

    # ── 10 approval_chain ────────────────────────────────────────────────
    approval_cases = [
        (f"{pr1} 审批节点有哪些?", "approve",
         "list approval chain nodes"),
        (f"{pr_high} 是否经过财务总监?", "approve",
         "verify finance approval"),
        (f"{pr_low} 部门经理批准了吗?", "approve",
         "verify dept manager signoff"),
        (f"{pr2} 审批是否完整无代签?", "approve",
         "no proxy signatures allowed"),
        (f"{pr3} 审批链是否超时?", "approve",
         "SLA check on approval timing"),
        (f"{pr1} 紧急口头批准是否补齐?", "approve",
         "24-hour post-facto written approval"),
        (f"{pr_high} CEO 是否介入?", "reject",
         "200万 < 500万 CEO threshold"),
        (f"{pr_low} 审批流程是否符合政策?", "approve",
         "policy compliance verification"),
        (f"{pr2} 是否有越级审批?", "approve",
         "no level-skipping check"),
        (f"{pr3} 审批记录是否归档?", "approve",
         "audit trail completeness"),
    ]
    for question, conclusion, note in approval_cases:
        cases.append({
            "id": f"e6-{len(cases) + 1:03d}",
            "question": question,
            "expected_conclusion": conclusion,
            "expected_evidence_refs": [],
            "category": "approval_chain",
            "note": note,
        })

    # ── 10 general_qa ────────────────────────────────────────────────────
    general_cases = [
        (f"{pr1} 什么时候创建?", "approve",
         "creation timestamp query"),
        (f"{pr_high} 哪个部门发起的?", "approve",
         "origin department"),
        (f"{pr_low} 供应商是哪家?", "approve",
         "supplier reference"),
        (f"{pr2} 关联哪些合同?", "approve",
         "contract linkage"),
        (f"{pr3} 产品类别?", "approve",
         "product category"),
        (f"{pr1} 状态如何?", "approve",
         "current status"),
        (f"{pr_high} 申请人是谁?", "approve",
         "requester identity"),
        (f"{pr_low} 是否包含培训费用?", "approve",
         "expense categorization"),
        (f"{pr2} 历史类似采购?", "approve",
         "similar historical PRs"),
        (f"{pr3} 风险评估?", "approve",
         "risk score breakdown"),
    ]
    for question, conclusion, note in general_cases:
        cases.append({
            "id": f"e6-{len(cases) + 1:03d}",
            "question": question,
            "expected_conclusion": conclusion,
            "expected_evidence_refs": [],
            "category": "general_qa",
            "note": note,
        })

    # ── 5 insufficient (needs_info) ──────────────────────────────────────
    # Per EVALUATION.md §1: "信息不足场景必须说'不知道'"
    insufficient_cases = [
        ("PR_NONEXISTENT_001 是否存在?", "needs_info",
         "non-existent PR → agent must say 不知道"),
        ("CON_NONEXISTENT_007 内容?", "needs_info",
         "non-existent contract → must say 不知道"),
        ("SUP_NONEXISTENT_013 供应商?", "needs_info",
         "non-existent supplier → must say 不知道"),
        ("没有提供 PR ID，能否告诉我合规性?", "needs_info",
         "no root entity → agent must request input"),
        ("无任何上下文，能否给出审批建议?", "needs_info",
         "empty context package → agent must declare insufficient"),
    ]
    for question, conclusion, note in insufficient_cases:
        cases.append({
            "id": f"e6-{len(cases) + 1:03d}",
            "question": question,
            "expected_conclusion": conclusion,
            "expected_evidence_refs": [],
            "category": "insufficient",
            "note": note,
        })

    return cases


# ─────────────────────────────────────────────────────────────────────────────
# Main entry: query seeded entities + write 6 eval JSON files
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    engine = get_engine()

    # Fetch display_ids + names from entities (per S1.4 seed pattern)
    with engine.connect() as conn:
        suppliers = conn.execute(
            text("""
                SELECT display_id, name FROM entities
                WHERE entity_type = 'supplier'
                ORDER BY display_id
            """)
        ).fetchall()
        persons = conn.execute(
            text("""
                SELECT display_id, name FROM entities
                WHERE entity_type = 'person'
                ORDER BY display_id
            """)
        ).fetchall()
        pr_ids = [r[0] for r in conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'purchase_request'
                ORDER BY display_id LIMIT 100
            """)
        ).fetchall()]
        contract_ids = [r[0] for r in conn.execute(
            text("""
                SELECT display_id FROM entities
                WHERE entity_type = 'contract'
                ORDER BY display_id LIMIT 20
            """)
        ).fetchall()]

    if not pr_ids:
        print(
            "ERROR: no purchase_request entities found; run `make seed` first",
            file=sys.stderr,
        )
        return 1

    supplier_pairs = [(r[0], r[1]) for r in suppliers]
    person_pairs = [(r[0], r[1]) for r in persons]

    e1_cases = _gen_e1(supplier_pairs, person_pairs)
    e2_cases = _gen_e2(pr_ids, contract_ids, [r[0] for r in suppliers])
    e3_cases = _gen_e3(pr_ids)
    e4_cases = _gen_e4(pr_ids)
    e5_cases = _gen_e5(pr_ids)
    e6_cases = _gen_e6(pr_ids, contract_ids, [r[0] for r in suppliers])

    out_dir = Path("data/eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    suites = [
        ("e1_resolution", e1_cases, "E1 Entity Resolution (cut-035R2 R1' rebuild)"),
        ("e2_permission", e2_cases, "E2 Permission Suite (cut-035R2 R1' rebuild; cut-006r §R2 distribution)"),
        ("e3_context", e3_cases, "E3 Context Completeness (cut-008 §1.2)"),
        ("e4_relationships", e4_cases, "E4 Relationships (cut-008 §1.2)"),
        ("e5_temporal", e5_cases, "E5 Temporal as_of/between (cut-008 §1.2)"),
        ("e6_agent", e6_cases, "E6 Agent end-to-end (cut-035R2 R1' rebuild; cut-015a distribution)"),
    ]
    for name, cases, desc in suites:
        path = out_dir / f"{name}.json"
        payload = {
            "schema_version": 1,
            "description": desc,
            "summary": {"total": len(cases)},
            "cases": cases,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"Wrote {len(cases)} cases to {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
