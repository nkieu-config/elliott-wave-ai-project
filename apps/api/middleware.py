"""Pure-ASGI middlewares (not BaseHTTPMiddleware) so the SSE narration stream is
never buffered: header injection wraps ``send``, the concurrency guard holds a slot
for the whole response and releases in ``finally``."""

from __future__ import annotations

import json
import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_log = logging.getLogger(__name__)

RELEASE_SCOPE_KEY = "ewl.release_concurrency_slot"


class SecurityHeadersMiddleware:
    """Static hardening headers on every response. No CSP: a JSON API loads no
    sub-resources, and a strict ``default-src`` would break the dev ``/docs`` UI."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self._extra: list[tuple[bytes, bytes]] = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
        ]
        if hsts:
            self._extra.append(
                (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in headers}
                headers.extend(
                    (name, value)
                    for name, value in self._extra
                    if name not in present
                )
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ConcurrencyLimitMiddleware:
    """Bounds in-flight heavy requests (POST under ``path_prefix``); excess gets an
    immediate 503 instead of piling onto the engine + LLM. In-process only — one
    guard per worker, not a cluster-wide limit.

    Guarded requests get an idempotent release callable at
    ``scope[RELEASE_SCOPE_KEY]`` so a handler can free its slot once the heavy
    work is done (the SSE route's typewriter playback shouldn't hold capacity);
    unreleased slots still free in ``finally``."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int,
        path_prefix: str = "/api/v1",
        methods: frozenset[str] = frozenset({"POST"}),
    ) -> None:
        self.app = app
        self.limit = limit
        self.path_prefix = path_prefix
        self.methods = methods
        self._inflight = 0

    def _guarded(self, scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope.get("method") in self.methods
            and scope.get("path", "").startswith(self.path_prefix)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.limit <= 0 or not self._guarded(scope):
            await self.app(scope, receive, send)
            return

        # Check-then-increment runs without an await between, so it is atomic on the
        # single-threaded event loop — no lock needed.
        if self._inflight >= self.limit:
            _log.warning(
                "concurrency limit %d reached; rejecting %s", self.limit, scope["path"]
            )
            await _send_busy(send)
            return

        self._inflight += 1
        released = False

        def release() -> None:
            nonlocal released
            if not released:
                released = True
                self._inflight -= 1

        scope[RELEASE_SCOPE_KEY] = release
        try:
            await self.app(scope, receive, send)
        finally:
            release()


async def _send_busy(send: Send) -> None:
    body = json.dumps({"detail": "Server busy — retry shortly"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", b"2"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
