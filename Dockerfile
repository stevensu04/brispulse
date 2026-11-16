# BrisPulse service image. The web app build stage is added in M3.

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
USER brispulse
EXPOSE 8000
# Apply migrations with `alembic upgrade head` as a release step before starting.
CMD ["uvicorn", "brispulse.main:app", "--host", "0.0.0.0", "--port", "8000"]
