# BrisPulse: one image holding the API, the collector and the built web app.

FROM node:22-slim AS web
WORKDIR /web
# Dependencies first: this layer is reused until the lock file changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.13.8
WORKDIR /app
# Dependencies first: this layer is reused until the lock file changes.
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --no-create-home brispulse
WORKDIR /app
COPY --from=build /app /app
COPY --from=web /web/dist /app/web
ENV BRISPULSE_WEB_DIR=/app/web
USER brispulse
EXPOSE 8000
# One process only: live state is held in memory.
# Hosts that assign the port set PORT; otherwise 8000.
# With a database, apply migrations first: `alembic upgrade head`.
CMD ["sh", "-c", "exec uvicorn brispulse.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
