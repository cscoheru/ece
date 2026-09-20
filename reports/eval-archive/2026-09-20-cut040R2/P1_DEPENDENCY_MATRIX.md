# P1_DEPENDENCY_MATRIX.md — E2 读取集 ⊆ 指纹覆盖集

> Date: 2026-09-20
> 依据: Codex 第三轮补充判词 §二
> 目的: 独立证明 `scripts/db_state_fingerprint.sql` **覆盖了 E2 每个决策实际读取的全部 DB 状态**
> 结论: **✅ 覆盖成立**（发现 3 处初始遗漏, 已修指纹 —— 未使用"应该没问题"式论证）

---

## 0. 方法

1. 从 `/permissions/check` 端点出发, 沿调用链向下**逐层列出**每一个 DB 读取点。
2. 记录每个读取点的 **表 / 列 / WHERE 条件**。
3. 对照 `db_state_fingerprint.sql` 的覆盖范围, 逐项判定。
4. **发现遗漏即修指纹**（不解释、不豁免）。

---

## 1. E2 决策链的完整追踪

```
scripts/run_e2_permission.py
    │  HTTP POST /api/v1/permissions/check   ← 【R5】本文件 0 处 DB 访问
    │                                            (grep get_engine|sqlalchemy|psycopg = 0)
    ▼
src/ece/api/identity.py :: permissions_check
    │
    ├─► identity = resolve_identity(engine, user_ref)
    │       │
    │       ├─ [R2] SELECT id, display_id, name, attributes
    │       │        FROM entities
    │       │        WHERE entity_type='person' AND source_id=:sid
    │       │        LIMIT 1
    │       │        （identity.py:83 → parser.py:44-58）
    │       │
    │       └─ [R3] SELECT alias FROM entity_aliases
    │                WHERE entity_id=:eid AND method IN ('api-header','manual')
    │                （parser.py:75-83）
    │
    ├─► acl_entries = SELECT subject_type, subject_ref, effect,
    │                        valid_from, valid_to, source_system
    │                  FROM acl_entries
    │                  WHERE object_type=:otype AND object_ref=:oref
    │       【R1】（identity.py:114-120）
    │
    └─► decision = check_permission(identity, ..., acl_entries, engine)
            │
            ├─ identity.department       ← 来自 [R2] 的 attributes
            ├─ identity.roles            ← 来自 [R2] 的 attributes
            ├─ identity.is_management    ← 来自 [R2] 的 attributes
            ├─ identity.user_ref         ← 来自请求体, 非 DB
            ├─ acl_entries               ← 来自 [R1]
            │
            └─ [R4] SELECT attributes->>'department' FROM entities
                     WHERE display_id = :d
                    （engine.py:218-222, 仅 allow_dept 分支调用）

【R6】/permissions/check 无写操作 —— 整个函数体内无 INSERT/UPDATE/DELETE
      （已核验: identity.py permissions_check 中仅 1 处 conn.execute, 即 [R1] 的 SELECT）
```

---

## 2. 依赖矩阵

| # | E2 决策依赖 | 表 | 列 / 属性 | WHERE 条件 | 指纹覆盖 | 证据 |
|---|---|---|---|---|---|---|
| R1 | ACL 判定行 | `acl_entries` | `subject_type`, `subject_ref`, `effect`, `valid_from`, `valid_to`, `source_system` | `object_type`, `object_ref` | ✅ **全部 10 列**（含 `id` / `note`，超集） | `identity.py:114-120` |
| R2a | 身份行存在性 | `entities` | `entity_type`, `source_id` | 同左 | ✅ | `parser.py:44-53` |
| R2b | `identity.display_id` | `entities` | `display_id` | — | ✅ | 同上 |
| R2c | `identity.name` | `entities` | `name` | — | ✅ | 同上 |
| R2d | `identity.department` | `entities` | `attributes->>'department'` | — | ✅ | 同上 |
| R2e | `identity.roles` | `entities` | `attributes->'roles'` | — | ✅ | 同上 |
| R2f | `identity.is_management` | `entities` | `attributes->>'is_management'` | — | ✅ | `parser.py:88` |
| R2g | 行标识 | `entities` | `id` (uuid) | — | ✅ **（本轮新增）** | 同上 |
| R3 | `identity.aliases` | `entity_aliases` | `alias`, `method`, `entity_id` | 同左 | ✅ **（本轮新增）** | `parser.py:75-83` |
| R4 | 对象部门 | `entities` | `display_id`, `attributes->>'department'` | `display_id` | ✅ | `engine.py:218-222` |
| R5 | — | — | — | — | n/a | `run_e2_permission.py` 无 DB 访问 |
| R6 | — | — | — | — | n/a | 无写操作 |

**判定: E2 读取的状态 ⊆ 指纹覆盖的状态 —— ✅ 成立。**

---

## 3. 本轮发现并修复的 3 处遗漏

Codex 要求「发现遗漏就直接修 fingerprint —— 不要用文字解释『应该没问题』」。
初版指纹（md5）确实有 3 处缺口:

| # | 遗漏 | 初版指纹 | 处置 |
|---|---|---|---|
| 1 | **`entity_aliases` 整表** | ❌ 未覆盖 | **[R3] 被 `resolve_identity` 读取**（虽然 `check_permission` 不消费 `identity.aliases`，但按 Codex 原则不依赖"不影响判定"的论证）→ **已加入，9 列全覆盖** |
| 2 | **`entities.id`** | ❌ 未覆盖 | **[R2] 被选中并返回为 `entity_id`** → **已加入** |
| 3 | **`acl_entries.id` / `note`** | ❌ 未覆盖 | 虽不在 SELECT 列表内，但按超集原则 → **已加入**（现为全 10 列） |

**同时升级**: md5 → **SHA-256**（`encode(sha256(...), 'hex')`）。
**并输出行数**，使审查者能看到覆盖规模:

```
<sha256>|<entities_rows>|<aliases_rows>|<acl_rows>
```

**唯一排除**: `entity_aliases.created_at`（volatile，不在读取集内，会引入与实验无关的噪声）。
该排除已在 SQL 注释中写明 —— 是**显式声明**而非静默忽略。

---

## 4. 指纹实现的两个额外保证

1. **有序**: `string_agg(row_text, E'\n' ORDER BY scope, row_text)`
   → 行顺序变化也会改变指纹，不会因排序掩盖差异。
2. **作用域前缀**: 每行带 `entities|` / `entity_aliases|` / `acl_entries|`
   → 跨表内容相同的行不会互相抵消。

---

## 5. 实验参数（与 `single-variable-v2/EXPERIMENT_RECORD.txt` 一致）

| 项 | 值 |
|---|---|
| **F0**（两臂开始前） | `13f4b221ebe3daaff2e69d68aada51a91ce14894907f37070bd860832340b2b6\|435\|1\|3` |
| **F1**（ARM A 结束后） | 同上（逐字符相同） |
| **F2**（ARM B 结束后） | 同上（逐字符相同） |
| baseline commit | `c92316370b87343ba76c5776f9d56eb05e3f7be3` |
| fixed commit | `32a0b920b014c50543c92d826b00c262f11def9b` |
| dataset | `data/eval/e2_permission.json` |
| dataset sha256 | `7f82340adcbca4118aae51ad20090a0c40fd75f8301e1e7cd59c2a9d5ca9670c` |
| runtime（两臂相同） | 宿主 uvicorn（同 venv） |
| DATABASE_URL | `postgresql+psycopg://ece:ece@localhost:5432/ece`（默认值） |
| ARM A exit code | **2**（4 暴露 + 4 失败） |
| ARM B exit code | **0**（0 / 0） |

**复现**: `bash scripts/run_p1_single_variable_experiment.sh`

---

## 6. 证据等级声明（措辞纪律）

> ⚠️ **不使用「严格因果证明」表述。**
> 本实验的证据类型是 **可审计、可复现的实验控制**，不是密码学意义上的绝对证明。
>
> **已证明**: 固定 DB state + 固定 dataset + 相同 runtime 下，
> baseline/fixed **runtime 代码**的差异使 E2 由 4/4 变为 0/0。
> **未测量**: seed/数据层修复（RC-6/7/9）各自的贡献 —— 两者在两臂中被『共享』而非『对照』。
> **若需回答未测量部分**: 增设第三臂（baseline 代码 + baseline seed 产出的 DB）。本轮不必要。

---

**Author**: Claude（Fable 5.1）
**Date**: 2026-09-20
