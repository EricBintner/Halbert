"""HalbertModelBackend: TierRouter delegation with raw-Ollama fallback.

app_seam imports haloysius at module level, so these tests skip when the
cognition extra is not installed (same convention as test_phase_d_integration).
"""

from __future__ import annotations

import pytest

pytest.importorskip("haloysius")

from halbert_core.integrations.app_seam import HalbertModelBackend  # noqa: E402
from halbert_core.model.providers.base import ModelResponse  # noqa: E402


class _FakeProvider:
    pass


class _FakeRouter:
    """Duck-typed TierRouter: records generate() calls."""

    def __init__(self, text: str = "routed", fail: bool = False):
        self.text = text
        self.fail = fail
        self.calls: list[dict] = []
        self.provider = _FakeProvider()
        self.config = type("Cfg", (), {"models": {"guide-m": object()}})()

    def generate(self, prompt, images=None, prefer_specialist=False, task_type=None, **kwargs):
        self.calls.append(
            dict(prompt=prompt, prefer_specialist=prefer_specialist, task_type=task_type, **kwargs)
        )
        if self.fail:
            raise RuntimeError("router exploded")
        resp = ModelResponse(
            text=self.text, model_id="guide-m", provider="fake", tokens_used=1, latency_ms=1.0
        )
        return resp, object()

    # raw_provider() path
    def select_model(self, tier, **kwargs):
        return type("Sel", (), {"model": object()})()

    def _get_provider(self, model):
        return self.provider


class _FakeResp:
    def __init__(self, content: str = "raw", lines: list[bytes] | None = None):
        self._content = content
        self._lines = lines or []

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self._content}}

    def iter_lines(self):
        return iter(self._lines)


def _patch_ollama(monkeypatch, seen: dict, resp: _FakeResp):
    import requests

    def fake_post(url, json=None, **kwargs):
        seen["url"] = url
        seen["json"] = json
        return resp

    monkeypatch.setattr(requests, "post", fake_post)


def test_chat_delegates_to_tier_router(monkeypatch):
    backend = HalbertModelBackend()
    router = _FakeRouter()
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)

    out = backend.chat(
        [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi there"}],
        temperature=0.2,
        max_tokens=64,
    )

    assert out == "routed"
    call = router.calls[0]
    assert "be terse" in call["prompt"]
    assert "hi there" in call["prompt"]
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 64


def test_chat_falls_back_to_ollama_when_router_unavailable(monkeypatch):
    backend = HalbertModelBackend(ollama_url="http://ollama.test", model="m0")
    monkeypatch.setattr(backend, "_get_tier_router", lambda: None)
    seen: dict = {}
    _patch_ollama(monkeypatch, seen, _FakeResp("raw"))

    assert backend.chat([{"role": "user", "content": "hi"}]) == "raw"
    assert seen["url"] == "http://ollama.test/api/chat"
    assert seen["json"]["model"] == "m0"
    assert seen["json"]["stream"] is False


def test_chat_falls_back_to_ollama_when_router_raises(monkeypatch):
    backend = HalbertModelBackend(ollama_url="http://ollama.test")
    router = _FakeRouter(fail=True)
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)
    seen: dict = {}
    _patch_ollama(monkeypatch, seen, _FakeResp("raw"))

    assert backend.chat([{"role": "user", "content": "hi"}]) == "raw"
    assert router.calls, "router should have been tried first"
    assert seen["url"] == "http://ollama.test/api/chat"


def test_stream_uses_ollama_path_not_router(monkeypatch):
    backend = HalbertModelBackend(ollama_url="http://ollama.test")
    router = _FakeRouter(fail=True)  # would raise if touched
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)
    seen: dict = {}
    lines = [b'{"message": {"content": "a"}}', b"", b'{"message": {"content": "b"}}']
    _patch_ollama(monkeypatch, seen, _FakeResp(lines=lines))

    chunks = list(backend.chat([{"role": "user", "content": "hi"}], stream=True))

    assert chunks == ["a", "b"]
    assert not router.calls
    assert seen["json"]["stream"] is True


def test_explicit_model_kwarg_bypasses_router(monkeypatch):
    backend = HalbertModelBackend(ollama_url="http://ollama.test", model="default-m")
    router = _FakeRouter(fail=True)
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)
    seen: dict = {}
    _patch_ollama(monkeypatch, seen, _FakeResp("raw"))

    assert backend.chat([{"role": "user", "content": "hi"}], model="pinned-m") == "raw"
    assert not router.calls
    assert seen["json"]["model"] == "pinned-m"


def test_raw_provider_returns_router_provider(monkeypatch):
    backend = HalbertModelBackend()
    router = _FakeRouter()
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)
    assert backend.raw_provider() is router.provider


def test_raw_provider_none_without_router(monkeypatch):
    backend = HalbertModelBackend()
    monkeypatch.setattr(backend, "_get_tier_router", lambda: None)
    assert backend.raw_provider() is None


def test_get_tier_router_treats_empty_config_as_unavailable(monkeypatch):
    """A TierRouter that found no models.yml (models == {}) can't route
    anything; treat it as unavailable so chat() goes straight to Ollama
    instead of raising ModelNotFoundError on every call."""
    import halbert_core.model.tier_router as tr

    class _EmptyRouter:
        def __init__(self, *a, **k):
            self.config = type("Cfg", (), {"models": {}})()

    monkeypatch.setattr(tr, "TierRouter", _EmptyRouter)
    backend = HalbertModelBackend()
    assert backend._get_tier_router() is None
    # cached: second call doesn't retry construction
    assert backend._get_tier_router() is None


def test_get_tier_router_caches_instance(monkeypatch):
    import halbert_core.model.tier_router as tr

    built = []

    class _Router:
        def __init__(self, *a, **k):
            built.append(self)
            self.config = type("Cfg", (), {"models": {"m": object()}})()

    monkeypatch.setattr(tr, "TierRouter", _Router)
    backend = HalbertModelBackend()
    r1 = backend._get_tier_router()
    r2 = backend._get_tier_router()
    assert r1 is r2
    assert len(built) == 1
