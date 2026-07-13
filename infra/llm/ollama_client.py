from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("infra.llm.ollama_client")

DEFAULT_CLOUD_HOST = "https://ollama.com"
DEFAULT_LOCAL_HOST = "http://localhost:11434"

_DEFAULT_PRIMARY_MODEL = "gpt-oss:120b"
_DEFAULT_FALLBACK_MODEL = "qwen3.5:9b"

# Large num_ctx so long RAG prompts aren't truncated; fixed seed stabilises narration.
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_NUM_CTX = 32768
_DEFAULT_SEED = 0

# Bounded timeout — ollama default is None, which freezes the UI thread.
_DEFAULT_CLOUD_TIMEOUT_S = 120.0
_DEFAULT_LOCAL_TIMEOUT_S = 60.0

# Cloud 5xx during load spikes usually clears in <2s; cheaper than failing to local 9B.
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_RETRY_BACKOFF_BASE_S = 0.5

# Gate concurrent cloud calls: the cloud model 429s ("too many concurrent
# requests") or stalls past the timeout when all modes fire at once. 1 = serialise.
_DEFAULT_CLOUD_CONCURRENCY = 1


class _NullGate:
    # No-op CM so the cloud-gated call site stays branch-free.
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc: object) -> None:
        return None


_NULL_GATE = _NullGate()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("ignoring non-float %s=%r", name, raw)
        return default


class OllamaClient:
    # Cloud path skipped entirely when OLLAMA_API_KEY is unset.
    def __init__(
        self,
        primary_model: str | None = None,
        fallback_model: str | None = None,
        api_key: str | None = None,
        cloud_host: str = DEFAULT_CLOUD_HOST,
        local_host: str = DEFAULT_LOCAL_HOST,
        ollama_module: Any = None,
        temperature: float = _DEFAULT_TEMPERATURE,
        num_ctx: int = _DEFAULT_NUM_CTX,
        seed: int = _DEFAULT_SEED,
        cloud_timeout_s: float | None = None,
        local_timeout_s: float | None = None,
        max_retries: int | None = None,
        retry_backoff_base_s: float = _DEFAULT_RETRY_BACKOFF_BASE_S,
        cloud_concurrency: int | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        # explicit arg > env override > default.
        self.primary_model = (
            primary_model
            or os.environ.get("OLLAMA_PRIMARY_MODEL")
            or _DEFAULT_PRIMARY_MODEL
        )
        self.fallback_model = (
            fallback_model
            or os.environ.get("OLLAMA_FALLBACK_MODEL")
            or _DEFAULT_FALLBACK_MODEL
        )
        self.model_id = self.primary_model
        # Decoding knobs public so cache key includes them (T=0.2 must not serve T=0.8).
        self.temperature = temperature
        self.seed = seed
        self._options = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "seed": seed,
        }
        self.api_key = api_key or os.environ.get("OLLAMA_API_KEY")
        if ollama_module is None:
            import ollama as ollama_module  # type: ignore
        self._ollama_module = ollama_module

        cloud_to = (
            cloud_timeout_s
            if cloud_timeout_s is not None
            else _env_float("OLLAMA_CLOUD_TIMEOUT_S", _DEFAULT_CLOUD_TIMEOUT_S)
        )
        local_to = (
            local_timeout_s
            if local_timeout_s is not None
            else _env_float("OLLAMA_LOCAL_TIMEOUT_S", _DEFAULT_LOCAL_TIMEOUT_S)
        )
        self.cloud_timeout_s = cloud_to
        self.local_timeout_s = local_to

        # Clamp ≥ 0: negative → range() empty → provider never tried.
        self.max_retries = max(
            0,
            max_retries
            if max_retries is not None
            else int(_env_float("OLLAMA_MAX_RETRIES", _DEFAULT_MAX_RETRIES)),
        )
        self.retry_backoff_base_s = retry_backoff_base_s
        self._sleep = sleep

        # Shared across all threads on the singleton client, so concurrent /analyst
        # streams queue here instead of stampeding the cloud. Clamp ≥ 1.
        concurrency = max(
            1,
            cloud_concurrency
            if cloud_concurrency is not None
            else int(_env_float("OLLAMA_CLOUD_CONCURRENCY", _DEFAULT_CLOUD_CONCURRENCY)),
        )
        self.cloud_concurrency = concurrency
        self._cloud_sema = threading.BoundedSemaphore(concurrency)

        if self.api_key:
            self._cloud = ollama_module.Client(
                host=cloud_host,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=cloud_to,
            )
        else:
            self._cloud = None
        self._local = ollama_module.Client(host=local_host, timeout=local_to)

    @property
    def cache_model_id(self) -> str:
        # Fallover-stable (≠ mutable model_id) so a scenario keys to one cache entry.
        return self.primary_model if self._cloud is not None else self.fallback_model

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        format: Any | None = None,
    ) -> str:
        plan: list[tuple[Any, str]] = []
        if self._cloud is not None:
            plan.append((self._cloud, self.primary_model))
        plan.append((self._local, self.fallback_model))

        # Resolved at call time so stub modules in tests need not expose these.
        request_err = getattr(self._ollama_module, "RequestError", ())
        response_err = getattr(self._ollama_module, "ResponseError", ())
        # Only catch transport/API failures — AttributeError/ZeroDivisionError must surface.
        # httpx.TransportError covers ollama's underlying read/connect timeouts, which are
        # NOT builtin TimeoutError/OSError subclasses and would otherwise skip fallover.
        transient = tuple(
            exc
            for exc in (
                request_err,
                response_err,
                httpx.TransportError,
                ConnectionError,
                TimeoutError,
                OSError,
                KeyError,
                TypeError,
                ValueError,
            )
            if isinstance(exc, type) and issubclass(exc, BaseException)
        )

        chat_kwargs_base: dict[str, Any] = {
            "messages": messages,
            "options": self._options,
        }
        if format is not None:
            chat_kwargs_base["format"] = format

        last_err: Exception | None = None
        for client, model in plan:
            # Serialise cloud calls; local has no shared quota so it runs unthrottled.
            gate = self._cloud_sema if client is self._cloud else _NULL_GATE
            for attempt in range(self.max_retries + 1):
                try:
                    with gate:
                        resp = client.chat(model=model, **chat_kwargs_base)
                except transient as e:
                    last_err = e
                    if attempt < self.max_retries:
                        wait = self.retry_backoff_base_s * (2**attempt)
                        logger.warning(
                            "LLM call failed on %s (attempt %d/%d): %s — "
                            "retry in %.1fs",
                            model, attempt + 1, self.max_retries + 1, e, wait,
                        )
                        self._sleep(wait)
                        continue
                    logger.warning(
                        "LLM call failed on %s (attempt %d/%d): %s — "
                        "falling over to next provider",
                        model, attempt + 1, self.max_retries + 1, e,
                    )
                    break
                else:
                    # Parse outside the try so a malformed-but-200 response surfaces
                    # as a real bug, not a "transient" fallover.
                    self.model_id = model
                    return resp["message"]["content"]
        raise RuntimeError(
            f"Both primary ({self.primary_model}) and fallback "
            f"({self.fallback_model}) failed. Last error: {last_err}"
        )
