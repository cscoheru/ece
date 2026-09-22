# cut-042R2 mutation anchors — six anchors verified

| Anchor | Mutation | Test that bites | Status |
|--------|----------|-----------------|--------|
| M1 | `_re_read_through_assembly` returns `pr_attrs_before` (skip re-read) | `test_re_read_asks_the_assembly_path_again` | BITTEN ✅ |
| M2 | `apply_context_update` returns review_status without SQL | `test_loop_result_carries_every_step_product` | BITTEN ✅ |
| M3 | Bypass `assemble_context` permission filter via raw SQL | `test_denied_user_does_not_write_to_db` (R2-F1 NEW) | BITTEN ✅ |
| M4 | `reason` includes time.strftime (non-deterministic) | `test_decision_reason_is_byte_equal_across_runs` | BITTEN ✅ |
| M5 | Open JWT with `alg=none` | `test_decode_jwt_token_invalid_signature` | BITTEN ✅ |
| **M6** (NEW) | Skip `materialize_fn` call in loop step [3b] | `test_params_quote_count_lands_in_db_after_loop` | BITTEN ✅ |

M1–M5 are inherited from cut-042R (see `reports/cut-042R-report.md` §10 for full mutation descriptions).
M6 is the new R2-F2 mutation — see [M6_F2_materializer_disabled.md](./M6_F2_materializer_disabled.md).