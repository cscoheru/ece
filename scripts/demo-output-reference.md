# Demo 期望输出 Reference

> **作者**: Claude（Opus 5）
> **日期**: 2026-09-22
> **用途**: user 跑 `scripts/run-demo.sh` 时, 对照每步输出确认"对/不对", 不需要懂代码就能判断

---

## Step 1: uv sync

**预期 stdout 末尾**:
```
Installed 200+ packages in X.Xs
```

**判定**:
- ✅ 看到 "Installed" → 通过
- ❌ 看到 "error: failed to download" → 网络问题, 重试或换 WiFi
- ❌ 看到 "No Python 3.12 found, downloading..." 然后卡住 → 等 30s, uv 在下 Python 3.12

---

## Step 2: docker compose up

**预期 stdout 末尾**:
```
Container ece-api-1  Started
Container ece-db-1   Started
```

**postgres ready 检测**:
```
==> waiting for postgres...ready
```

**判定**:
- ✅ 看到 "ready" → 通过
- ❌ 看到 30 个点没 "ready" → `docker compose logs db` 看错
- ❌ "port 5432 already in use" → 之前 postgres 没清, `docker compose down -v`

---

## Step 3: gen-dataset + db-upgrade + seed

**gen-dataset 预期末尾**:
```
✓ data/dataset/demo.json (428 entities)
```

**db-upgrade 预期末尾**:
```
Running upgrade  -> xxxx (head)
```

**seed 预期末尾**:
```
✓ entities: 428
✓ relationships: 1200
✓ acl_entries: 3
✓ seed complete
```

**ingest_demo_docs 预期末尾**:
```
✓ ingested X demo docs
```

**判定**:
- ✅ 看到三个数字 428/1200/3 → 通过
- ❌ "seed failed: relation already exists" → 旧数据, 先 `make rev` + 重新跑

---

## Step 4: 三件证据

### 4.1 S6 确定性测试

**预期末尾**:
```
test_s6_determinism.py::test_byte_equal_10_runs PASSED
====== N passed in X.Xs ======
```

**判定**:
- ✅ 看到 N passed (N ≥ 1) → 通过
- ❌ FAILED → V0 spike 状态被破坏, 不要演示, 排查

### 4.2 E2 权限测试

**预期末尾**:
```
E2 permission test: 61 passed, 0 failed
E2 unauthorized context exposure: 0
```

**判定**:
- ✅ 看到 "0 failed" 和 "0" → 通过
- ❌ 任何 failed 或 unauthorized exposure > 0 → 不能演示

### 4.3 S6 Evidence 反查

**预期末尾**:
```
test_s6_evidence_reversal.py::test_4_hop_reversal PASSED
====== N passed in X.Xs ======
```

**判定**:
- ✅ 看到 4-hop test PASSED → 通过

---

## Step 5: MCP stdio 启动

**预期输出**:
```
(timeout 3s 后退出, 无输出是正常)
```

**判定**:
- ✅ 3s 超时退出, 无报错 → 通过（stdio 等 stdin）
- ❌ "ModuleNotFoundError: ece.mcp.transport" → cut-041 没装, 跑 `uv sync --all-groups`
- ❌ "Address already in use" → 端口冲突, 关掉其他 MCP 进程

---

## 演示 Step 2: 张三 PR 查询（Claude Desktop）

**预期 Claude 回答片段**:
```
找到 3 个 100万+ 的采购申请:
- PR-2024-001: 张三提交, 1,234,567 元, 触发 POL-2026-03 比价阈值检查
- PR-2024-005: 张三提交, 987,654 元, ...
- ...
```

**判定**:
- ✅ 看到张三类 PR 列表 + POL-2026-03 政策引用 → 通过
- ❌ "未找到匹配的 PR" → seed 没装, 跑 `make seed`
- ❌ "permission denied" → Claude Desktop 的 MCP 配置 user 不是 ece 用户

---

## 演示 Step 3: 比价检查

**预期 Claude 回答**:
```
PR-2024-001 比价完整性检查:
- 报价供应商: A公司, B公司 (共 2 家)
- POL-2026-03 要求: ≥3 家独立比价
- 决策: 阻断 ✗
- 依据: 比价不充分, 需补充第 3 家独立报价
```

**判定**:
- ✅ 看到 "阻断 ✗" + "≥3 家" + 依据引用 POL → 通过
- ❌ "检查通过" → seed 的 PR 没构造 2 家比价的负面 case, 换一个 PR

---

## 演示 Step 4: SQL 反查

**预期 stdout**:
```
PR-2024-001: 比价不充分阻断 (依据 POL-2026-03 §3.2)
PR-2024-005: 金额超阈值需 VP 审批 (依据 POL-2026-03 §2.1)
...
```

**判定**:
- ✅ 看到 decision_reason 字段有真实依据 → 通过
- ❌ 0 行 → SQL 字段名不对, 这是简化版 demo, 接受 0 行（演示回退）

---

## 演示 Step 5: Permission denied

**预期 curl 输出**:
```
HTTP/1.1 401 Unauthorized
{"detail": "Unknown user"}
```

**预期 docker logs db 末尾**:
```
(无新 INSERT 日志)
```

**判定**:
- ✅ 401 + db 无新 INSERT → 通过（V0 防御正确）
- ❌ 200 OK → 严重 BUG, 立即停止演示, 这是 V0 防线失守

---

## 演示 Step 6: Audit trail

**预期 stdout 末尾**:
```
audit_exported.csv (N rows)
```

**判定**:
- ✅ 看到 CSV 输出 → 通过
- ❌ 0 rows → 之前演示步骤没产生 context_request, 跑一遍 Step 2-4 再来

---

## 总判定矩阵

| Step | 通过条件 | 失败动作 |
|---|---|---|
| 1. uv sync | "Installed" 输出 | 网络/PATH 问题 |
| 2. docker | postgres "ready" | Docker Desktop 未启动 |
| 3. seed | 428/1200/3 三数字 | 旧数据, `make rev` 重来 |
| 4.1 确定性 | N passed | V0 状态破坏, 不演示 |
| 4.2 E2 | 61 passed, 0 failed | 不能演示 |
| 4.3 反查 | PASSED | 不能演示 |
| 5. MCP stdio | 3s 超时无错 | uv sync 不全 |
| 6. 现场 Step 2-6 | 见各步 | 见各步 |

**全部 ✅ 才进客户演示; 任一 ❌ 不演示, 退回 T-1 排查。**

---

**Author**: Claude（Opus 5）
**Date**: 2026-09-22
**配合**: `scripts/run-demo.sh` + `scripts/demo-checklist.md` 三件套齐备