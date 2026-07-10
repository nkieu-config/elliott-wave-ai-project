"""Unit tests for the pure-ASGI middlewares: header injection and the in-process
concurrency guard. Driven with asyncio.run (no pytest-asyncio dependency)."""

from __future__ import annotations

import asyncio
import contextlib

from apps.api.middleware import (
    RELEASE_SCOPE_KEY,
    ConcurrencyLimitMiddleware,
    SecurityHeadersMiddleware,
)

_POST_SCOPE = {"type": "http", "method": "POST", "path": "/api/v1/pipeline"}


async def _noop_receive() -> dict:
    return {"type": "http.request", "body": b"", "more_body": False}


def _drive(app, scope) -> list[dict]:
    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(app(scope, _noop_receive, send))
    return sent


async def _ok_app(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_security_headers_injected_once():
    mw = SecurityHeadersMiddleware(_ok_app, hsts=False)
    sent = _drive(mw, {"type": "http", "method": "GET", "path": "/x"})
    headers = dict(sent[0]["headers"])
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"x-frame-options"] == b"DENY"
    assert headers[b"referrer-policy"] == b"no-referrer"
    assert b"strict-transport-security" not in headers


def test_security_headers_add_hsts_when_enabled():
    mw = SecurityHeadersMiddleware(_ok_app, hsts=True)
    sent = _drive(mw, {"type": "http", "method": "GET", "path": "/x"})
    headers = dict(sent[0]["headers"])
    assert headers[b"strict-transport-security"].startswith(b"max-age=")


def test_security_headers_do_not_clobber_existing():
    async def app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-frame-options", b"SAMEORIGIN")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    mw = SecurityHeadersMiddleware(app, hsts=False)
    sent = _drive(mw, {"type": "http", "method": "GET", "path": "/x"})
    frame_values = [v for k, v in sent[0]["headers"] if k == b"x-frame-options"]
    assert frame_values == [b"SAMEORIGIN"]


def test_concurrency_guard_rejects_when_saturated():
    called: list[str] = []

    async def app(scope, receive, send):
        called.append(scope["path"])

    mw = ConcurrencyLimitMiddleware(app, limit=1)
    mw._inflight = 1
    sent = _drive(mw, _POST_SCOPE)
    assert called == []  # app never ran
    assert sent[0]["status"] == 503
    assert (b"retry-after", b"2") in sent[0]["headers"]


def test_concurrency_guard_allows_and_releases_slot():
    mw = ConcurrencyLimitMiddleware(_ok_app, limit=1)
    _drive(mw, _POST_SCOPE)
    assert mw._inflight == 0  # released in finally


def test_concurrency_guard_releases_slot_on_app_error():
    async def boom(scope, receive, send):
        raise RuntimeError("downstream failed")

    mw = ConcurrencyLimitMiddleware(boom, limit=1)
    with contextlib.suppress(RuntimeError):
        _drive(mw, _POST_SCOPE)
    assert mw._inflight == 0  # slot not leaked on exception


def test_concurrency_guard_early_release_frees_slot_mid_response():
    inflight_after_release: list[int] = []

    async def app(scope, receive, send):
        scope[RELEASE_SCOPE_KEY]()
        inflight_after_release.append(mw._inflight)
        await _ok_app(scope, receive, send)

    mw = ConcurrencyLimitMiddleware(app, limit=1)
    _drive(mw, dict(_POST_SCOPE))
    assert inflight_after_release == [0]  # slot freed before the response finished
    assert mw._inflight == 0  # finally's release is a no-op, no double decrement


def test_concurrency_guard_release_is_idempotent():
    async def app(scope, receive, send):
        scope[RELEASE_SCOPE_KEY]()
        scope[RELEASE_SCOPE_KEY]()
        await _ok_app(scope, receive, send)

    mw = ConcurrencyLimitMiddleware(app, limit=1)
    _drive(mw, dict(_POST_SCOPE))
    assert mw._inflight == 0


def test_concurrency_guard_ignores_non_post_even_when_full():
    called: list[str] = []

    async def app(scope, receive, send):
        called.append(scope["path"])

    mw = ConcurrencyLimitMiddleware(app, limit=1)
    mw._inflight = 5
    _drive(mw, {"type": "http", "method": "GET", "path": "/api/health"})
    assert called == ["/api/health"]


def test_concurrency_guard_disabled_when_limit_zero():
    called: list[str] = []

    async def app(scope, receive, send):
        called.append(scope["path"])

    mw = ConcurrencyLimitMiddleware(app, limit=0)
    mw._inflight = 999
    _drive(mw, _POST_SCOPE)
    assert called == ["/api/v1/pipeline"]
