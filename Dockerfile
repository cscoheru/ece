FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (Docker layer cache)
COPY pyproject.toml uv.lock ./

# Install runtime dependencies (no dev group)
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/

# Set environment
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8000

# Container-level healthcheck (docker compose service healthcheck overrides this)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=15s \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# Run uvicorn
CMD ["uv", "run", "uvicorn", "ece.main:app", "--host", "0.0.0.0", "--port", "8000"]
