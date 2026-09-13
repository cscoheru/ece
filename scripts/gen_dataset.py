#!/usr/bin/env python3
"""S0.6: scripts/gen_dataset.py

依据 docs/PRD.md §27 (`# 27. Demo Dataset`) 规模定义产出 Demo Corporation
合成数据,含对抗性标记列。

确定性(--seed,默认 42)、幂等(重跑覆盖不报错)、无网络、不入库(S1.2 才接管线)。

per ece/TASKS.md S0.6 + PRD §27 验收要求:
- 打印统计(各类型实体/关系数量 + 对抗用例计数)
- 与 PRD §27 声明规模不符 → exit 1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


# PRD §27 target scale (must match this dict exactly)
PRD_27_TARGET = {
    "users": 20,
    "departments": 6,
    "suppliers": 50,
    "products": 100,
    "purchase_requests": 200,
    "contracts": 50,
    "policies": 20,
    "approval_records": 500,
    "documents": 500,
}

# PRD §27 用 "20+"/"200+" 数量级表达,非精确值;容许 ±5% 偏差
def tolerance_for(target_value: int) -> int:
    return max(2, target_value // 20)  # 至少 2,大值 5%

DEPARTMENTS = ["采购", "财务", "IT", "销售", "HR", "法务"]
SUPPLIER_NAMES = [f"供应商{chr(0x41 + i // 26)}{chr(0x41 + i % 26)}有限公司" for i in range(60)]
PRODUCT_CATEGORIES = ["办公设备", "IT服务", "原材料", "物流", "咨询", "软件许可"]
ROLE_NAMES = ["采购经理", "采购专员", "部门负责人", "财务审核员", "法务顾问"]


@dataclass
class Person:
    name: str
    department: str
    role: str
    alias_count: int  # 对抗性: 同名异人


@dataclass
class Dataset:
    users: list[Person]
    departments: list[str]
    suppliers: list[str]
    products: list[str]
    purchase_requests: list[dict]
    contracts: list[dict]
    policies: list[str]
    approval_records: list[dict]
    documents: list[str]


def generate(seed: int = 42) -> Dataset:
    rng = random.Random(seed)
    ds = Dataset(
        users=[],
        departments=list(DEPARTMENTS),
        suppliers=[],
        products=[],
        purchase_requests=[],
        contracts=[],
        policies=[],
        approval_records=[],
        documents=[],
    )

    # Users (20+) with 2 同名异人对抗用例
    for i in range(PRD_27_TARGET["users"]):
        dept = rng.choice(DEPARTMENTS)
        role = rng.choice(ROLE_NAMES)
        ds.users.append(Person(name=f"用户{i:03d}", department=dept, role=role, alias_count=0))
    # 对抗性: 2 个"张三"不同部门不同角色(同名异人 — 验证 entity resolution 能力)
    ds.users[0] = Person(name="张三", department="采购", role="采购经理", alias_count=2)
    ds.users[1] = Person(name="张三", department="财务", role="财务审核员", alias_count=0)

    # Suppliers (50+) with 2 同名异司对抗用例
    ds.suppliers = list(SUPPLIER_NAMES[: PRD_27_TARGET["suppliers"]])
    ds.suppliers[0] = "无限极"      # 简化名 (PRD §27 adversarial)
    ds.suppliers[1] = "无限极(中国)有限公司"  # 全名 — entity resolution 应对

    # Products (100+)
    for i in range(PRD_27_TARGET["products"]):
        cat = rng.choice(PRODUCT_CATEGORIES)
        ds.products.append(f"{cat}-型号{i:03d}")

    # Policies (20+) — 政策文档名
    for i in range(PRD_27_TARGET["policies"]):
        ds.policies.append(f"采购政策 v{i}.0")

    # Purchase requests (200+) — 含触发比价阈值(≥100 万)的对抗用例
    for i in range(PRD_27_TARGET["purchase_requests"]):
        amount = rng.choice([50_000, 200_000, 800_000, 1_500_000])  # 第 4 项触发比价
        ds.purchase_requests.append({
            "id": f"PR{i:04d}",
            "amount": amount,
            "supplier": rng.choice(ds.suppliers),
            "department": rng.choice(DEPARTMENTS),
            "product": rng.choice(ds.products),
            "created_at": (date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))).isoformat(),
        })

    # Contracts (50+)
    for i in range(PRD_27_TARGET["contracts"]):
        ds.contracts.append({
            "id": f"CON{i:04d}",
            "supplier": rng.choice(ds.suppliers),
            "value": rng.randint(50_000, 5_000_000),
            "signed_at": (date(2026, 1, 1) + timedelta(days=rng.randint(0, 180))).isoformat(),
        })

    # Documents (500+) — 政策 20 + 合同 50 + 杂项 430 (培训记录 / 内部通知 / PR 附件等)
    for p in ds.policies:
        ds.documents.append(f"{p}.pdf")
    for c in ds.contracts:
        ds.documents.append(f"合同-{c['id']}.pdf")
    # 杂项文档填充至 PRD §27 500+
    doc_types = ["培训记录", "内部通知", "PR 附件", "审计报告", "供应商评估"]
    while len(ds.documents) < PRD_27_TARGET["documents"]:
        ds.documents.append(f"{rng.choice(doc_types)}-{len(ds.documents):04d}.pdf")

    # Approval records (500+) — 平均每个 PR 2.5 个审批节点;目标 500 ≈ 200×2.5
    # 但 PR §27 不精确指定每 PR 审批次数,放宽到 2-3 个确保落在 400-600 区间
    for pr in ds.purchase_requests:
        for approver_role in rng.sample(ROLE_NAMES, k=rng.randint(2, 3)):
            ds.approval_records.append({
                "pr_id": pr["id"],
                "approver_role": approver_role,
                "decision": rng.choice(["approved", "approved", "rejected"]),  # 偏向通过
                "timestamp": pr["created_at"],
            })

    return ds


def print_stats(ds: Dataset, target: dict) -> bool:
    """Print actual vs target; return True if all within tolerance."""
    actual = {
        "users": len(ds.users),
        "departments": len(ds.departments),
        "suppliers": len(ds.suppliers),
        "products": len(ds.products),
        "purchase_requests": len(ds.purchase_requests),
        "contracts": len(ds.contracts),
        "policies": len(ds.policies),
        "approval_records": len(ds.approval_records),
        "documents": len(ds.documents),
    }
    print(f"\n{'Type':<22} {'Actual':>8} {'Target':>8} {'Tol':>5} {'Status':<10}")
    print("-" * 57)
    all_ok = True
    for k, actual_v in actual.items():
        target_v = target[k]
        tol = tolerance_for(target_v)
        diff = actual_v - target_v
        status = "OK" if abs(diff) <= tol else f"OFF ({diff:+d}, tol={tol})"
        if status != "OK":
            all_ok = False
        print(f"{k:<22} {actual_v:>8} {target_v:>8} {tol:>5} {status:<10}")

    # 对抗性用例计数
    print()
    same_name_users = sum(1 for u in ds.users if u.name == "张三")
    print(f"同名异人对抗用例: '张三' 出现 {same_name_users} 次 (期望 ≥ 2)")
    if same_name_users < 2:
        all_ok = False
    same_name_suppliers = sum(1 for s in ds.suppliers if s.startswith("无限极"))
    print(f"同名异司对抗用例: '无限极*' 出现 {same_name_suppliers} 次 (期望 ≥ 2)")
    if same_name_suppliers < 2:
        all_ok = False
    high_value_prs = sum(1 for pr in ds.purchase_requests if pr["amount"] >= 1_000_000)
    print(f"高额 PR 对抗用例 (≥100万 触发比价): {high_value_prs} 个 (期望 ≥ 10)")
    if high_value_prs < 10:
        all_ok = False

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/dataset/demo.json"))
    args = parser.parse_args()

    ds = generate(seed=args.seed)

    out_path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "schema_version": 1,
        "seed": args.seed,
        "users": [u.__dict__ for u in ds.users],
        "departments": ds.departments,
        "suppliers": ds.suppliers,
        "products": ds.products,
        "purchase_requests": ds.purchase_requests,
        "contracts": ds.contracts,
        "policies": ds.policies,
        "approval_records": ds.approval_records,
        "documents": ds.documents,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDataset written: {out_path}")
    print(f"Seed: {args.seed} (deterministic — re-run with same seed yields identical data)")

    if print_stats(ds, PRD_27_TARGET):
        print("\nOK — all counts within tolerance, adversarial cases present")
        return 0
    else:
        print("\nFAIL — some counts outside tolerance or adversarial cases missing")
        return 1


if __name__ == "__main__":
    sys.exit(main())
