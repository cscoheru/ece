# eval-archive / 2026-09-20-cut040R2

cut-040R-2 收口实测归档。**全部数字由 CC 亲跑,raw stdout 原样落盘。**

## 目录

| 目录 | 内容 |
|---|---|
| `baseline-seeded/` | **改前基线**(数据完好态):E1–E5 原始 stdout |
| `fixed/` | **改后**:E1/E2/E3/E4/E5 + 全套 pytest + post-pytest E2 |

## 核心结果

### E2 权限套件(本次交付目标)

| 时点 | 结果 | 退出码 |
|---|---|---|
| 改前基线(`baseline-seeded/E2.txt`) | **5 暴露 + 5 失败**(16.4%) | 2 (FAIL) |
| 改后 · 刚 seed 完(`fixed/E2.txt`) | **0 暴露 + 0 失败**(61/61) | 0 (PASS) |
| 改后 · **跑完全套 pytest 之后**(`fixed/E2-post-pytest.txt`) | **0 暴露 + 0 失败**(61/61) | 0 (PASS) |

第三行是关键:RC-6(状态洗库)此前使 E2 在任何 pytest 之后都回到修复前水平。
post-pytest 仍全绿 = RC-6 确实修好,而非"只在干净库上好看"。

### 全套 pytest

`fixed/PYTEST.txt` — 退出码 0,**353 passed / 3 skipped / 0 failed**。

3 个 skip 全部为 `ECE_LLM_BASE_URL not set`(LLM 依赖,预期)。

与 cut-040R 的 CI 签名 `349P/5S/3D` 的差异,已逐条解释:

| 项 | 变化 | 原因 |
|---|---|---|
| passed | 349 → 353 (+4) | +2 = 本次新增 `test_cut040r2_state_integrity.py` 的 2 个测试;<br>+2 = E2 wrapper 测试由 skip 转为真实执行并通过(本地有 live API,CI 没有) |
| skipped | 5 → 3 (−2) | 同上:两个 E2 wrapper 测试此前在无 API 时 skip,**即 CI 的"绿但盲"** |
| deselected | 3 → 3 | `-m "not eval and not eval_llm"` 过滤,不变 |

### E1 实体消歧

`fixed/E1.txt` — **95.4%(62/65)**,≥95% 达标,但**低于修复前的 98.5%**。

**这是测试污染,不是代码回归。已定位到根因:**

- 全库仅 2 个重名实体:`R4-Acme` ×5、`R4-Globex` ×5。
- E1 的 2 个新增失败(`e1-002` / `e1-003`)的 mention **正好就是这两个**。
- 成因:某些测试以 `csv:r4-test-<uuid>` 为 `source_system` 创建同名供应商,每次运行产生新 UUID →
  `ON CONFLICT` 永不命中 → 同名实体无界累积 → 解析器看到 5 个同置信度候选 →
  按"歧义不猜"规则判 `resolved=False`。
- `e1-054`(无限极)是**修复前就存在**的基线失败(该名字重名份数 = 1),与本次改动无关。

**结论**:E1 指标**非 hermetic** —— 重复跑测试会单调压低消歧率。这是一处独立缺陷(未修,不在本次范围)。

### E3 / E4 / E5(未修,R40R2.7 不在本次范围)

| 套件 | 状态 |
|---|---|
| E3 Context | 崩溃 `'ContextPackage' object has no attribute 'get'` |
| E4 Relationships | 同上 |
| E5 Temporal | 0.0%(`'str' object has no attribute 'isoformat'`) |

根因已由 Cline 定位(runner 从 HTTP 改写为直调 Python 时,假设返回 dict)。
修复很小(每处约 2 行),属 R40R2.7,**本次未做**。

## 第二轮判词落实: P1 / P2 (2026-09-20)

Codex 第二轮判词要求补两项测试卫生工作。两项均已完成并验证。

### P1 — 严格单变量实验（`single-variable/`，已被 `single-variable-v2/` 取代）

> ⚠️ **本节的结论口径已于 Codex 第三轮判词后被修正。以 `single-variable-v2/` 为准。**

判词指出原对照组**同时改变了代码与数据集**,因此"5 暴露 → 0 暴露"不是纯代码效果。
本实验固定数据集(一律用**新** `e2_permission.json`),只变代码:

| 组 | 源码 | 数据集 | 结果 | 退出码 |
|---|---|---|---|---|
| 对照 | `037260b~1`(baseline,宿主 uvicorn :8766) | 新 | **4 暴露 + 4 失败**(13.1%) | 2 |
| 处理 | `037260b`(docker :8765) | 新 | **0 暴露 + 0 失败** | 0 |

原始 stdout: `single-variable/E2-baseline-code-NEW-dataset.txt` /
`single-variable/E2-fixed-code-NEW-dataset.txt`

> ❌ **已撤回的声明**：本节原来写"证据等级：由「可信」提升为**严格因果证明**"。
> **该声明过强。** 本实验只证明了**两臂共用同一份数据集**,**没有**证明两臂共用同一份
> **DB 状态**；而 seed/数据层面的修复(RC-6/7/9)本身就是 `037260b` 变更集的一部分,
> 两臂共用的那个 DB 状态**已经是修后的 seed 产出的**,故它是一个**未受控变量**。
> 另,两臂运行时环境不同(宿主 vs docker)。
>
> **已由 `single-variable-v2/` 补齐** —— 见下节。

**该实验顺带把「代码修复」与「数据修复」分开了**（此部分结论仍然成立）:

| 消失的 case（baseline 代码上） | 根因 | 性质 |
|---|---|---|
| e2-025 | RC-10 `restricted` 语义 | **代码** |
| e2-029 / e2-030 / e2-055 | RC-8 `is_management` 派生 | **代码** |
| e2-004 / e2-008 / e2-044 / e2-048 | RC-11 未知身份提前 deny | **代码** |

而 **e2-059 / e2-060 / e2-061(ACL 案)在 baseline 代码上同样通过** —— 因为 ACL 数据已由修后的
seed 写成域类型。这证明 **RC-9 是数据/seed 修复,不是代码修复**。

### P1' — 补齐 DB 状态证据（`single-variable-v2/`）

Codex 第三轮判词 [MAJOR]：「P1 的『严格单变量实验』目前还不能达到它声称的『严格因果证明』等级……
它没有充分证明：两组使用完全相同的数据库 state。」

**本实验补齐两点**:

1. **DB 状态指纹**(`scripts/db_state_fingerprint.sql` —— entities + acl_entries 的有序 md5),
   在两臂**之前 / 之间 / 之后**各取一次。
2. **两臂同运行时** —— 均跑宿主 uvicorn(同 venv、同 `DATABASE_URL`),
   消除原实验"宿主 vs docker"的环境差异。

| 项 | 值 |
|---|---|
| F0(开始前) | `faff49167d6781e6245dcd58ab116c10` |
| F1(ARM A 结束后) | `faff49167d6781e6245dcd58ab116c10` |
| F2(ARM B 结束后) | `faff49167d6781e6245dcd58ab116c10` |
| baseline commit | `c92316370b87343ba76c5776f9d56eb05e3f7be3` |
| fixed commit | `93ed0e307fd22f9b30b5a16314344c730bd837ff` |
| dataset sha256 | `7f82340adcbca4118aae51ad20090a0c40fd75f8301e1e7cd59c2a9d5ca9670c` |
| ARM A 退出码 | 2(4 暴露 + 4 失败) |
| ARM B 退出码 | 0(0 / 0) |

**F0 == F1 == F2 → DB 状态在两臂之间未被改动,已证明。**

**修正后的结论口径(严格)**:

> 在【固定 DB 状态】+【固定数据集】+【同一运行时】下,
> **permission RUNTIME 代码**由 baseline 改为 fixed,E2 从 4 暴露/4 失败 变为 0/0。

**本实验【不】测量的**:

> seed / 数据层面的修复(RC-6 部门注入位置、RC-7 专属对象、RC-9 ACL 词表)——
> 它们已由修后的 seed 写入 DB,两臂共用同一份,故其贡献在本设计中**恒为 0**。
> 要测量它们需另设一臂:baseline 代码 + **baseline seed 产出的 DB**。

复现: `bash scripts/run_p1_single_variable_experiment.sh`(完整记录见
`single-variable-v2/EXPERIMENT_RECORD.txt`)。

### P2 — E1 hermeticity（`fixed/E1.txt`）

**根因**: `tests/integration/test_s11_connector_ingestion.py` 为断言 `stats.created == 2`,
每轮生成 `csv:r4-test-<uuid>` 唯一来源并写入两个同名供应商(R4-Acme / R4-Globex),
**跑完不清理** → 同名实体无界累积 → E1 解析器看到 N 个同置信度候选 → 判 `resolved=False`。

**修复**: 保留唯一 source_system(断言需要),在 `finally` 中删除本轮创建的关系 / 别名 / 实体,
并加自检断言「本轮残留 = 0」。

**已清理的历史污染**: 删除 8 个累积实体(含 32 条关系),保留 SUP052 / SUP053 一对
(已提交的 E1 数据集引用这两个名字,且 `SUP052` 被 E2 的 ACL 引用)。

**验证**:

| 检查 | 结果 |
|---|---|
| 连跑 test_s11 两次 | 无新增重名,零残留 |
| 全套 pytest 后重名查询 | **0 行**(此前为 8 行) |
| **E1** | **98.5%**(64/65)—— 回到基线值 |
| 全套 pytest | 353 passed / 3 skipped / 0 failed, exit 0 |
| E2 | 仍 61/61 |

> 残留的唯一 e1 失败是 `e1-054`(mention `无限极`),**修复前即存在**,与本轮无关。

---

## 复现命令

```bash
cd ece
docker compose up -d                       # api + postgres
uv run alembic upgrade head
uv run python -m ece.seed
uv run pytest -m "not eval and not eval_llm" -q

# E2(需 live API)
uv run python scripts/run_e2_permission.py --data data/eval/e2_permission.json \
    --base-url http://127.0.0.1:8765
```

## 本次改动的 6 个根因 → 文件

| 根因 | 文件 |
|---|---|
| RC-6 状态洗库 | `src/ece/seed.py`(`seed_from_demo_json` 内注入部门) |
| RC-9 ACL 词表哑弹 | `src/ece/seed.py`(`seed_acl_entries` object_type 改域类型) |
| RC-7 数据集冲突 | `scripts/gen_eval_datasets.py` + `src/ece/seed.py`(专属对象 PR003/CON002) |
| RC-8 派生空操作 | `src/ece/identity/parser.py`(`is_management` 改显式属性) |
| RC-10 restricted 错置 | `src/ece/permissions/engine.py`(`restricted` → deny) |
| RC-11 未知身份 | `src/ece/api/identity.py`(去掉提前 deny) |
| 连带:admin 用户 | `src/ece/seed.py`(新增 `demo-user-admin`) |

## 连带修复:4 个把 bug 当契约的测试

RC-8 修好后,4 个测试失败 —— 它们**编码了 substring 派生的错误行为**:

| 测试 | 原断言 | 处置 |
|---|---|---|
| `test_s21_identity.py:59` | `is_management is True` | 改 `is False`(语义修正) |
| `test_s32_assembly.py:32` | `pkg.user["is_management"] is True` | 改 `is False` |
| `test_cut006r.py` ×2 | 用 `demo-user-procurement` 过 admin 门禁 | 改用新的 `demo-user-admin` |

后两个此前**只因为 `"procurement_manager"` 含子串 `"manager"` 才通过 POST /entities 的
management-or-admin 门禁** —— 即它们依赖的正是 RC-8 这个 bug。E2 的 4 个用户必须
**不是** management(否则 6 个 management 分类案全破),故为 ingestion 测试单设一个
显式 `admin` 角色的用户(admin ≠ management)。

---

## Final Evidence Repair (2026-09-20) — E3/E4/E5 有效性修复

Codex 最终判定:**NO-GO,但非架构 NO-GO**。架构 PASS/FREEZE,P1/P2/E1/E2 全 PASS,
唯一阻塞是 E3/E4/E5 的**评测有效性**。

### 根因(本轮查明)

| 套件 | 原结果 | 真实根因 |
|---|---|---|
| **E3** | 15.0% | `e3_context.json` 引用 `PR001…`,而 `_next_display_id` 按 max+1 分配、wipe+replay 会推移 display_id → **数据集过期** |
| **E4** | 100% | **vacuous**:边界 `[0,100]`,对象缺失(0 关系)也在带内。生成器原 note 明写 *"no relationships seeded; expect empty"* —— 它本来就是占位符 |
| **E5** | 0.0% | ① 数据集过期 ② **关系 fixture 被 wipe 摧毁且无人恢复** ③ `expected_count=5` **从未匹配实现(6)** |

### 关键发现:E5 的 expected 一直错了

`scripts/seed_relationships.py` 的 `rel_specs` 列表有 **六** 项(第 6 项带注释
`# 2nd submitter for variety`),但代码注释写"create 5"、生成器 docstring 写 5、
数据集 `expected_count` 写 5 —— **三处陈旧副本**。E5 runner 从写出来那天就崩,
所以这个错配**从未被发现**。

### 关键发现:时态语义没有问题

`docs/DATA_MODEL.md:67-68` 明写 `valid_from NULL = -∞ / valid_to NULL = +∞`,区间 `[from, to)`;
`src/ece/context/relationships.py:49-50` 的实现与之**逐字一致**。
所以 `[None,None]` = 永久有效、在任何 `as_of` 都命中 —— E5 的"0 条"从来不是时态 bug。

### 修复

| # | 修复 | 文件 |
|---|---|---|
| 1 | 关系 fixture **canonical 化**(DELETE-then-INSERT 限于自身 source_system) | `scripts/seed_relationships.py` |
| 2 | 陈旧注释 "5" → "6" + 说明 | 同上 |
| 3 | E5 `expected_rels_per_pr` 5 → **6**;E4 边界 `[0,100]` → `[6,6]` | `scripts/gen_eval_datasets.py` |
| 4 | 数据集重生成并固化为正式 artifact | `data/eval/*.json` |
| 5 | ACL 对象改为**从 DB 派生**(与生成器同算法)→ seed↔dataset 不再漂移 | `src/ece/seed.py` |
| 6 | `test_seed_relationships_test` 加 cleanup | `tests/integration/test_seed_relationships.py` |
| 7 | 两个 wipe 测试**恢复它们毁掉的 fixture** | `test_s14_*` / `test_cut040r2_state_integrity.py` |
| 8 | **4 类 guard**(6 个测试) | `tests/integration/test_eval_asset_integrity.py` |

### Guards(Codex 要求)

- **G1** 数据集引用的 display_id 必须存在(`expect=ok` 用例);不存在 → 明确 FAIL 并列出 stale reference
- **G2** 关系 fixture 必须 canonical(每 PR 恰 6 条)+ 不得有 `test:*` 来源污染
- **G3** 时态契约回归:`valid_from=valid_to=NULL` 必须在**每个** `as_of` 都命中
- **G4** 数据集 expected 必须与 fixture 一致;E4 下界必须 > 0(防 vacuous)

### 结果

| 套件 | 修复前 | 修复后 |
|---|---|---|
| E1 | 98.5% | **98.5%** |
| E2 | 61/61 | **61/61** |
| **E3** | 15.0% (exit 1) | **100.0% (exit 0)** |
| **E4** | 100% (vacuous) | **100.0% (exit 0, 非 vacuous)** |
| **E5** | 0.0% (exit 1) | **100.0% (exit 0)** |
| pytest | 353P/3S/0F | **359P/3S/0F** (+6 guards) |
| P1 | F0==F1==F2 | **F0==F1==F2**(无回归) |

原始 stdout: `reports/eval-archive/2026-09-20-cut040R2/FER/`
