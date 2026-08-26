"""HalbertModelBackend: TierRouter delegation with raw-Ollama fallback.

app_seam imports haloysius lazily (B7), so these tests run without the
cognition extra; they exercise only the TierRouter/Ollama paths.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from halbert_core.integrations.app_seam import HalbertModelBackend
from halbert_core.model.providers.base import ModelResponse


@pytest.fixture(autouse=True)
def _isolate_model_config(monkeypatch):
    """Never read the developer's real models.yml / env when constructing
    HalbertModelBackend() with no explicit model."""
    import halbert_core.model.client as client

    monkeypatch.delenv("HALBERT_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.setattr(client, "get_configured_model", lambda: "guide-x")
    monkeypatch.setattr(client, "get_ollama_endpoint", lambda: "http://ep.test")


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


def test_get_tier_router_caches_instance(monkeypatch, tmp_path):
    import halbert_core.model.tier_router as tr

    # _get_tier_router requires a user models.yml; make that deterministic
    # regardless of $HOME (the suite is also run with HOME=<empty tmp>).
    monkeypatch.delenv("HALBERT_MODELS_CONFIG", raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path)
    (tmp_path / "models.yml").write_text("models: {}\n")

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


# -- B3: defaults converge on the agent's config ---------------------------


def test_default_model_comes_from_configured_guide_model():
    backend = HalbertModelBackend()
    assert backend.model == "guide-x"
    assert backend.ollama_url == "http://ep.test"
    assert backend.model != "llama3.2"


def test_env_and_explicit_model_override_configured(monkeypatch):
    monkeypatch.setenv("HALBERT_MODEL", "envm")
    assert HalbertModelBackend().model == "envm"
    assert HalbertModelBackend(model="m1").model == "m1"
    monkeypatch.setenv("OLLAMA_URL", "http://env.ollama")
    assert HalbertModelBackend().ollama_url == "http://env.ollama"
    assert HalbertModelBackend(ollama_url="http://x").ollama_url == "http://x"


def test_default_model_falls_back_when_config_unreadable(monkeypatch):
    import halbert_core.model.client as client

    def boom():
        raise RuntimeError("no config")

    monkeypatch.setattr(client, "get_configured_model", boom)
    monkeypatch.setattr(client, "get_ollama_endpoint", boom)
    backend = HalbertModelBackend()
    assert backend.model == "llama3.1:8b"
    assert backend.ollama_url == "http://localhost:11434"


def test_tier_router_built_from_config_dir_models_yml(monkeypatch, tmp_path):
    """Router config_path comes from config_locator (user file), same as chat."""
    import halbert_core.model.tier_router as tr

    seen = {}

    class _Router:
        def __init__(self, config_path=None, **k):
            seen["config_path"] = config_path
            self.config = type("Cfg", (), {"models": {"m": object()}})()

    monkeypatch.setattr(tr, "TierRouter", _Router)
    monkeypatch.delenv("HALBERT_MODELS_CONFIG", raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path)
    (tmp_path / "models.yml").write_text("models: {}\n")
    backend = HalbertModelBackend()
    assert backend._get_tier_router() is not None
    assert seen["config_path"] == tmp_path / "models.yml"


def test_tier_router_unavailable_without_user_file(monkeypatch, tmp_path):
    """No user models.yml (and no env override): never construct TierRouter,
    which would otherwise fall through to the repo config."""
    import halbert_core.model.tier_router as tr

    class _Boom:
        def __init__(self, *a, **k):
            raise AssertionError("TierRouter must not be constructed")

    monkeypatch.setattr(tr, "TierRouter", _Boom)
    monkeypatch.delenv("HALBERT_MODELS_CONFIG", raising=False)
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path)
    backend = HalbertModelBackend()
    assert backend._get_tier_router() is None
    assert backend._tier_router_unavailable is True
    assert backend._get_tier_router() is None


def test_tier_router_honours_env_override(monkeypatch, tmp_path):
    import halbert_core.model.tier_router as tr

    seen = {}

    class _Router:
        def __init__(self, config_path=None, **k):
            seen["config_path"] = config_path
            self.config = type("Cfg", (), {"models": {"m": object()}})()

    monkeypatch.setattr(tr, "TierRouter", _Router)
    env_file = tmp_path / "override.yml"
    env_file.write_text("models: {}\n")
    monkeypatch.setenv("HALBERT_MODELS_CONFIG", str(env_file))
    monkeypatch.setattr("halbert_core.model.config_locator.get_config_dir", lambda: tmp_path / "nouser")
    backend = HalbertModelBackend()
    assert backend._get_tier_router() is not None
    assert seen["config_path"] == env_file


def test_generate_text_flattens_to_single_user_message(monkeypatch):
    backend = HalbertModelBackend()
    router = _FakeRouter("thought")
    monkeypatch.setattr(backend, "_get_tier_router", lambda: router)
    assert backend.generate_text("ping") == "thought"
    assert "ping" in router.calls[0]["prompt"]
    assert router.calls[0]["max_tokens"] == 256


# -- B7: haloysius is optional at import time ------------------------------


def test_app_seam_importable_without_haloysius(monkeypatch):
    monkeypatch.setitem(sys.modules, "haloysius", None)
    monkeypatch.setitem(sys.modules, "haloysius.seam", None)
    monkeypatch.delitem(sys.modules, "halbert_core.integrations.app_seam", raising=False)
    try:
        mod = importlib.import_module("halbert_core.integrations.app_seam")
        backend = mod.HalbertModelBackend()
        assert backend.model == "guide-x"
    finally:
        sys.modules.pop("halbert_core.integrations.app_seam", None)
        importlib.import_module("halbert_core.integrations.app_seam")


def test_wire_halbert_seam_registers_lazily(monkeypatch):
    pytest.importorskip("haloysius")
    import haloysius.seam as hs
    from halbert_core.integrations.app_seam import HalbertAppSeam, wire_halbert_seam

    registered = []
    monkeypatch.setattr(hs, "register_app_seam", lambda seam: registered.append(seam))
    seam = wire_halbert_seam(skip_retrieval=True, skip_model=True)
    assert registered == [seam]
    assert isinstance(seam, HalbertAppSeam)
