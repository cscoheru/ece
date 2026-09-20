# R2.1 evidence archive — `rejected` 失败语义

用途：Codex 裁定 **R2 = PASS WITH MINOR CONDITIONS** 后，处置其唯一代码级条件
（`rejected` 是否应使 canonical seed 失败）的**原始 stdout 归档**。
所有文件都是命令直接重定向出来的，未经转述。

复现入口：仓库根 `docs/v0/R2_IMPLEMENTATION_REPORT.md` §10。

| 文件 | 证明了什么 |
|---|---|
| `01-cli-wrapper-ok.txt` | 健康环境下 `scripts/seed_relationships.py` **exit 0**，`Total relationships in DB: 1204`（1200 我方 + 3 HAS_ROLE + 1 S1 spike SELECTS） |
| `02-cli-wrapper-incomplete.txt` | 外部 fixture 占走一条 triple 后，同一命令 **exit 1**，错误串精确指出成因（"1200 insert(s) were reported" 而实际 1199） |
| `03-make-seed.txt` | `make seed` exit 0，关系分布 200/400/200/200/200 = **1200**，0 rejected |
| `04-guards-bite-old-code.txt` | ⭐ **新 guard 对旧代码确实失败** —— 见下 |
| `05-pytest-full.txt` | 全量 **363 passed, 3 skipped, 0 failed** |
| `06-e4.txt` / `07-e5.txt` | E4 / E5 各 30/30 = 100%，exit 0 |
| `08-e1.txt` / `09-e2.txt` / `10-e3.txt` | E1 98.5% / E2 0 暴露 0 失败 / E3 100% —— 与 R2 基线逐项一致 |
| `11-probe-inserted-semantics.txt` | ⭐ `upsert_relationship` 对同一 triple 两次调用**都返回 `inserted=True`，库里只有一行** |
| `12-r21-diff.patch` | 本次全部改动 |
| `13-scope.txt` | 改动范围 **恰好 3 个文件** |

## 为什么 `04` 和 `11` 是这次最重要的两份

裁定提出的问题是「`rejected` 是否应该让 seed 失败」。回答之前必须先问一个更基础的问题：
**`ok=True` 到底证明了什么？**

`11` 给出的答案是：它什么都证明不了。`upsert_relationship` 的 `ON CONFLICT DO NOTHING`
no-op 与真正写入**返回值完全相同**，而 `uq_relationships_triple` 的键
`(src, relation, dst, valid_from)` **不含 `source_system`** —— 于是另一个 fixture 占住
triple 时，我们的插入静默失败、计数器照常 +1。

所以修复不能只加一个 `if rejected: ok = False`，必须**以库内实发行数为准**：

```
owned = count(*) WHERE source_system = 'demo:seed_relationships'
ok    = (rejected == []) and (owned == len(PRs) * 6)
```

`04` 则是这条修复的负向对照 —— 把新 guard 对着**改动前的代码**跑，两份失败输出
本身就是缺陷的直接证据：

```
G7（旧码）ok: True, BELONGS_TO: 199, rejected: ['PR001 -BELONGS_TO-> D001: ...']
        → make seed 会在 1199 条的 fixture 上报成功

G8（旧码）ok: True, BELONGS_TO: 200（计数器）而实际只写入 199 条
        → 计数器撒谎，seed 说成功
```

没有这一步，`ok is False` 之类的断言就只是「看起来在检查」——
与 R2 要消灭的假绿同型。
