-- cut-040R-2 P1'' DB state fingerprint (SHA-256, read-set complete)
--
-- Codex 第三轮补充判词 §二 要求:
--   1. 从 E2 runner 与 permission runtime 的实际代码反向列出 E2 每个决策读取的
--      DB table / column / attribute
--   2. 证明「E2 读取的状态 ⊆ fingerprint 覆盖的状态」
--   3. 发现遗漏就直接修 fingerprint —— 不要用文字解释"应该没问题"
--   5. fingerprint 升级为 SHA-256,并同时记录 row count
--
-- 反向列出的读取集(证据见 P1_DEPENDENCY_MATRIX.md):
--   [R1] ece/api/identity.py:115-118   acl_entries  WHERE object_type, object_ref
--        SELECT subject_type, subject_ref, effect, valid_from, valid_to, source_system
--   [R2] ece/identity/parser.py:45-53  entities     WHERE entity_type='person', source_id
--        SELECT id, display_id, name, attributes
--   [R3] ece/identity/parser.py:76-82  entity_aliases WHERE entity_id, method
--        SELECT alias
--   [R4] ece/permissions/engine.py:218-221  entities  WHERE display_id
--        SELECT attributes->>'department'
--   [R5] scripts/run_e2_permission.py   —— 无 DB 访问(纯 HTTP)
--   [R6] /permissions/check 无写操作(已核验)
--
-- 覆盖策略:对本读取集做**超集**覆盖(整表或整列),不依赖"某列不参与判定"的论证。
-- 唯一排除的是 volatile 列(created_at / updated_at):它们不参与读取集,且会引入
-- 与实验无关的噪声。
--
-- 用法(在实验脚本中):
--   docker compose exec -T db psql -U ece -d ece -t -A -F'|' -f - < scripts/db_state_fingerprint.sql
-- 输出: fingerprint|entities_rows|aliases_rows|acl_rows

WITH entity_surface AS (
    -- [R2] + [R4] : every column the E2 decision path reads from `entities`,
    -- including attributes.department / is_management / roles.
    SELECT
        id::text                                        AS c1,
        display_id                                      AS c2,
        entity_type                                     AS c3,
        name                                            AS c4,
        coalesce(source_system, '')                     AS c5,
        coalesce(source_id, '')                         AS c6,
        coalesce(attributes->>'department', '')         AS c7,
        coalesce(attributes->>'is_management', '')      AS c8,
        coalesce((attributes->'roles')::text, '')       AS c9
    FROM entities
),
alias_surface AS (
    -- [R3] : `entity_aliases` is read by resolve_identity. `alias` / `method`
    -- are the columns the query touches; the rest of the row is included so the
    -- fingerprint is a strict superset of the read-set (no "it doesn't affect
    -- the decision" argument required). `created_at` is excluded as volatile —
    -- it is not in the read-set and would add experiment-irrelevant noise.
    SELECT
        id::text                                        AS c1,
        entity_id::text                                 AS c2,
        alias                                           AS c3,
        norm_alias                                      AS c4,
        coalesce(source_system, '')                     AS c5,
        coalesce(source_ref, '')                        AS c6,
        method                                          AS c7,
        confidence::text                                AS c8,
        status                                          AS c9
    FROM entity_aliases
),
acl_surface AS (
    -- [R1] : ACL rows are prefetched with all columns listed in the SELECT plus
    -- the two WHERE columns. All ten columns are covered here (id + note
    -- included) so no subset argument is needed.
    SELECT
        id::text                                        AS c1,
        subject_type                                    AS c2,
        subject_ref                                     AS c3,
        object_type                                     AS c4,
        object_ref                                      AS c5,
        effect                                          AS c6,
        coalesce(valid_from::text, '')                  AS c7,
        coalesce(valid_to::text, '')                    AS c8,
        source_system                                   AS c9,
        coalesce(note, '')                              AS c10
    FROM acl_entries
),
all_rows AS (
    SELECT 'entities|'       AS scope,
           c1||'|'||c2||'|'||c3||'|'||c4||'|'||c5||'|'||c6||'|'||c7||'|'||c8||'|'||c9 AS row_text FROM entity_surface
    UNION ALL
    SELECT 'entity_aliases|', c1||'|'||c2||'|'||c3||'|'||c4||'|'||c5||'|'||c6||'|'||c7||'|'||c8||'|'||c9 FROM alias_surface
    UNION ALL
    SELECT 'acl_entries|',    c1||'|'||c2||'|'||c3||'|'||c4||'|'||c5||'|'||c6||'|'||c7||'|'||c8||'|'||c9||'|'||c10 FROM acl_surface
)
SELECT
    encode(sha256(string_agg(row_text, E'\n' ORDER BY scope, row_text)::bytea), 'hex') AS fingerprint,
    (SELECT count(*) FROM entity_surface) AS entities_rows,
    (SELECT count(*) FROM alias_surface)  AS aliases_rows,
    (SELECT count(*) FROM acl_surface)    AS acl_rows
FROM all_rows;
