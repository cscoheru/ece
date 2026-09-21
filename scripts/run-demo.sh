#!/usr/bin/env bash
# scripts/run-demo.sh
# ECE V0 现场演示一键脚本（09-30 客户演示用）
# Author: Claude（Opus 5）2026-09-22
# 范围: 仅串接现有命令，不新建任何模块
# 退出码: 0 = 全部成功；非 0 = 失败步骤的退出码

set -euo pipefail

cd "$(dirname "$0")/.."

# 颜色（仅当 stdout 是 tty 时）
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' NC=''
fi

step() {
    echo -e "${GREEN}==> $1${NC}"
}

fail() {
    echo -e "${RED}FAIL: $1${NC}" >&2
    exit 1
}

# Step 1: uv sync（自动下载 Python 3.12 并装依赖）
step "[1/5] uv sync (auto-downloads Python 3.12 if needed)"
uv sync --all-groups || fail "uv sync 失败（检查网络/uv 安装）"

# Step 2: docker compose up（postgres）
step "[2/5] docker compose up -d api"
docker compose up -d api || fail "docker compose 失败（检查 Docker Desktop 是否运行）"

# 等 postgres ready（最多 30s）
echo -n "  waiting for postgres"
for i in {1..30}; do
    if docker compose exec -T db pg_isready -U ece >/dev/null 2>&1; then
        echo -e " ${GREEN}ready${NC}"
        break
    fi
    echo -n "."
    sleep 1
done
docker compose exec -T db pg_isready -U ece >/dev/null 2>&1 || fail "postgres 30s 内未就绪"

# Step 3: gen-dataset + db-upgrade + seed
step "[3/5] gen-dataset + db-upgrade + seed"
make gen-dataset || fail "gen-dataset 失败"
make db-upgrade || fail "db-upgrade 失败"
make seed || fail "seed 失败（db 未空？先 make rev + make seed）"
uv run python scripts/ingest_demo_docs.py || fail "ingest_demo_docs 失败"

# Step 4: 跑 S6 三件证据（确定性 + E2 + 反查）
step "[4/5] 三件证据验证（S6 PASS 同套）"
echo "  --- 确定性 N=10 byte-equal ---"
uv run pytest tests/evaluation/test_s6_determinism.py -v 2>&1 | tail -20 || fail "S6 确定性测试失败"

echo "  --- E2 权限不漏 ---"
uv run python scripts/run_e2_permission.py 2>&1 | tail -15 || fail "E2 权限测试失败"

echo "  --- 4-hop Evidence 反查 ---"
uv run pytest tests/evaluation/test_s6_evidence_reversal.py -v 2>&1 | tail -20 || fail "S6 Evidence 反查失败"

# Step 5: MCP stdio 启动验证（证明部署形态可对接）
step "[5/5] MCP stdio 启动验证"
timeout 3 uv run python -m ece.mcp.transport < /dev/null 2>&1 | head -3 || true
echo "  (stdio 启动 3s 超时是预期行为：stdio 等 stdin 输入)"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Demo 环境就绪！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "接下来 6 步现场演示（45 min）："
echo ""
echo "1. 三件证据开篇 (5 min)"
echo "   uv run pytest tests/evaluation/test_s6_*.py -v"
echo ""
echo "2. 张三 PR + POL-2026-03 (8 min)"
echo "   启动 Claude Desktop/Cline + MCP stdio"
echo "   demo: 'show me a single purchase request review for PR with 100万+ amount'"
echo ""
echo "3. 比价完整性检查 (5 min)"
echo "   demo: 'check 比价完整性 on PR with <3 quotes → 阻断'"
echo ""
echo "4. Evidence 一行 SQL 反查 (3 min)"
echo "   uv run python -c \"from ece.db import get_engine; ...\""
echo ""
echo "5. Permission denied 零副作用 (3 min)"
echo "   用未知 user 调 /context → ACL 拒绝 → DB 无写入"
echo ""
echo "6. Audit trail (3 min)"
echo "   uv run python scripts/export_audit.py"
echo ""
echo "完整话术见: docs/customer/demo-script.md"