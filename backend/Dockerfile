FROM python:3.11-slim

RUN pip install uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY api/ api/
COPY agent/ agent/
COPY db/ db/
COPY models/ models/
COPY utils/ utils/
COPY __init__.py .

# Alembic migrations run automatically at app startup (api.main lifespan)
COPY alembic.ini ./
COPY migrations/ migrations/

EXPOSE 8000

# The app sits behind a proxy chain (Caddy -> frontend nginx) that strips an
# /api prefix, so trust forwarded headers for scheme detection and declare the
# external prefix so OAuth redirect URIs are generated with it.
CMD ["uv", "run", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--root-path", "/api"]
