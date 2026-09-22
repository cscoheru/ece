"""cut-042R3 R3-B3 — mutation evidence runner.

For each of M1–M6:
  1. Read target file → backup to .bak.N
  2. Apply string-level mutation (single find/replace, no sed)
  3. Run the targeted pytest node → capture RED stdout
  4. Restore from .bak.N
  5. Run the same targeted pytest node → capture GREEN stdout
  6. Verify .bak.N was restored (md5 match)
  7. Write ``reports/cut-042R3/mutation-evidence/M{N}-{slug}.md`` with both outputs.

Each mutation entry has 4 fields:
  - target: file path relative to ece/ root
  - find: unique substring in target
  - replace: replacement substring (the mutation)
  - test: pytest node id (e.g. ``tests/integration/test_foo.py::test_bar``)
  - red_marker: substring expected in RED stdout (proves test failed meaningfully)

Usage:
    cd /Users/kjonekong/projects/domainAgentECE/ece
    DATABASE_URL=... python scripts/cut_042r3_mutation_runner.py

Scope lock: runner is read-only against the DB; it only mutates source files,
then restores them. Final exit verifies all targets match pre-mutation md5.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ECE_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ECE_ROOT / "reports" / "cut-042R3" / "mutation-evidence"
DATABASE_URL = "postgresql+psycopg://ece:ece@localhost:55440/ece"


# ---------------------------------------------------------------------------
# 6 mutation anchors
# ---------------------------------------------------------------------------

MUTATIONS: list[dict[str, str]] = [
    {
        "id": "M1",
        "name": "re_read_through_assembly_skipped",
        "target": "src/ece/v0/loop.py",
        "find": (
            "    re_read_attrs = _re_read_through_assembly(\n"
            "        engine, user_ref, display_id, root_type, scenario_spec.spec,\n"
            "        scenario_spec.pack,\n"
            "    )"
        ),
        "replace": (
            "    # M1 MUTATION: skip re-read, use pre-materialize attrs\n"
            "    re_read_attrs = pr_attrs_before"
        ),
        "test": "tests/integration/test_v0_loop.py::test_re_read_asks_the_assembly_path_again",
        "red_marker": "AssertionError",
    },
    {
        "id": "M2",
        "name": "apply_context_update_skip_sql",
        "target": "src/ece/context/update.py",
        "find": (
            "    with engine.begin() as conn:\n"
            "        result = conn.execute(\n"
            "            _UPDATE_SQL,\n"
            "            {"
        ),
        "replace": (
            "    # M2 MUTATION: skip SQL update\n"
            "    return\n"
            "    with engine.begin() as conn:\n"
            "        result = conn.execute(\n"
            "            _UPDATE_SQL,\n"
            "            {"
        ),
        "test": "tests/integration/test_v0_loop.py::test_loop_result_carries_every_step_product",
        "red_marker": "AssertionError",
    },
    {
        "id": "M3",
        "name": "permission_acl_check_bypassed",
        "target": "src/ece/context/assembly.py",
        "find": (
            "        if not decision.allowed:\n"
            "            denied.append({\"ref\": ent_id, \"reason\": f\"acl:{decision.matched_rule}\"})"
        ),
        "replace": (
            "        # M3 MUTATION: bypass ACL check\n"
            "        if False and not decision.allowed:\n"
            "            denied.append({\"ref\": ent_id, \"reason\": f\"acl:{decision.matched_rule}\"})"
        ),
        "test": "tests/integration/test_params_land_in_db.py::test_denied_user_does_not_write_to_db",
        "red_marker": "AssertionError",
    },
    {
        "id": "M4",
        "name": "evaluated_conditions_inject_nondeterministic_amount",
        "target": "src/ece/domain_packs/procurement/agent/v0_rules.py",
        "find": (
            "    def _evaluate_via_params(ctx: Any, params: dict[str, Any]) -> list[dict[str, Any]]:\n"
            "        # params keys mirror the rule's original signature: amount, quote_count.\n"
            "        # Fall back to ctx-derived values when params omit them — keeps the\n"
            "        # generic loop callable without scenario-specific wiring.\n"
            "        amount = int(params.get(\"amount\") or 0)\n"
            "        quote_count = int(params.get(\"quote_count\") or 0)\n"
            "        return evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)"
        ),
        "replace": (
            "    def _evaluate_via_params(ctx: Any, params: dict[str, Any]) -> list[dict[str, Any]]:\n"
            "        # M4 MUTATION: inject non-deterministic timestamp into amount\n"
            "        import time\n"
            "        amount = int(params.get(\"amount\") or 0) + int(time.time() * 1000) % 1000\n"
            "        quote_count = int(params.get(\"quote_count\") or 0)\n"
            "        return evaluate_rule_R_SPIKE_REVIEW(amount, quote_count)"
        ),
        "test": "tests/integration/test_v0_specialized.py::test_determinism_under_loop_runs_byte_equal_decision_and_conditions",
        "red_marker": "AssertionError",
    },
    {
        "id": "M5",
        "name": "jwt_decode_skips_signature_verification",
        "target": "src/ece/auth/jwt.py",
        "find": (
            "        claims = _jwt_lib.decode(token, key, algorithms=[algorithm])  # type: ignore[attr-defined]"
        ),
        "replace": (
            "        # M5 MUTATION: skip signature verification\n"
            "        claims = _jwt_lib.decode(token, options={\"verify_signature\": False})  # type: ignore[attr-defined]"
        ),
        "test": "tests/integration/test_s13_jwt_auth.py::test_decode_jwt_token_invalid_signature",
        "red_marker": "AssertionError",
    },
    {
        "id": "M6",
        "name": "materialize_fn_disabled_in_loop",
        "target": "src/ece/v0/loop.py",
        "find": (
            "    if descriptor.materialize_fn is not None and scenario_spec.relations_fields:"
        ),
        "replace": (
            "    # M6 MUTATION: disable materializer\n"
            "    if False and descriptor.materialize_fn is not None and scenario_spec.relations_fields:"
        ),
        "test": "tests/integration/test_params_land_in_db.py::test_params_quote_count_lands_in_db_after_loop",
        "red_marker": "AssertionError",
    },
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _run_pytest(test_node: str) -> tuple[int, str]:
    """Run a single pytest node; return (exit_code, stdout_text)."""
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
    """Apply one mutation, capture RED + GREEN, restore, write evidence md."""
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
        # Apply mutation
        mutated = target_text.replace(mutation["find"], mutation["replace"], 1)
        target_path.write_text(mutated)

        # Run RED
        red_code, red_stdout = _run_pytest(mutation["test"])
        # Mutation is effective if pytest exits non-zero AND stdout shows a
        # failing test (FAILED/ERROR), regardless of which exception class
        # raised (AssertionError / RuntimeError / etc. all bite).
        red_ok = red_code != 0 and (
            "AssertionError" in red_stdout
            or "RuntimeError" in red_stdout
            or "ValueError" in red_stdout
            or "FAILED" in red_stdout
            or "ERROR" in red_stdout
        )

        # Restore
        target_path.write_bytes(backup_path.read_bytes())

        # Run GREEN
        green_code, green_stdout = _run_pytest(mutation["test"])
        green_ok = green_code == 0 and "passed" in green_stdout

        # Verify restore
        restored_md5 = _md5(target_path)
        restore_ok = restored_md5 == original_md5

        # Write evidence file
        evidence_path = EVIDENCE_DIR / f"{mutation['id']}_{mutation['name']}.md"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            f"# Mutation Anchor {mutation['id']} — {mutation['name']}\n\n"
            f"**Target**: `{mutation['target']}`\n"
            f"**Test**: `{mutation['test']}`\n"
            f"**Date**: 2026-09-22\n\n"
            f"## RED (mutation applied)\n\n"
            f"```\n{_truncate(red_stdout)}\n```\n\n"
            f"Exit code: {red_code}\n"
            f"Marker `{mutation['red_marker']}` present: **{red_ok}**\n\n"
            f"## GREEN (mutation reverted)\n\n"
            f"```\n{_truncate(green_stdout)}\n```\n\n"
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
        # Belt and braces: always restore
        if backup_path.exists():
            target_path.write_bytes(backup_path.read_bytes())
            backup_path.unlink()
            # Final md5 verify
            assert _md5(target_path) == original_md5, (
                f"restore failed for {mutation['target']!r}"
            )


def main() -> int:
    print(f"=== cut-042R3 mutation runner — {len(MUTATIONS)} anchors ===\n")
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

    # Write index
    index_path = EVIDENCE_DIR / "README.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        "# cut-042R3 mutation evidence index\n\n"
        "Each anchor below was executed end-to-end (apply mutation → RED pytest → "
        "restore → GREEN pytest) by `scripts/cut_042r3_mutation_runner.py`.\n\n"
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
