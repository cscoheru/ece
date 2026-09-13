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
