# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Test: PeerProvider registration and transport (S3 / W14).

Home automation simplification (handoff
HOME-AUTOMATION-SIMPLIFICATION-2026-08-30, 5.4 / W14): ``peer`` must be a
first-class provider in the model stack — CHAT_CAPABLE_PROVIDERS,
TierRouter, and the providers package — so a ``peer://`` slot resolves
instead of being disabled as "not chat-capable", and the provider speaks
the paired node's OpenAI-compatible compute contract under
/api/compute/v1.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from halbert_core.model import llm_config as store
from halbert_core.model.client import CHAT_CAPABLE_PROVIDERS, call_llm_chat
from halbert_core.model.providers import PeerProvider
from halbert_core.model.providers.base import GenerationError, ModelNotFoundError
from halbert_core.model.providers.peer import (
    COMPUTE_CHAT_PATH,
    COMPUTE_MODELS_PATH,
    PEER_GOVERNED_MODEL,
)
from halbert_core.model.tier_router import ProviderType, TierRouter
from halbert_core.model.capabilities import ModelDefinition

PEER_URL = "peer://desktop.lan:8000"
HTTP_URL = "http://desktop.lan:8000"


def _response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Registration (W14) — a peer:// slot must resolve, not be disabled
# ---------------------------------------------------------------------------

class TestPeerRegistration:

    def test_peer_is_chat_capable(self):
        assert "peer" in CHAT_CAPABLE_PROVIDERS

    def test_peer_is_a_tier_router_provider_type(self):
        assert ProviderType.PEER == "peer"

    def test_peer_provider_is_exported(self):
        import halbert_core.model.providers as pkg
        assert pkg.PeerProvider is PeerProvider
        assert "PeerProvider" in pkg.__all__

    def test_peer_slot_survives_normalise(self, models_config_dir):
        """The slot-disable path (llm_config.normalise's 'not chat-capable'
        warning) no longer fires for a peer provider."""
        store.save({
            "saved_endpoints": [
                {"id": "e1", "name": "Desktop", "provider": "peer", "url": PEER_URL},
            ],
            "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "auto"},
            "specialist_model": {"enabled": True, "endpoint_id": "e1", "model": "auto"},
        })
        cfg = store.load()
        assert cfg["chat_model"]["enabled"] is True
        assert cfg["specialist_model"]["enabled"] is True

    def test_peer_slot_resolves_with_provider_peer(self, models_config_dir):
        store.save({
            "saved_endpoints": [
                {"id": "e1", "name": "Desktop", "provider": "peer", "url": PEER_URL},
            ],
            "chat_model": {"enabled": True, "endpoint_id": "e1", "model": "auto"},
        })
        resolved = store.resolve("chat_model")
        assert resolved is not None
        assert resolved.url == PEER_URL
        assert resolved.provider == "peer"

    def test_set_slot_accepts_peer_endpoint(self, models_config_dir):
        """set_slot raises SlotProviderError for non-chat-capable providers;
        the peer endpoint must not trip it."""
        endpoint_id = store.ensure_endpoint(PEER_URL, provider="peer", name="Desktop")
        store.set_slot("chat_model", "auto", endpoint_id)
        assert store.load()["chat_model"]["enabled"] is True

    def test_secure_model_still_rejects_peer(self, models_config_dir):
        """The peer registration must not weaken the secure_model local-only
        rule (M11): a peer endpoint in secure_model is disabled on load."""
        store.save({
            "saved_endpoints": [
                {"id": "e1", "name": "Desktop", "provider": "peer", "url": PEER_URL},
            ],
            "secure_model": {"enabled": True, "endpoint_id": "e1", "model": "auto"},
        })
        assert store.load()["secure_model"]["enabled"] is False

    def test_tier_router_builds_a_peer_provider(self, models_config_dir):
        store.save({
            "saved_endpoints": [
                {"id": "e1", "name": "Desktop", "provider": "peer",
                 "url": PEER_URL, "api_key": "tok-1"},
            ],
        })
        router = TierRouter.__new__(TierRouter)
        router._providers = {}
        model = ModelDefinition(
            name="guide-model", model_id="auto", provider="peer", endpoint=PEER_URL,
        )
        provider = router._get_provider(model)
        assert isinstance(provider, PeerProvider)
        # peer:// resolved to http://, and the bearer token came from the
        # saved endpoint's api_key.
        assert provider._endpoint == HTTP_URL
        assert provider._peer_token == "tok-1"


# ---------------------------------------------------------------------------
# Transport — the OpenAI-compatible compute contract (C3)
# ---------------------------------------------------------------------------

def _provider():
    return PeerProvider(endpoint=PEER_URL, peer_token="tok-1", peer_node_id="desktop")


class TestPeerTransport:

    def test_list_models_parses_openai_list(self):
        provider = _provider()
        payload = {"object": "list", "data": [
            {"id": "m-a", "owned_by": "ollama"},
            {"id": "", "owned_by": "ollama"},   # no id → skipped, not invented
        ]}
        with patch("halbert_core.model.providers.peer.requests.get",
                   return_value=_response(payload)) as get:
            models = provider.list_models()
        get.assert_called_once()
        assert get.call_args.args[0] == HTTP_URL + COMPUTE_MODELS_PATH
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tok-1"
        assert [m.model_id for m in models] == ["m-a"]
        assert models[0].provider == "peer"

    def test_list_models_returns_the_stub_empty_list(self):
        """The workstation's models route is still an empty stub
        (TODO(federation-9.3)); the provider must return that empty list,
        never fabricate models."""
        provider = _provider()
        with patch("halbert_core.model.providers.peer.requests.get",
                   return_value=_response({"object": "list", "data": []})):
            assert provider.list_models() == []

    def test_list_models_wraps_transport_errors(self):
        provider = _provider()
        with patch("halbert_core.model.providers.peer.requests.get",
                   side_effect=requests.ConnectionError("down")):
            with pytest.raises(GenerationError):
                provider.list_models()

    def test_health_check_probes_the_models_route(self):
        provider = _provider()
        with patch("halbert_core.model.providers.peer.requests.get",
                   return_value=_response({"object": "list", "data": []})) as get:
            assert provider.health_check() is True
        assert get.call_args.args[0] == HTTP_URL + COMPUTE_MODELS_PATH
        assert get.call_args.kwargs["timeout"] == 1.5

    def test_health_check_false_when_peer_is_down(self):
        with patch("halbert_core.model.providers.peer.requests.get",
                   side_effect=ConnectionError("down")):
            assert _provider().health_check() is False

    def test_generate_posts_to_compute_chat_completions(self):
        provider = _provider()
        payload = {
            "choices": [{"message": {"role": "assistant", "content": " hi "}}],
            "usage": {"total_tokens": 42},
        }
        with patch("halbert_core.model.providers.peer.requests.post",
                   return_value=_response(payload)) as post:
            out = provider.generate("hello", model_id="m-a")
        assert post.call_args.args[0] == HTTP_URL + COMPUTE_CHAT_PATH
        body = post.call_args.kwargs["json"]
        assert body["model"] == "m-a"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["stream"] is False
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok-1"
        assert out.text == "hi"
        assert out.provider == "peer"
        assert out.tokens_used == 42

    def test_generate_maps_revoked_token_to_generation_error(self):
        provider = _provider()
        with patch("halbert_core.model.providers.peer.requests.post",
                   return_value=_response({}, status=401)):
            with pytest.raises(GenerationError) as exc:
                provider.generate("hello", model_id="m-a")
        assert exc.value.status_code == 401

    def test_generate_maps_broker_full_to_generation_error(self):
        provider = _provider()
        with patch("halbert_core.model.providers.peer.requests.post",
                   return_value=_response({}, status=503)):
            with pytest.raises(GenerationError) as exc:
                provider.generate("hello", model_id="m-a")
        assert exc.value.status_code == 503

    def test_is_loaded_asks_the_peer_model_list(self):
        provider = _provider()
        with patch.object(provider, "list_models",
                          return_value=[MagicMock(model_id="m-a")]) as listing:
            assert provider.is_loaded("m-a") is True
            assert provider.is_loaded("m-z") is False
        listing.assert_called()

    def test_is_loaded_governs_the_auto_tag(self):
        """PEER_GOVERNED_MODEL is resolved by the workstation, so it is
        servable even while the workstation's model list is an empty stub."""
        assert _provider().is_loaded(PEER_GOVERNED_MODEL) is True

    def test_get_model_info_raises_for_unknown_model(self):
        provider = _provider()
        with patch.object(provider, "list_models", return_value=[]):
            with pytest.raises(ModelNotFoundError):
                provider.get_model_info("m-z")


# ---------------------------------------------------------------------------
# Chat path — call_llm_chat dispatches peer:// to the compute contract
# ---------------------------------------------------------------------------

class TestPeerChatAdapter:

    def test_posts_to_compute_chat_completions(self, monkeypatch):
        monkeypatch.setattr(store, "load", lambda: store.default_llm_config())
        payload = {"choices": [{"message": {
            "content": "ok",
            "tool_calls": [{"function": {"name": "search_knowledge", "arguments": "{}"}}],
        }}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            out = call_llm_chat(
                endpoint=PEER_URL, model="auto",
                messages=[{"role": "user", "content": "hi"}],
                provider="peer", api_key="tok-1",
            )
        assert post.call_args.args[0] == HTTP_URL + COMPUTE_CHAT_PATH
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok-1"
        assert out["content"] == "ok"
        assert out["tool_calls"] == [
            {"id": "call_0", "name": "search_knowledge", "arguments": {}},
        ]

    def test_token_is_recovered_from_the_saved_endpoint(self, models_config_dir):
        """A caller that passes only the URL still authenticates — the
        pairing flow stored the peer token as the endpoint's api_key."""
        store.save({
            "saved_endpoints": [
                {"id": "e1", "name": "Desktop", "provider": "peer",
                 "url": PEER_URL, "api_key": "tok-1"},
            ],
        })
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response({"choices": [{"message": {"content": "ok"}}]})) as post:
            call_llm_chat(
                endpoint=PEER_URL, model="auto",
                messages=[{"role": "user", "content": "hi"}],
                provider="peer",
            )
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tok-1"

    def test_streaming_is_rejected_until_the_peer_supports_it(self, monkeypatch):
        """The workstation side has no SSE path yet (TODO(federation-9.4));
        a streaming request must fail loudly, not return a full body to a
        caller expecting chunks."""
        monkeypatch.setattr(store, "load", lambda: store.default_llm_config())
        with patch("halbert_core.model.client.requests.post") as post:
            with pytest.raises(NotImplementedError, match="federation-9.4"):
                call_llm_chat(
                    endpoint=PEER_URL, model="auto",
                    messages=[{"role": "user", "content": "hi"}],
                    provider="peer", stream=True,
                )
        post.assert_not_called()

    def test_peer_takes_no_gpu_lock(self, monkeypatch):
        """The peer is a remote GPU — the advisory lock protects the local
        one, so a peer call must not contend for it."""
        monkeypatch.setattr(store, "load", lambda: store.default_llm_config())
        with patch("halbert_core.model.client.llm_advisory_lock") as lock:
            with patch("halbert_core.model.client.requests.post",
                       return_value=_response({"choices": [{"message": {"content": "ok"}}]})):
                call_llm_chat(
                    endpoint=PEER_URL, model="auto",
                    messages=[{"role": "user", "content": "hi"}],
                    provider="peer", api_key="tok-1",
                )
        lock.assert_not_called()