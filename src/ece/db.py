"""DB engine singleton + session helpers (S1.1 / S1.2 / S1.4 dependency)."""

from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Singleton SQLAlchemy Engine.

    DATABASE_URL env override -> defaults to compose db:
      postgresql+psycopg://ece:ece@localhost:5432/ece
    (compose exposes 5432 on host; use docker compose up -d db to start.)
    """
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://ece:ece@localhost:5432/ece",
    )
    return create_engine(url, future=True)
