# cut-042R3 mutation evidence index

Each anchor below was executed end-to-end (apply mutation → RED pytest → restore → GREEN pytest) by `scripts/cut_042r3_mutation_runner.py`.

| Anchor | Name | Status | Evidence |
|--------|------|--------|----------|
| M1 | re_read_through_assembly_skipped | OK | `reports/cut-042R3/mutation-evidence/M1_re_read_through_assembly_skipped.md` |
| M2 | apply_context_update_skip_sql | OK | `reports/cut-042R3/mutation-evidence/M2_apply_context_update_skip_sql.md` |
| M3 | permission_acl_check_bypassed | OK | `reports/cut-042R3/mutation-evidence/M3_permission_acl_check_bypassed.md` |
| M4 | evaluated_conditions_inject_nondeterministic_amount | OK | `reports/cut-042R3/mutation-evidence/M4_evaluated_conditions_inject_nondeterministic_amount.md` |
| M5 | jwt_decode_skips_signature_verification | OK | `reports/cut-042R3/mutation-evidence/M5_jwt_decode_skips_signature_verification.md` |
| M6 | materialize_fn_disabled_in_loop | OK | `reports/cut-042R3/mutation-evidence/M6_materialize_fn_disabled_in_loop.md` |
