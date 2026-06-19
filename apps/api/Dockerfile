# syntax=docker/dockerfile:1
# ── Elliott Wave Lab — FastAPI backend (Python 3.12 + uv) ──
# Built from the REPO ROOT as context: the API imports the engine/ and
# analyst/ packages, so docker-compose sets `context: .` for this service.

# Astral's image ships Python 3.12 + the `uv` package manager preinstalled.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# UV_COMPILE_BYTECODE: precompile .pyc at build time → faster container startup.
# UV_LINK_MODE=copy: avoid hardlink warnings on Docker's overlay filesystem.
# PYTHONUNBUFFERED: flush logs immediately instead of buffering them.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Install ONLY dependencies first, from the lockfiles. Docker caches this
#    layer and re-runs it solely when pyproject.toml / uv.lock change — editing
#    source code below won't trigger a slow dependency reinstall.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra api

# 2) Copy the source the API needs — the engine, the analyst (incl. the prebuilt
#    RAG corpus under analyst/theory/data/), and the api layer — then install the
#    project itself into the venv.
COPY engine/ ./engine/
COPY analyst/ ./analyst/
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api/ ./apps/api/
RUN uv sync --frozen --no-dev --extra api

# Put the project venv on PATH so `uvicorn` resolves without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

# Drop root: code stays root-owned (read-only); only the cache dir needs writing.
RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /app/data && chown app:app /app/data

ENV EWL_CACHE_DIR=/app/data/.cache
USER app

EXPOSE 8000
# --host 0.0.0.0 makes the port reachable from outside the container (not just
# loopback inside it). Maps to the host via docker-compose `ports`.
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
