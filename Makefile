.PHONY: setup up test eval demo rev help check-api-docs db-upgrade schema-check gen-dataset pull-db

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

setup:
	uv sync --all-groups

up:
	docker compose up -d api

test:
	uv run pytest -m "not eval and not eval_llm"

eval:
	uv run pytest -m "eval or eval_llm"

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
