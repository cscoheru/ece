.PHONY: setup up test eval demo rev help check-api-docs db-upgrade schema-check gen-dataset pull-db seed-fixtures test-integration

help:
	@echo "ECE v0 Makefile"
	@echo "  make setup            - install deps via uv"
	@echo "  make up               - start docker compose (api + postgres)"
	@echo "  make test             - run unit + integration + security tests"
	@echo "  make eval             - run E1-E6 evaluation suite (needs ECE_LLM_*)"
	@echo "  make demo             - run procurement demo scenario"
	@echo "  make check-api-docs   - API.md ↔ FastAPI routes 双向 diff (S0.4)"
	@echo "  make db-upgrade       - alembic upgrade head (S0.5)"
	@echo "  make schema-check     - live DB ↔ DATA_MODEL.md 比对 (S0.5)"
	@echo "  make gen-dataset      - 生成 PRD §27 合成数据 (S0.6)"
	@echo "  make pull-db          - pgvector 镜像 pull+tag（绕 daocloud 403）"
	@echo "  make rev              - alembic downgrade by 1"
	@echo "  ----- OEI-005 (2026-09-24): 完整本地集成测试前置链 -----"
	@echo "  make seed-fixtures    - 跑 3 个集成 fixture seeder(temporal/knowledge/compliance)"
	@echo "  make test-integration - 完整集成测试前置(make pull-db + make db-upgrade + make gen-dataset + make seed + make seed-fixtures + pytest)。详见 ece/README.md 测试段。"

setup:
	uv sync --all-groups

up:
	docker compose up -d api

test:
	uv run pytest -m "not eval and not eval_llm"

eval:
	uv run pytest -m "eval or eval_llm"

# cut-039 R39.1: 6-runner E1-E6 eval report (real stdout, 禁止编数).
# Usage: make eval-report BASE_URL=http://127.0.0.1:8765
# Default BASE_URL=http://127.0.0.1:8765. E6 real-LLM mode requires ECE_LLM_BASE_URL.
# All output archived to reports/eval-archive/YYYYMMDD-cutNNNN/ (raw stdout per runner).
eval-report:
	@mkdir -p reports/eval-archive/$(shell date +%Y-%m-%d)
	@BASE_URL=$${BASE_URL:-http://127.0.0.1:8765}; \
	echo "ARCHIVE=reports/eval-archive/$(shell date +%Y-%m-%d)-cut039"; \
	ARCHIVE=reports/eval-archive/$(shell date +%Y-%m-%d)-cut039; \
	mkdir -p $$ARCHIVE; \
	uv run python scripts/run_e1_resolution.py --data data/eval/e1_resolution.json --base-url $$BASE_URL 2>&1 | tee $$ARCHIVE/E1.txt; \
	uv run python scripts/run_e2_permission.py --data data/eval/e2_permission.json --base-url $$BASE_URL 2>&1 | tee $$ARCHIVE/E2.txt; \
	uv run python scripts/run_e3_context.py --data data/eval/e3_context.json --base-url $$BASE_URL 2>&1 | tee $$ARCHIVE/E3.txt; \
	uv run python scripts/run_e4_relationships.py --data data/eval/e4_relationships.json --base-url $$BASE_URL 2>&1 | tee $$ARCHIVE/E4.txt; \
	uv run python scripts/run_e5_temporal.py --data data/eval/e5_temporal.json --base-url $$BASE_URL 2>&1 | tee $$ARCHIVE/E5.txt; \
	uv run python scripts/run_e6_agent.py --data data/eval/e6_agent.json 2>&1 | tee $$ARCHIVE/E6.txt

demo:
	uv run python -m ece.demo

# S0.4: API.md ↔ FastAPI openapi.json 双向 diff(文档有而路由无 WARNING;路由有而文档无 ERROR exit 1)
check-api-docs:
	uv run python scripts/check_api_docs.py

# S0.5: Alembic 迁移到最新 schema(默认 DATABASE_URL=compose db)
db-upgrade:
	uv run alembic -c src/ece/migrations/alembic.ini upgrade head

# S0.5: 连活库核对 information_schema vs DATA_MODEL.md §1-§5
schema-check:
	uv run python scripts/check_schema.py

# S0.6: 合成 Demo Corporation 数据(per PRD §27)
gen-dataset:
	uv run python scripts/gen_dataset.py --out data/dataset/demo.json

# cut-035R2 R1': E1-E6 评测数据集生成(per EVALUATION.md §1; cut-006r §R2 + cut-015a 分布)
# 必须在 make seed 之后跑(查询 entities 表获取 display_id)
gen-eval-datasets:
	uv run python scripts/gen_eval_datasets.py

# R2 (cut-006 §7.3): E2 权限套件 runner — Unauthorized Exposure = 0 一票否决
# 前置: make pull-db + docker compose up -d db + uv run alembic upgrade head + make seed
e2-runner:
	uv run python scripts/run_e2_permission.py --data data/eval/e2_permission.json

# S1.4: seed 入库 (Connectors + Entity pipeline 串接);幂等:再跑 created=0
seed:
	uv run python -m ece.seed

rev:
	uv run alembic downgrade -1

# R5 (cut-003r2): pgvector 镜像源补救 — daocloud.io 对 library/postgres:16-pgvector 403 Forbidden,
# 但 pgvector/pgvector:pg16 走同一 mirror 可拉;tag 一下 compose 即可找到。
pull-db:
	@echo "Pulling pgvector/pgvector:pg16 (avoids daocloud.io 403 on library/postgres:16-pgvector upstream)..."
	docker pull pgvector/pgvector:pg16
	docker tag pgvector/pgvector:pg16 postgres:16-pgvector
	@echo "Tagged pgvector/pgvector:pg16 → postgres:16-pgvector (compose can now find it locally)"

# OEI-005 (2026-09-24): 集成测试 fixture seeder 集合
# 这三个 seeder 之前只在 deploy/README.md:84-85 与 deploy/SERVER_DEPLOYMENT_CHECKLIST.md 提到,
# 仓里集成测试默认跑 `make test` 不会自动跑 → 27 个测试因缺 fixture 失败.
# 用法(在已 `make db-upgrade` + `make seed` 之后):
#   make seed-fixtures
# 等价于:
#   uv run python scripts/seed_temporal_roles.py
#   uv run python scripts/seed_knowledge_fixture.py
#   uv run python scripts/seed_compliance_fixture.py
#   uv run python scripts/seed_v0_spike_fixture.py  # OEI-007 step 0.1
# 幂等:再跑一次会删除并重建 fixture 行(seed_*.py 内置 self-check + removed prior rows)。
seed-fixtures:
	@echo "Seeding integration test fixtures (temporal / knowledge / compliance / spike)..."
	uv run python scripts/seed_temporal_roles.py
	uv run python scripts/seed_knowledge_fixture.py
	uv run python scripts/seed_compliance_fixture.py
	uv run python scripts/seed_v0_spike_fixture.py
	@echo "All fixtures seeded. Now `make test` should reach baseline (0 failed)."

# OEI-005 (2026-09-24): 集成测试完整前置链(供 CI / 新开发者用)
# 等价于:
#   make pull-db && make db-upgrade && make gen-dataset && make seed && make seed-fixtures && make test
# DATABASE_URL 须指向可达的 PG(本地 compose 或远程)。在 WSL 上若 bind-mount 因 uid 999
# 失败,临时 PG 跑法见 deploy/README.md 与本仓 OEI-005 evidence/。
test-integration:
	make pull-db
	make db-upgrade
	make gen-dataset
	make seed
	make seed-fixtures
	make test
