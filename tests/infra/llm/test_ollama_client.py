import threading

import httpx
import pytest

from infra.llm.ollama_client import (
    _DEFAULT_FALLBACK_MODEL,
    _DEFAULT_PRIMARY_MODEL,
    OllamaClient,
)

_HI = [{"role": "user", "content": "hi"}]


class _FakeClient:
    def __init__(self, host, headers=None, timeout=None):
        self.host = host
        self.headers = headers or {}
        self.timeout = timeout
        self.calls = []
        self._response_queue: list = []
        self._raise_queue: list = []

    def chat(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        if self._raise_queue and self._raise_queue[0] is not None:
            err = self._raise_queue.pop(0)
            raise err
        if self._raise_queue:
            self._raise_queue.pop(0)
        return {"message": {"content": self._response_queue.pop(0)}}


class _FakeOllamaModule:
    def __init__(self):
        self.clients: list[_FakeClient] = []
        self._cloud_plan: list = []
        self._local_plan: list = []

    def Client(self, host, headers=None, timeout=None):  # noqa: N802
        c = _FakeClient(host, headers, timeout=timeout)
        if host.startswith("https"):
            for entry in self._cloud_plan:
                if isinstance(entry, BaseException):
                    c._raise_queue.append(entry)
                else:
                    c._response_queue.append(entry)
                    c._raise_queue.append(None)
        else:
            for entry in self._local_plan:
                if isinstance(entry, BaseException):
                    c._raise_queue.append(entry)
                else:
                    c._response_queue.append(entry)
                    c._raise_queue.append(None)
        self.clients.append(c)
        return c


def test_complete_uses_cloud_when_api_key_present():
    fake = _FakeOllamaModule()
    fake._cloud_plan = ["primary output"]
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        api_key="test-key",
        ollama_module=fake,
    )
    out = c.complete(_HI)
    assert out == "primary output"
    assert c.model_id == "qwen3-next:80b-cloud"
    cloud_client = next(cl for cl in fake.clients if cl.host.startswith("https"))
    assert cloud_client.headers["Authorization"] == "Bearer test-key"


def test_complete_falls_back_to_local_on_cloud_error():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [ConnectionError("cloud 403")]
    fake._local_plan = ["fallback output"]
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        api_key="test-key",
        ollama_module=fake,
        max_retries=0,
    )
    out = c.complete(_HI)
    assert out == "fallback output"
    assert c.model_id == "qwen3.5:9b"


def test_no_api_key_skips_cloud_path(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    fake = _FakeOllamaModule()
    fake._local_plan = ["local-only output"]
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        api_key=None,
        ollama_module=fake,
    )
    out = c.complete(_HI)
    assert out == "local-only output"
    assert c.model_id == "qwen3.5:9b"
    assert all(not cl.host.startswith("https") for cl in fake.clients)


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "env-key")
    fake = _FakeOllamaModule()
    fake._cloud_plan = ["ok"]
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        ollama_module=fake,
    )
    assert c.api_key == "env-key"
    out = c.complete(_HI)
    assert out == "ok"


def test_complete_sends_system_role_and_generation_options():
    fake = _FakeOllamaModule()
    fake._cloud_plan = ["ok"]
    c = OllamaClient(primary_model="m", api_key="k", ollama_module=fake)
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]
    c.complete(messages)
    cloud = next(cl for cl in fake.clients if cl.host.startswith("https"))
    _model, sent_messages, sent_kwargs = cloud.calls[0]
    assert sent_messages == messages
    opts = sent_kwargs["options"]
    assert opts["temperature"] == 0.2
    assert opts["num_ctx"] == 32768
    assert "seed" in opts


def test_complete_forwards_format_to_chat_when_provided():
    fake = _FakeOllamaModule()
    fake._cloud_plan = ["{}", "{}"]
    c = OllamaClient(primary_model="m", api_key="k", ollama_module=fake)
    schema = {"type": "object"}
    c.complete(_HI, format=schema)
    c.complete(_HI)
    cloud = next(cl for cl in fake.clients if cl.host.startswith("https"))
    _m, _msg, kw_with = cloud.calls[0]
    _m, _msg, kw_without = cloud.calls[1]
    assert kw_with["format"] == schema
    assert "format" not in kw_without


def test_model_names_resolved_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_PRIMARY_MODEL", "env-primary")
    monkeypatch.setenv("OLLAMA_FALLBACK_MODEL", "env-fallback")
    c = OllamaClient(ollama_module=_FakeOllamaModule())
    assert c.primary_model == "env-primary"
    assert c.fallback_model == "env-fallback"


def test_explicit_model_arg_overrides_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_PRIMARY_MODEL", "env-primary")
    c = OllamaClient(primary_model="explicit", ollama_module=_FakeOllamaModule())
    assert c.primary_model == "explicit"


def test_default_models_when_no_arg_and_no_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_FALLBACK_MODEL", raising=False)
    c = OllamaClient(ollama_module=_FakeOllamaModule())
    assert c.primary_model == _DEFAULT_PRIMARY_MODEL
    assert c.fallback_model == _DEFAULT_FALLBACK_MODEL


def test_timeout_passed_to_cloud_and_local_clients(monkeypatch):
    monkeypatch.delenv("OLLAMA_CLOUD_TIMEOUT_S", raising=False)
    monkeypatch.delenv("OLLAMA_LOCAL_TIMEOUT_S", raising=False)
    fake = _FakeOllamaModule()
    OllamaClient(api_key="k", ollama_module=fake,
                 cloud_timeout_s=42.0, local_timeout_s=7.5)
    cloud = next(cl for cl in fake.clients if cl.host.startswith("https"))
    local = next(cl for cl in fake.clients if not cl.host.startswith("https"))
    assert cloud.timeout == 42.0
    assert local.timeout == 7.5


def test_timeout_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_CLOUD_TIMEOUT_S", "33")
    monkeypatch.setenv("OLLAMA_LOCAL_TIMEOUT_S", "11")
    fake = _FakeOllamaModule()
    OllamaClient(api_key="k", ollama_module=fake)
    cloud = next(cl for cl in fake.clients if cl.host.startswith("https"))
    local = next(cl for cl in fake.clients if not cl.host.startswith("https"))
    assert cloud.timeout == 33.0
    assert local.timeout == 11.0


def test_unexpected_exception_propagates_not_fallback():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [AttributeError("real bug")]
    fake._local_plan = ["would-be fallback"]
    c = OllamaClient(api_key="k", ollama_module=fake)
    with pytest.raises(AttributeError, match="real bug"):
        c.complete(_HI)


def test_retry_recovers_on_second_attempt_without_fallback():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [ConnectionError("transient blip"), "cloud output"]
    fake._local_plan = ["should NOT be used"]
    sleeps: list[float] = []
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        api_key="k",
        ollama_module=fake,
        max_retries=1,
        sleep=sleeps.append,
    )
    out = c.complete(_HI)
    assert out == "cloud output"
    assert c.model_id == "qwen3-next:80b-cloud"
    assert sleeps == [0.5]


def test_retry_exhausted_then_falls_back_to_local():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [
        ConnectionError("blip 1"),
        ConnectionError("blip 2"),
    ]
    fake._local_plan = ["local output"]
    sleeps: list[float] = []
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud",
        fallback_model="qwen3.5:9b",
        api_key="k",
        ollama_module=fake,
        max_retries=1,
        sleep=sleeps.append,
    )
    out = c.complete(_HI)
    assert out == "local output"
    assert c.model_id == "qwen3.5:9b"
    assert sleeps == [0.5]


def test_retry_backoff_doubles_per_attempt():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [
        ConnectionError("1"),
        ConnectionError("2"),
        ConnectionError("3"),
        "ok",
    ]
    fake._local_plan = []
    sleeps: list[float] = []
    c = OllamaClient(
        primary_model="m",
        api_key="k",
        ollama_module=fake,
        max_retries=3,
        sleep=sleeps.append,
    )
    c.complete(_HI)
    assert sleeps == [0.5, 1.0, 2.0]


def test_max_retries_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MAX_RETRIES", "3")
    fake = _FakeOllamaModule()
    c = OllamaClient(api_key="k", ollama_module=fake)
    assert c.max_retries == 3


def test_malformed_response_shape_surfaces_not_treated_as_transient():
    class _BadClient:
        def chat(self, model, messages, **kwargs):
            return {"unexpected": "shape"}  # no "message" key → KeyError on parse

    class _BadModule:
        def Client(self, host, headers=None, timeout=None):  # noqa: N802
            return _BadClient()

    c = OllamaClient(api_key="k", ollama_module=_BadModule(), max_retries=0)
    # The parse error must propagate (real bug), not be swallowed as a transport
    # blip and collapsed into a generic "both providers failed" RuntimeError.
    with pytest.raises(KeyError, match="message"):
        c.complete(_HI)


def test_negative_max_retries_clamped_to_zero():
    c = OllamaClient(api_key="k", ollama_module=_FakeOllamaModule(), max_retries=-3)
    assert c.max_retries == 0


def test_cache_model_id_is_stable_across_fallover():
    fake = _FakeOllamaModule()
    fake._cloud_plan = [ConnectionError("blip")]
    fake._local_plan = ["local out"]
    c = OllamaClient(
        primary_model="P", fallback_model="F", api_key="k",
        ollama_module=fake, max_retries=0,
    )
    assert c.cache_model_id == "P"
    c.complete(_HI)                    # fallover flips the volatile model_id
    assert c.model_id == "F"
    assert c.cache_model_id == "P"     # stable id is unaffected → stable cache key


def test_cache_model_id_is_fallback_when_cloud_disabled(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    c = OllamaClient(
        primary_model="P", fallback_model="F", api_key=None,
        ollama_module=_FakeOllamaModule(),
    )
    assert c.cache_model_id == "F"


def test_cloud_read_timeout_falls_over_to_local():
    # httpx.ReadTimeout is not a builtin TimeoutError/OSError — must still be caught.
    fake = _FakeOllamaModule()
    fake._cloud_plan = [httpx.ReadTimeout("timed out")]
    fake._local_plan = ["local output"]
    c = OllamaClient(
        primary_model="qwen3-next:80b-cloud", fallback_model="qwen3.5:9b",
        api_key="k", ollama_module=fake, max_retries=0,
    )
    assert c.complete(_HI) == "local output"
    assert c.model_id == "qwen3.5:9b"


def test_cloud_concurrency_default_is_one(monkeypatch):
    monkeypatch.delenv("OLLAMA_CLOUD_CONCURRENCY", raising=False)
    c = OllamaClient(api_key="k", ollama_module=_FakeOllamaModule())
    assert c.cloud_concurrency == 1


def test_cloud_concurrency_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_CLOUD_CONCURRENCY", "3")
    c = OllamaClient(api_key="k", ollama_module=_FakeOllamaModule())
    assert c.cloud_concurrency == 3


def test_cloud_concurrency_clamped_to_one():
    c = OllamaClient(api_key="k", ollama_module=_FakeOllamaModule(), cloud_concurrency=0)
    assert c.cloud_concurrency == 1


def test_cloud_calls_are_serialised_by_semaphore():
    # N threads hit the shared singleton; the semaphore must keep concurrent
    # in-flight cloud chats ≤ cloud_concurrency (here 1).
    observed_max = 0
    inflight = 0
    state_lock = threading.Lock()
    start = threading.Barrier(4)

    class _ConcClient:
        def __init__(self, host, headers=None, timeout=None):
            self.host = host

        def chat(self, model, messages, **kwargs):
            nonlocal observed_max, inflight
            with state_lock:
                inflight += 1
                observed_max = max(observed_max, inflight)
            # Hold the slot so a leak would overlap with a peer.
            threading.Event().wait(0.02)
            with state_lock:
                inflight -= 1
            return {"message": {"content": "ok"}}

    class _ConcModule:
        def Client(self, host, headers=None, timeout=None):  # noqa: N802
            return _ConcClient(host, headers, timeout)

    c = OllamaClient(api_key="k", ollama_module=_ConcModule(), cloud_concurrency=1)

    def worker():
        start.wait()
        c.complete(_HI)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert observed_max == 1
