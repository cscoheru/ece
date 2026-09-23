FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (Docker layer cache)
COPY pyproject.toml uv.lock ./

# Copy source BEFORE uv sync (setuptools build_meta needs src/ for editable install)
COPY src/ ./src/

# cut-045R3 R13-B1 fix — Phase 6 in-container commands need:
#   1. scripts/       — three seed scripts (procurement / knowledge / compliance)
#   2. alembic.ini    — alembic reads it from CWD (/app); the canonical config
#                       lives at src/ece/migrations/alembic.ini, so we copy
#                       it to /app/alembic.ini so `alembic upgrade head`
#                       works without a -c flag. script_location in alembic.ini
#                       points to src/ece/migrations (relative to prepend_sys_path=.),
#                       which already exists from the COPY src/ above.
COPY scripts/ ./scripts/
COPY src/ece/migrations/alembic.ini ./alembic.ini

# Install runtime dependencies (no dev group)
RUN uv sync --frozen --no-dev

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

# Container-level healthcheck (docker compose service healthcheck overrides this)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://localhost:8000/healthz').status==200 else 1)" || exit 1

# Run uvicorn
CMD ["uv", "run", "uvicorn", "ece.main:app", "--host", "0.0.0.0", "--port", "8000"]
