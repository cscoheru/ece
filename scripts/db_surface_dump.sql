-- cut-040R-2 DB surface dump (unhashed, one row per line, ordered)
-- 与 db_state_fingerprint.sql 覆盖同一读取集, 但不做哈希 —— 用于**逐行 diff**,
-- 定位指纹变化的确切来源。
--
-- 用法:
--   docker compose exec -T db psql -U ece -d ece -t -A -f - < scripts/db_surface_dump.sql
SELECT 'entities|'||id::text||'|'||display_id||'|'||entity_type||'|'||name||'|'
       ||coalesce(source_system,'')||'|'||coalesce(source_id,'')||'|'
       ||coalesce(attributes->>'department','')||'|'
       ||coalesce(attributes->>'is_management','')||'|'
       ||coalesce((attributes->'roles')::text,'')
FROM entities
UNION ALL
SELECT 'entity_aliases|'||id::text||'|'||entity_id::text||'|'||alias||'|'||norm_alias||'|'
       ||coalesce(source_system,'')||'|'||coalesce(source_ref,'')||'|'||method||'|'
       ||confidence::text||'|'||status
FROM entity_aliases
UNION ALL
SELECT 'acl_entries|'||id::text||'|'||subject_type||'|'||subject_ref||'|'||object_type||'|'
       ||object_ref||'|'||effect||'|'||coalesce(valid_from::text,'')||'|'
       ||coalesce(valid_to::text,'')||'|'||source_system||'|'||coalesce(note,'')
FROM acl_entries
ORDER BY 1;
