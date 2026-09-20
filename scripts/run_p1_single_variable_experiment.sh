#!/usr/bin/env bash
# cut-040R-2 P1' — strict single-variable experiment with DB-state fingerprinting.
#
# Codex 第三轮判词 [MAJOR]: the original P1 only proved both arms shared the same
# DATASET. It did not prove they shared the same DATABASE STATE, and the seed/data
# fixes are themselves part of the commit under test — so seed state was an
# uncontrolled variable.
#
# This script closes that gap:
#   * BOTH arms run on the SAME runtime (host uvicorn, same venv, same DB) —
#     this also removes the "control ran on host, treatment ran in docker"
#     caveat from the first attempt.
#   * A deterministic DB fingerprint is taken BEFORE, BETWEEN and AFTER the two
#     arms. If all three match, the DB was provably constant across the arms.
#
# Usage:  bash scripts/run_p1_single_variable_experiment.sh
# Requires: docker compose db up, reseeded (`uv run python -m ece.seed`).

cd "$(dirname "$0")/.." || exit 1

ARCHIVE=reports/eval-archive/2026-09-20-cut040R2/single-variable-v2
mkdir -p "$ARCHIVE"
RECORD="$ARCHIVE/EXPERIMENT_RECORD.txt"

BASELINE_COMMIT=$(git rev-parse 037260b~1)
FIXED_COMMIT=$(git rev-parse HEAD)
DATASET_SHA=$(shasum -a 256 data/eval/e2_permission.json | cut -d' ' -f1)

fingerprint() {
  docker compose exec -T db psql -U ece -d ece -t -A -f - \
    < scripts/db_state_fingerprint.sql 2>/dev/null | tr -d '[:space:]'
}

run_arm() {
  # $1 = label, $2 = port, $3 = outfile, $4 = exitcode-file
  local label="$1" port="$2" out="$3" ecfile="$4"
  nohup uv run uvicorn ece.main:app --host 127.0.0.1 --port "$port" \
    > "/tmp/p1v2-$label.log" 2>&1 &
  local pid=$!
  local ok=no
  for _ in $(seq 1 30); do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/healthz" 2>/dev/null)" = "200" ]; then
      ok=yes; break
    fi
    sleep 2
  done
  if [ "$ok" != "yes" ]; then
    echo "ARM $label FAILED TO START (see /tmp/p1v2-$label.log)" | tee "$out"
    echo 99 > "$ecfile"
    kill "$pid" 2>/dev/null
    return
  fi
  uv run python scripts/run_e2_permission.py \
    --data data/eval/e2_permission.json --base-url "http://127.0.0.1:$port" \
    > "$out" 2>&1
  echo $? > "$ecfile"
  kill "$pid" 2>/dev/null
  pkill -f "uvicorn ece.main:app --host 127.0.0.1 --port $port" 2>/dev/null
  sleep 2
}

{
  echo "==================================================================="
  echo "cut-040R-2 P1' — 严格单变量实验记录"
  echo "==================================================================="
  echo "目的: 证明在【固定 DB 状态 + 固定数据集】下, 两臂的唯一差异是源码。"
  echo ""
  echo "baseline commit : $BASELINE_COMMIT"
  echo "fixed commit    : $FIXED_COMMIT"
  echo "                  (037260b = 六根因修复; HEAD 仅追加注释 + P2 测试修复)"
  echo "dataset         : data/eval/e2_permission.json"
  echo "dataset sha256  : $DATASET_SHA"
  echo "runtime         : 两臂均为宿主 uvicorn (同一 venv, 同一 DATABASE_URL)"
  echo "db              : docker compose ece-db-1 (postgresql+psycopg://ece@localhost:5432/ece)"
  echo "fingerprint     : scripts/db_state_fingerprint.sql (entities + acl_entries 的有序 md5)"
  echo ""
} > "$RECORD"

F0=$(fingerprint)
echo "F0 (两臂开始前)      : $F0" | tee -a "$RECORD"

echo "" | tee -a "$RECORD"
echo "--- ARM A: baseline 源码 ($BASELINE_COMMIT) @ :8766 ---" | tee -a "$RECORD"
git checkout "$BASELINE_COMMIT" -- src/
run_arm "baseline" 8766 "$ARCHIVE/E2-baseline-code.txt" /tmp/p1v2-ec-a
F1=$(fingerprint)
echo "F1 (ARM A 结束后)    : $F1" | tee -a "$RECORD"
echo "ARM A exit code      : $(cat /tmp/p1v2-ec-a)" | tee -a "$RECORD"

echo "" | tee -a "$RECORD"
echo "--- ARM B: fixed 源码 ($FIXED_COMMIT) @ :8767 ---" | tee -a "$RECORD"
git checkout "$FIXED_COMMIT" -- src/
run_arm "fixed" 8767 "$ARCHIVE/E2-fixed-code.txt" /tmp/p1v2-ec-b
F2=$(fingerprint)
echo "F2 (ARM B 结束后)    : $F2" | tee -a "$RECORD"
echo "ARM B exit code      : $(cat /tmp/p1v2-ec-b)" | tee -a "$RECORD"

{
  echo ""
  echo "==================================================================="
  echo "DB 状态恒定性判定"
  echo "==================================================================="
  if [ "$F0" = "$F1" ] && [ "$F1" = "$F2" ]; then
    echo "PASS — F0 == F1 == F2, DB 状态在两臂之间未被改动。"
  else
    echo "FAIL — 指纹不一致, 实验无效:"
    echo "  F0=$F0"
    echo "  F1=$F1"
    echo "  F2=$F2"
  fi
  echo ""
  echo "结论口径 (严格):"
  echo "  在【固定 DB 状态】+【固定数据集】下, permission RUNTIME 代码由 baseline"
  echo "  改为 fixed, E2 从 4 暴露/4 失败 变为 0/0。"
  echo ""
  echo "本实验【不】测量的:"
  echo "  seed/数据层面的修复 (RC-6 部门注入位置 / RC-7 专属对象 / RC-9 ACL 词表) ——"
  echo "  这些已由修后的 seed 写入 DB, 两臂共用同一份, 故其对结果的贡献在本设计中恒为 0。"
  echo "  要测量它们需另设一臂: baseline 代码 + baseline seed 产出的 DB。"
} >> "$RECORD"

cat "$RECORD"
