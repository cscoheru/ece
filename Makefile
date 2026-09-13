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

rev:
	uv run alembic downgrade -1

# R5 (cut-003r2): pgvector 镜像源补救 — daocloud.io 对 library/postgres:16-pgvector 403 Forbidden,
# 但 pgvector/pgvector:pg16 走同一 mirror 可拉;tag 一下 compose 即可找到。
pull-db:
	@echo "Pulling pgvector/pgvector:pg16 (avoids daocloud.io 403 on library/postgres:16-pgvector upstream)..."
	docker pull pgvector/pgvector:pg16
	docker tag pgvector/pgvector:pg16 postgres:16-pgvector
	@echo "Tagged pgvector/pgvector:pg16 → postgres:16-pgvector (compose can now find it locally)"
