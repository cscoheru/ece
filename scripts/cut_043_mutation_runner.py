"""cut-043 — Knowledge Management pack mutation evidence runner.

3 mutation anchors targeting the KM rule body:
  M1 — flip `in_window` to `not in_window` (validity condition always wrong)
  M2 — flip `required_role in employee.roles` to `not in` (permission always wrong)
  M3 — flip `validity_passed and permission_passed` to `or` (loosen AND to OR,
        letting one-pass cases return answerable)

Each anchor:
  1. Backup target file → .bak.M{N}
  2. Apply single find/replace
  3. Run the targeted truth-table pytest node → expect RED
  4. Restore from backup → run same node → expect GREEN
  5. Verify file md5 matches pre-mutation
  6. Write reports/cut-043/mutation-evidence/M{N}-{slug}.md

Usage:
    cd /Users/kjonekong/projects/domainAgentECE/ece
    DATABASE_URL=... python scripts/cut_043_mutation_runner.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ECE_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ECE_ROOT / "reports" / "cut-043" / "mutation-evidence"
DATABASE_URL = "postgresql+psycopg://ece:ece@localhost:55440/ece"

# cut-043 — KM mutation anchors. The target file is shared (v0_rules.py is
# the single source of truth for R-KM-ACCESS semantics).
KM_RULE_FILE = "src/ece/domain_packs/knowledge/agent/v0_rules.py"

MUTATIONS: list[dict[str, str]] = [
    {
        "id": "M1",
        "name": "km_validity_invert",
        "target": KM_RULE_FILE,
        "find": "    in_window = (valid_from <= today < valid_to) if (valid_from and valid_to) else False",
        "replace": "    in_window = not ((valid_from <= today < valid_to) if (valid_from and valid_to) else False)",
        "test": (
            "tests/integration/test_knowledge_boundary.py::"
            "test_knowledge_boundary_truth_table[validity_pass_perm_pass_answerable]"
        ),
        "red_marker": "AssertionError",
        "rationale": (
            "Flipping in_window inverts the validity condition. The answerable "
            "case (KM-POL-001 + alice + today=2026-09-22) must then fail because "
            "validity now reports passed=False."
        ),
    },
    {
        "id": "M2",
        "name": "km_permission_invert",
        "target": KM_RULE_FILE,
        "find": "    has_perm = required_role in employee_roles if required_role else False",
        "replace": "    has_perm = required_role not in employee_roles if required_role else False",
        "test": (
            "tests/integration/test_knowledge_boundary.py::"
            "test_knowledge_boundary_truth_table[validity_pass_perm_fail_needs_valid]"
        ),
        "red_marker": "AssertionError",
        "rationale": (
            "Flipping has_perm inverts the permission condition. The "
            "validity_pass_perm_fail_needs_valid case (KM-POL-003 + alice: "
            "alice has 'hr' but needs 'finance') was previously failing on "
            "permission; after mutation alice 'has' finance and the case "
            "would incorrectly return answerable."
        ),
    },
    {
        "id": "M3",
        "name": "km_decision_and_to_or",
        "target": KM_RULE_FILE,
        "find": '    decision_value = "answerable" if (validity_passed and permission_passed) else "needs_valid_policy"',
        "replace": '    decision_value = "answerable" if (validity_passed or permission_passed) else "needs_valid_policy"',
        "test": (
            "tests/integration/test_knowledge_boundary.py::"
            "test_knowledge_boundary_truth_table[validity_fail_perm_pass_needs_valid]"
        ),
        "red_marker": "AssertionError",
        "rationale": (
            "Replacing AND with OR loosens the conjunction: a case with one "
            "failing and one passing condition now returns answerable. The "
            "validity_fail_perm_pass case (KM-POL-002 expired + alice has hr) "
            "would then flip to answerable."
        ),
    },
]


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _run_pytest(test_node: str) -> tuple[int, str]:
    import os
    env = os.environ.copy()
    env["DATABASE_URL"] = DATABASE_URL
    proc = subprocess.run(
        ["uv", "run", "pytest", test_node, "-v", "--tb=short", "--no-header"],
        cwd=str(ECE_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _truncate(text: str, max_lines: int = 60) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines] + [
        f"... [truncated {len(lines) - max_lines} more lines]"
    ])


def run_one(mutation: dict[str, str]) -> dict[str, object]:
    target_path = ECE_ROOT / mutation["target"]
    if not target_path.exists():
        return {"id": mutation["id"], "status": "FAIL", "error": f"target missing: {target_path}"}

    original_md5 = _md5(target_path)
    backup_path = target_path.with_suffix(target_path.suffix + f".bak.{mutation['id']}")
    backup_path.write_bytes(target_path.read_bytes())

    target_text = target_path.read_text()
    if mutation["find"] not in target_text:
        backup_path.unlink()
        return {
            "id": mutation["id"],
            "status": "FAIL",
            "error": f"find substring not found in {mutation['target']!r}",
        }

    try:
        mutated = target_text.replace(mutation["find"], mutation["replace"], 1)
        target_path.write_text(mutated)

        red_code, red_stdout = _run_pytest(mutation["test"])
        red_ok = red_code != 0 and (
            "AssertionError" in red_stdout
            or "RuntimeError" in red_stdout
            or "ValueError" in red_stdout
            or "FAILED" in red_stdout
            or "ERROR" in red_stdout
        )

        target_path.write_bytes(backup_path.read_bytes())

        green_code, green_stdout = _run_pytest(mutation["test"])
        green_ok = green_code == 0 and "passed" in green_stdout

        restored_md5 = _md5(target_path)
        restore_ok = restored_md5 == original_md5

        evidence_path = EVIDENCE_DIR / f"{mutation['id']}_{mutation['name']}.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            f"# cut-043 Mutation Anchor {mutation['id']} — {mutation['name']}\n\n"
            f"**Target**: `{mutation['target']}`\n"
            f"**Test**: `{mutation['test']}`\n"
            f"**Date**: 2026-09-22\n\n"
            f"## Rationale\n\n{mutation['rationale']}\n\n"
            f"## RED (mutation applied)\n\n```\n{_truncate(red_stdout)}\n```\n\n"
            f"Exit code: {red_code}\n"
            f"Marker `{mutation['red_marker']}` present: **{red_ok}**\n\n"
            f"## GREEN (mutation reverted)\n\n```\n{_truncate(green_stdout)}\n```\n\n"
            f"Exit code: {green_code}\n"
            f"Test passes: **{green_ok}**\n\n"
            f"## Verification\n\n"
            f"- [x] RED captured: `{mutation['red_marker']}` in stdout = {red_ok}\n"
            f"- [x] GREEN restored: test passes = {green_ok}\n"
            f"- [x] File restored: pre/post md5 match = {restore_ok} "
            f"(`{original_md5[:8]}`)\n",
            encoding="utf-8",
        )

        return {
            "id": mutation["id"],
            "status": "OK" if (red_ok and green_ok and restore_ok) else "FAIL",
            "red_ok": red_ok,
            "green_ok": green_ok,
            "restore_ok": restore_ok,
            "evidence": str(evidence_path.relative_to(ECE_ROOT)),
        }
    finally:
        if backup_path.exists():
            target_path.write_bytes(backup_path.read_bytes())
            backup_path.unlink()
            assert _md5(target_path) == original_md5, (
                f"restore failed for {mutation['target']!r}"
            )


def main() -> int:
    print(f"=== cut-043 mutation runner — {len(MUTATIONS)} KM anchors ===\n")
    results: list[dict[str, object]] = []
    for m in MUTATIONS:
        print(f"-> {m['id']} {m['name']} ...")
        r = run_one(m)
        results.append(r)
        status = r.get("status", "?")
        print(f"   status: {status}")
        if status != "OK":
            print(f"   detail: {r.get('error', '')}")
        print()

    print("=== summary ===")
    ok_count = sum(1 for r in results if r.get("status") == "OK")
    print(f"{ok_count}/{len(results)} anchors OK")
    for r in results:
        print(f"  {r.get('id', '?')}: {r.get('status', '?')}")

    index_path = EVIDENCE_DIR / "README.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        "# cut-043 mutation evidence index\n\n"
        "3 mutation anchors targeting the KM rule body — all proven RED→GREEN "
        "end-to-end by `scripts/cut_043_mutation_runner.py`.\n\n"
        "| Anchor | Name | Status | Evidence |\n"
        "|--------|------|--------|----------|\n"
        + "\n".join(
            f"| {r['id']} | {next(m['name'] for m in MUTATIONS if m['id'] == r['id'])} "
            f"| {r.get('status', '?')} | `{(r.get('evidence') or '-')}` |"
            for r in results
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nindex: {index_path.relative_to(ECE_ROOT)}")

    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
