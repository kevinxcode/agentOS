FROM ghcr.io/astral-sh/uv:0.12.8 AS uv

FROM python:3.13.5-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1

WORKDIR /app

COPY --from=uv /uv /uvx /bin/

COPY services/api/pyproject.toml ./pyproject.toml
COPY services/api/uv.lock ./uv.lock
RUN apt-get update \
    && apt-get upgrade --yes \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --frozen --no-dev --no-install-project

COPY services/api/src ./src
COPY services/api/alembic.ini ./alembic.ini
COPY services/api/alembic ./alembic
COPY scripts/bootstrap_admin.py scripts/backup_archive.py ./scripts/
RUN uv sync --frozen --no-dev \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin agentos

ENV PATH="/app/.venv/bin:$PATH"

USER agentos

EXPOSE 8000

CMD ["uvicorn", "agentos.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
