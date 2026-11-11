# syntax=docker/dockerfile:1
# Build context: repository root (needs apps/api and apps/worker).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip install --upgrade pip && pip install .

COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./
COPY apps/worker/worker ./worker

RUN useradd --create-home --uid 10001 tenderos && mkdir -p /srv/var && chown -R tenderos /srv/var
USER tenderos
ENV PYTHONPATH=/srv
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]
