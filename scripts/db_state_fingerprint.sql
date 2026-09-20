-- cut-040R-2 P1' DB state fingerprint
-- Deterministic hash over exactly the state E2 depends on:
--   * entities: identity-bearing columns + the attributes E2 reads
--     (department, is_management, roles)
--   * acl_entries: the whole table
-- Ordering is part of the hash (ORDER BY row_text) so row order cannot hide a diff.
SELECT md5(string_agg(row_text, E'\n' ORDER BY row_text)) AS db_state_fingerprint
FROM (
    SELECT display_id || '|' || entity_type || '|' || name || '|'
           || coalesce(source_system, '') || '|' || coalesce(source_id, '') || '|'
           || coalesce(attributes->>'department', '') || '|'
           || coalesce(attributes->>'is_management', '') || '|'
           || coalesce((attributes->'roles')::text, '') AS row_text
    FROM entities
    UNION ALL
    SELECT subject_type || '|' || subject_ref || '|' || object_type || '|'
           || object_ref || '|' || effect || '|'
           || coalesce(source_system, '') || '|'
           || coalesce(valid_from::text, '') || '|'
           || coalesce(valid_to::text, '')
    FROM acl_entries
) t;
