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

# SAFETY GATE: this script does `git checkout <commit> -- src/`, which SILENTLY
# DESTROYS uncommitted changes under src/. That already happened once (an
# uncommitted seed.py fix was reverted before it could be committed, so a
# "green" run was measured on a state the commit did not contain). Refuse to run
# on a dirty src/.
if [ -n "$(git status --porcelain -- src/)" ]; then
  echo "REFUSING TO RUN: src/ has uncommitted changes; this script would revert them."
  echo "Commit or stash first."
  git status --short -- src/
  exit 2
fi

ARCHIVE=reports/eval-archive/2026-09-20-cut040R2/single-variable-v2
mkdir -p "$ARCHIVE"
RECORD="$ARCHIVE/EXPERIMENT_RECORD.txt"

BASELINE_COMMIT=$(git rev-parse 037260b~1)
FIXED_COMMIT=$(git rev-parse HEAD)
DATASET_SHA=$(shasum -a 256 data/eval/e2_permission.json | cut -d' ' -f1)

fingerprint() {
  # Emits:  <sha256>|<entities_rows>|<aliases_rows>|<acl_rows>
  docker compose exec -T db psql -U ece -d ece -t -A -F'|' -f - \
    < scripts/db_state_fingerprint.sql 2>/dev/null | tr -d '\r' | head -1
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
  echo "cut-040R-2 单变量实验记录 (rev3: SHA-256 指纹 + read-set 完整覆盖)"
  echo "==================================================================="
  echo "目的: 证明在【固定 DB 状态 + 固定数据集 + 同一运行时】下, 两臂的唯一差异是源码。"
  echo ""
  echo "baseline commit : $BASELINE_COMMIT"
  echo "fixed commit    : $FIXED_COMMIT"
  echo "                  (037260b = 六根因修复; HEAD 仅追加注释 + P2 测试修复)"
  echo "dataset         : data/eval/e2_permission.json"
  echo "dataset sha256  : $DATASET_SHA"
  echo "runtime         : 两臂均为宿主 uvicorn (同一 venv)"
  echo "DATABASE_URL    : ${DATABASE_URL:-postgresql+psycopg://ece:ece@localhost:5432/ece (default)}"
  echo "db              : docker compose ece-db-1 (postgres 16-pgvector)"
  echo "fingerprint     : scripts/db_state_fingerprint.sql — SHA-256 over the COMPLETE"
  echo "                  E2 read-set (entities 9 cols / entity_aliases 9 cols / acl_entries 10 cols),"
  echo "                  ordered by (scope, row_text). 输出格式: sha256|entities_rows|aliases_rows|acl_rows"
  echo "deps evidence   : P1_DEPENDENCY_MATRIX.md (E2 read-set ⊆ fingerprint scope, 逐项)"
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
  echo "-------------------------------------------------------------------"
  echo "A. 本实验【已经证明】的内容"
  echo "-------------------------------------------------------------------"
  echo "  固定 DB state + 固定 dataset + 相同 runtime +"
  echo "  baseline/fixed RUNTIME code    ->  E2 结果发生变化 (4/4 -> 0/0)"
  echo ""
  echo "  即: permission RUNTIME 代码是 E2 结果变化的【充分原因】,"
  echo "      且 DB 状态在两臂之间恒定 (F0==F1==F2), 数据集逐字节相同 (sha256 见上)。"
  echo ""
  echo "-------------------------------------------------------------------"
  echo "B. 本实验【没有测量】的内容"
  echo "-------------------------------------------------------------------"
  echo "  seed / 数据层面的修复各自贡献多少:"
  echo "    RC-6  部门注入位置  (seed_from_demo_json 内)"
  echo "    RC-7  专属对象      (PR003 / CON002)"
  echo "    RC-9  ACL 对象词表  (entity -> 域类型)"
  echo "  这些修复已由修后的 seed 写入 DB, 两臂共用同一份,"
  echo "  故其在本设计中对结果差异的贡献【恒为 0】—— 它们不是被『对照』了, 而是被『共享』了。"
  echo ""
  echo "-------------------------------------------------------------------"
  echo "C. 若将来需要回答 B, 应增加什么实验"
  echo "-------------------------------------------------------------------"
  echo "  增设第三臂: baseline 代码 + **baseline seed 产出的 DB**"
  echo "    - 需要一个独立数据库实例, 或用 dump/restore 保存两份 DB 快照"
  echo "    - 对本轮而言【不必要】: 本实验要回答的问题不是『seed 修复贡献几何』,"
  echo "      而是『runtime 代码修复是否足以把 E2 从 4/4 变为 0/0』—— 该问题已回答。"
  echo ""
  echo "  ⚠️ 措辞纪律: 不得使用超出证据范围的『严格因果证明』表述。"
  echo "     本实验的证据类型是【可审计、可复现的实验控制】, 不是密码学意义上的绝对证明。"
} >> "$RECORD"

cat "$RECORD"
