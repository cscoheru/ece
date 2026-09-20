#!/usr/bin/env bash
# cut-040R-2 最终工程验收 (Codex 第三轮补充判词 §七)
#
# 执行 §七 要求的 9 项检查并留原始输出。
#
# 关于 DB 指纹 [0] vs [4]:
#   本脚本在 pytest 前后各取一次指纹。**两者必然不同**, 原因已实测确认:
#     test_s14_seed_idempotent + test_cut040r2_state_integrity 会 **DELETE 全部
#     `demo:%` 实体再重播** —— 重播时 entities.id 是**新生成的 UUID**。
#     行数可以相同 (439 -> 439), 但 uuid 变化使哈希改变 (已用 surface diff 验证:
#     856 行差异, 全部是 entities.id 变化)。
#   这不是缺陷, 是该测试套件的既定设计; 也不是 P2 那种无界污染。
#
#   ⚠️ 因此指纹对 uuid **敏感** —— 这是**刻意的**: entities.id 属于 E2 读取集 ([R2]
#   的 SELECT id), 按 Codex §二 的规则必须覆盖。
#
#   而 P1 单变量实验的 F0==F1==F2 判定**不受影响**: 它跨度是两次 E2 runner 调用,
#   E2 runner 不写库 (R6 已核验), 故 uuid 不变 -> 指纹恒定。
#   脚本 [4b] 单独复验这一点 (E2 前后取指纹, 应相同)。

cd "$(dirname "$0")/.." || exit 1

A=reports/eval-archive/2026-09-20-cut040R2
ACC="$A/FINAL_ACCEPTANCE"
mkdir -p "$ACC"
OUT="$ACC/acceptance.txt"

fingerprint() {
  docker compose exec -T db psql -U ece -d ece -t -A -F'|' -f - \
    < scripts/db_state_fingerprint.sql 2>/dev/null | tr -d '\r' | head -1
}
count_entities() {
  docker compose exec -T db psql -U ece -d ece -t -A -c \
    "SELECT count(*) FROM entities;" 2>/dev/null | tr -d '[:space:]'
}

{
  echo "==================================================================="
  echo "cut-040R-2 最终工程验收 (Codex 第三轮补充判词 §七)"
  echo "date : $(date -Iseconds)"
  echo "HEAD : $(git rev-parse HEAD)"
  echo "==================================================================="
  echo ""
  echo "--- [0] 起点 DB 指纹 + 实体数 ---"
  echo "fingerprint: $(fingerprint)"
  echo "entities   : $(count_entities)"
  echo ""
  echo "--- [1] 完整 pytest ---"
  uv run pytest -m "not eval and not eval_llm" -q > /tmp/acc-pytest.txt 2>&1
  PYTEST_EC=$?
  python3 - <<'PY'
import re
t = open('/tmp/acc-pytest.txt').read()
tot=sk=fa=0
for line in t.splitlines():
    m = re.match(r'^([.sF]+)\s+\[\s*\d+%\]', line)
    if m: tot+=len(m.group(1)); sk+=m.group(1).count('s'); fa+=m.group(1).count('F')
print(f"collected {tot} / passed {tot-sk-fa} / skipped {sk} / failed {fa}")
PY
  echo "pytest exit code: $PYTEST_EC"
  echo ""
  echo "--- [2] E1 ---"
  uv run python scripts/run_e1_resolution.py --data data/eval/e1_resolution.json \
    --base-url http://127.0.0.1:8765 2>&1 | grep -E "Total:|Correct:|Wrong:|Accuracy:|PASS|UNDER"
  echo ""
  echo "--- [3] E2 ---"
  uv run python scripts/run_e2_permission.py --data data/eval/e2_permission.json \
    --base-url http://127.0.0.1:8765 2>&1 | grep -E "Total cases|Failures|Exposures|PASS|FAIL"
  echo ""
  echo "--- [4] 终点 DB 指纹 + 实体数 (见文件头说明: 与 [0] 必然不同, 因 uuid 重生成) ---"
  echo "fingerprint: $(fingerprint)"
  echo "entities   : $(count_entities)"
  echo ""
  echo "--- [4b] E2 运行前后的 DB 指纹 (应与 P1 的 F0==F1==F2 一致: **相同**) ---"
  FP_BEFORE_E2=$(fingerprint)
  uv run python scripts/run_e2_permission.py --data data/eval/e2_permission.json \
    --base-url http://127.0.0.1:8765 > /dev/null 2>&1
  FP_AFTER_E2=$(fingerprint)
  echo "before E2 run: $FP_BEFORE_E2"
  echo "after  E2 run: $FP_AFTER_E2"
  if [ "$FP_BEFORE_E2" = "$FP_AFTER_E2" ]; then
    echo "=> UNCHANGED — E2 runner 不写库, 与 P1 的 F0==F1==F2 一致 ✅"
  else
    echo "=> CHANGED — E2 runner 写库了, P1 的恒定判定需重估 ❌"
  fi
  echo ""
  echo "--- [5a] 污染检查: 重名实体 (P2 判据, 应为 0) ---"
  docker compose exec -T db psql -U ece -d ece -c \
    "SELECT count(*) AS dup_names FROM (SELECT name FROM entities WHERE entity_type IN ('supplier','person') GROUP BY name HAVING count(*)>1) t;"
  echo "--- [5b] 幂等性检查: 再跑一次 pytest, 实体数应不变 ---"
  B=$(count_entities)
  uv run pytest -m "not eval and not eval_llm" -q > /tmp/acc-pytest2.txt 2>&1
  echo "pytest #2 exit code: $?"
  AF=$(count_entities)
  echo "entities before 2nd run: $B"
  echo "entities after  2nd run: $AF"
  if [ "$B" = "$AF" ]; then
    echo "=> IDEMPOTENT (测试创建实体的 source_id 稳定, 无无界增长)"
  else
    echo "=> NOT IDEMPOTENT — 测试仍在累积实体, 需排查"
  fi
  echo ""
  echo "--- [5c] 残留 r4-test 来源 (应只剩保留的 SUP052/SUP053 一对) ---"
  docker compose exec -T db psql -U ece -d ece -c \
    "SELECT source_system, count(*) FROM entities WHERE source_system LIKE 'csv:r4-test-%' GROUP BY 1;"
  echo ""
  echo "--- [6] git status ---"
  git status --short
  echo ""
  echo "--- [7] P1 单变量实验记录 (最近一次) ---"
  cat "$A/single-variable-v2/EXPERIMENT_RECORD.txt" 2>/dev/null | head -30
  echo ""
  echo "--- [8] 指纹漂移归因 (聚焦实验: 只跑两个 wipe+replay 测试) ---"
  echo "目的: 证明跨 pytest 的指纹变化**全部来自 entities.id (uuid) 重生成**, 而非决策状态变化。"
  docker compose exec -T db psql -U ece -d ece -t -A -f - \
    < scripts/db_surface_dump.sql 2>/dev/null | tr -d '\r' > /tmp/surf_a.txt
  uv run pytest tests/integration/test_s14_seed_idempotent.py \
                tests/integration/test_cut040r2_state_integrity.py -o addopts="" -q > /dev/null 2>&1
  echo "wipe+replay 测试 exit code: $?"
  docker compose exec -T db psql -U ece -d ece -t -A -f - \
    < scripts/db_surface_dump.sql 2>/dev/null | tr -d '\r' > /tmp/surf_b.txt
  echo "surface 行数: before=$(wc -l < /tmp/surf_a.txt | tr -d ' ') after=$(wc -l < /tmp/surf_b.txt | tr -d ' ')"
  echo "差异行数    : $(diff /tmp/surf_a.txt /tmp/surf_b.txt | grep -c '^[<>]' || true)"
  echo "差异是否**仅**限于 id 字段 (第 2 列)?"
  python3 - <<'PY'
import subprocess
a = subprocess.run(["bash","-c","diff /tmp/surf_a.txt /tmp/surf_b.txt"],
                   capture_output=True, text=True).stdout.splitlines()
# 每行形如 "< entities|<id>|display_id|..." —— 去掉第 2 列后比较
def strip_id(line):
    body = line[2:]
    parts = body.split("|")
    if len(parts) > 2:
        parts[1] = "<ID>"
    return "|".join(parts)
removed = sorted(strip_id(l) for l in a if l.startswith("< "))
added   = sorted(strip_id(l) for l in a if l.startswith("> "))
if removed == added:
    print("  => YES — 除 id 外内容完全一致; 指纹变化 100% 由 uuid 重生成解释 ✅")
else:
    print(f"  => NO — 除 id 外仍有 {len(set(removed) ^ set(added))} 处差异, 需进一步排查 ❌")
    for x in sorted(set(removed) ^ set(added))[:5]:
        print("     ", x[:120])
PY
} > "$OUT" 2>&1

cat "$OUT"
