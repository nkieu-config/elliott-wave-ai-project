"""FastAPI backend wrapping `engine.pipeline.run_pipeline`.

.env is loaded in the package `__init__` (before any engine import reads EWL_CACHE_DIR).
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.middleware import ConcurrencyLimitMiddleware, SecurityHeadersMiddleware
from apps.api.routers import analyst, health, pipeline, qa
from apps.api.services import analyst_service
from engine.logging_config import configure_logging


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("%s=%r is not an int; using default %d", name, raw, default)
        return default

configure_logging()
_log = logging.getLogger(__name__)

# CORS: explicit allowlist via EWL_API_CORS_ORIGINS (comma-separated, exact).
# Unset → dev regex matching localhost / RFC1918 IPs on any port (fallback ports
# + same-Wi-Fi phones without enumerating IPs).
_EXPLICIT_ORIGINS_ENV = os.environ.get("EWL_API_CORS_ORIGINS")
_IS_PRODUCTION = os.environ.get("EWL_ENV", "").lower() == "production"
_DEV_ORIGIN_REGEX = (
    r"^http://"
    r"(localhost|127\.0\.0\.1|"
    r"10\.\d+\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)"
    r"(:\d+)?$"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the analyst singleton off the request path, in a thread. Non-fatal:
    # the first request loads lazily on failure.
    try:
        await asyncio.to_thread(analyst_service.prewarm)
        _log.info("analyst prewarmed")
    except Exception:
        _log.warning(
            "analyst prewarm failed; resources will load on first request",
            exc_info=True,
        )
    yield


app = FastAPI(
    title="EWL API",
    description="Elliott Wave Lab — pipeline + analyst HTTP API",
    version="0.1.0",
    lifespan=lifespan,
    # No app-level auth → don't publish the API schema/docs in production.
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)
_cors_kwargs: dict[str, Any] = {
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["*"],
}
if _EXPLICIT_ORIGINS_ENV:
    _cors_kwargs["allow_origins"] = [
        origin.strip() for origin in _EXPLICIT_ORIGINS_ENV.split(",") if origin.strip()
    ]
elif _IS_PRODUCTION:
    # Fail-fast: the permissive dev regex (+ allow_credentials) must never serve
    # production. Missing the allowlist is a deploy error, not a silent fallback.
    raise RuntimeError(
        "EWL_API_CORS_ORIGINS must be set in production "
        "(EWL_ENV=production). Set it to the deployed web origin(s)."
    )
else:
    _cors_kwargs["allow_origin_regex"] = _DEV_ORIGIN_REGEX

# Added inner→outer: the concurrency 503 still exits through CORS + security headers,
# so a browser can read it and it carries the hardening headers.
_MAX_CONCURRENCY = _int_env("EWL_API_MAX_CONCURRENCY", 8)
app.add_middleware(ConcurrencyLimitMiddleware, limit=_MAX_CONCURRENCY)
app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(SecurityHeadersMiddleware, hsts=_IS_PRODUCTION)

app.include_router(health.router)
app.include_router(pipeline.router)
app.include_router(analyst.router)
app.include_router(qa.router)
