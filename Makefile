.PHONY: setup up test eval demo rev help

help:
	@echo "ECE v0 Makefile"
	@echo "  make setup  - install deps via uv"
	@echo "  make up     - start docker compose (api + postgres)"
	@echo "  make test   - run unit + integration + security tests"
	@echo "  make eval   - run E1-E6 evaluation suite (needs ECE_LLM_*)"
	@echo "  make demo   - run procurement demo scenario"
	@echo "  make rev    - alembic downgrade by 1"

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

rev:
	uv run alembic downgrade -1

# R5 (cut-003r2): pgvector 镜像源补救 — daocloud.io 对 library/postgres:16-pgvector 403 Forbidden,
# 但 pgvector/pgvector:pg16 走同一 mirror 可拉;tag 一下 compose 即可找到。
pull-db:
	@echo "Pulling pgvector/pgvector:pg16 (avoids daocloud.io 403 on library/postgres:16-pgvector upstream)..."
	docker pull pgvector/pgvector:pg16
	docker tag pgvector/pgvector:pg16 postgres:16-pgvector
	@echo "Tagged pgvector/pgvector:pg16 → postgres:16-pgvector (compose can now find it locally)"
