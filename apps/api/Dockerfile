# syntax=docker/dockerfile:1
# ── Elliott Wave Lab — FastAPI backend (Python 3.12 + uv) ──
# Built from the REPO ROOT as context: the API imports the engine/ and
# analyst/ packages, so docker-compose sets `context: .` for this service.

# ---- Stage 1: build ----
# Astral's image ships Python 3.12 + the `uv` package manager preinstalled.
# It is built on python:3.12-slim-bookworm, so the venv it produces resolves
# against the same interpreter path as the runtime stage below.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

# UV_COMPILE_BYTECODE: precompile .pyc at build time → faster container startup.
# UV_LINK_MODE=copy: avoid hardlink warnings on Docker's overlay filesystem.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1) Install ONLY dependencies first, from the lockfiles. Docker caches this
#    layer and re-runs it solely when pyproject.toml / uv.lock change — editing
#    source code below won't trigger a slow dependency reinstall.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra api

# 2) Copy the source the API needs — the engine, the analyst (incl. the prebuilt
#    RAG corpus under analyst/theory/data/), the infra adapters, and the api layer
#    — then install the project itself into the venv.
COPY engine/ ./engine/
COPY analyst/ ./analyst/
COPY infra/ ./infra/
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api/ ./apps/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra api

# ---- Stage 2: run ----
FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

# PYTHONUNBUFFERED: flush logs immediately instead of buffering them.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=builder /app /app

# Put the project venv on PATH so `uvicorn` resolves without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# Drop root: code stays root-owned (read-only); only the cache dir needs writing.
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data && chown app:app /app/data \
    && mkdir -p /app/analyst/.cache && chown app:app /app/analyst/.cache

ENV EWL_CACHE_DIR=/app/data/.cache
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# --host 0.0.0.0 makes the port reachable from outside the container (not just
# loopback inside it). Maps to the host via docker-compose `ports`.
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
