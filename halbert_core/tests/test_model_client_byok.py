# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""BYOK authentication on the chat path (E-1).

Every one of these covers a way a saved endpoint used to test green in
Settings and then fail in chat: a dropped api_key, a missing Authorization
header, an Anthropic request posted to Ollama's /api/chat, or a doubled /v1.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from halbert_core.model.client import (
    CHAT_CAPABLE_PROVIDERS,
    LOCAL_GPU_PROVIDERS,
    OPENAI_COMPATIBLE_PROVIDERS,
    UnsupportedProviderError,
    api_key_for,
    call_llm_chat,
)
from halbert_core.model import llm_config as store

ENDPOINT_ID = "ep_test"
TOOL_SCHEMAS = [{
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Run a shell command",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
}]


def _response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _ollama_ok():
    return _response({"message": {"content": "ok"}})


@pytest.fixture
def no_saved_keys(monkeypatch):
    """models.yml holds no endpoints, so api_key_for() finds nothing."""
    monkeypatch.setattr(store, "load", lambda: store.default_llm_config())


@pytest.fixture
def saved_config(monkeypatch):
    """Install a models.yml with endpoints populated (store-backed)."""
    def _install(config):
        llm_cfg = config.get("llm_config", config)
        monkeypatch.setattr(store, "load", lambda: llm_cfg)
    return _install


# -----------------------------------------------------------------------------
# resolve_endpoint_by_id no longer drops the key (delegates to the store)
# -----------------------------------------------------------------------------

class TestResolveEndpoint:

    def test_returns_api_key_alongside_url_and_provider(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [{
            "id": ENDPOINT_ID,
            "url": "https://api.example.test",
            "provider": "openai",
            "api_key": "sk-secret",
        }]}})
        assert store.resolve_endpoint_by_id(ENDPOINT_ID) == (
            "https://api.example.test", "openai", "sk-secret",
        )

    def test_endpoint_without_key_yields_empty_string_not_none(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"id": ENDPOINT_ID, "url": "http://localhost:11434", "provider": "ollama"}
        ]}})
        assert store.resolve_endpoint_by_id(ENDPOINT_ID)[2] == ""

    def test_unknown_id_returns_none(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": []}})
        assert store.resolve_endpoint_by_id("nope") is None

    def test_no_id_returns_none(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": []}})
        assert store.resolve_endpoint_by_id("") is None


# -----------------------------------------------------------------------------
# api_key_for: the lookup that keeps 30+ existing call sites working
# -----------------------------------------------------------------------------

class TestApiKeyFor:

    def test_finds_key_in_llm_config_endpoints(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": "sk-unified"}
        ]}})
        assert api_key_for("https://api.example.test") == "sk-unified"

    def test_finds_key_in_legacy_top_level_endpoints(self, saved_config):
        saved_config({"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": "sk-legacy"}
        ]})
        assert api_key_for("https://api.example.test") == "sk-legacy"

    def test_unified_list_wins_over_legacy(self, saved_config):
        saved_config({
            "llm_config": {"saved_endpoints": [
                {"url": "https://api.example.test", "api_key": "sk-unified"}
            ]},
            "saved_endpoints": [
                {"url": "https://api.example.test", "api_key": "sk-legacy"}
            ],
        })
        assert api_key_for("https://api.example.test") == "sk-unified"

    def test_empty_key_in_single_list_returns_empty(self, saved_config):
        """After migration there is one list; an empty key means no key found.
        The migration back-fills empty keys from legacy entries, so this
        scenario only arises from a hand-edited file."""
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": ""}
        ]}})
        assert api_key_for("https://api.example.test") == ""

    @pytest.mark.parametrize("stored,looked_up", [
        ("https://api.example.test/", "https://api.example.test"),
        ("https://api.example.test", "https://api.example.test/"),
        ("https://API.Example.Test", "https://api.example.test"),
        ("https://api.example.test//", "https://api.example.test"),
    ])
    def test_url_matching_ignores_case_and_trailing_slash(
        self, saved_config, stored, looked_up
    ):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": stored, "api_key": "sk-match"}
        ]}})
        assert api_key_for(looked_up) == "sk-match"

    def test_unknown_url_returns_empty_string(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": "sk-x"}
        ]}})
        assert api_key_for("https://other.test") == ""

    def test_empty_url_returns_empty_string(self, no_saved_keys):
        assert api_key_for("") == ""

    def test_malformed_endpoint_entries_are_skipped(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            "not-a-dict",
            None,
            {"url": "https://api.example.test", "api_key": "sk-ok"},
        ]}})
        assert api_key_for("https://api.example.test") == "sk-ok"


# -----------------------------------------------------------------------------
# OpenAI-compatible providers: the missing Authorization header
# -----------------------------------------------------------------------------

class TestOpenAICompatibleAuth:

    @pytest.mark.parametrize("provider", sorted(OPENAI_COMPATIBLE_PROVIDERS))
    def test_bearer_header_is_sent(self, provider, no_saved_keys):
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider=provider,
                api_key="sk-secret",
            )
        headers = post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer sk-secret"

    @pytest.mark.parametrize("provider", sorted(OPENAI_COMPATIBLE_PROVIDERS))
    def test_posts_to_chat_completions_not_ollama_chat(self, provider, no_saved_keys):
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider=provider,
                api_key="sk",
            )
        url = post.call_args.args[0]
        assert url == "https://api.example.test/v1/chat/completions"
        assert "/api/chat" not in url

    def test_v1_suffix_is_not_doubled(self, no_saved_keys):
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test/v1",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
                api_key="sk",
            )
        assert post.call_args.args[0] == "https://api.example.test/v1/chat/completions"

    def test_trailing_slash_does_not_double_up(self, no_saved_keys):
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test/",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
                api_key="sk",
            )
        assert post.call_args.args[0] == "https://api.example.test/v1/chat/completions"

    def test_no_key_sends_no_authorization_header(self, no_saved_keys):
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
            )
        assert "Authorization" not in post.call_args.kwargs["headers"]

    def test_key_is_looked_up_when_caller_passes_only_a_url(self, saved_config):
        """The regression that mattered: get_specialist_model() hands back a
        URL, never a key."""
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": "sk-from-config"}
        ]}})
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
            )
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-from-config"

    def test_explicit_empty_key_forces_an_unauthenticated_call(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "api_key": "sk-from-config"}
        ]}})
        payload = {"choices": [{"message": {"content": "hi"}}]}
        with patch("halbert_core.model.client.requests.post",
                   return_value=_response(payload)) as post:
            call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
                api_key="",
            )
        assert "Authorization" not in post.call_args.kwargs["headers"]


# -----------------------------------------------------------------------------
# Anthropic: previously posted to {endpoint}/api/chat and 404'd
# -----------------------------------------------------------------------------

class TestAnthropic:

    def _anthropic_ok(self, blocks=None):
        return _response({
            "content": blocks if blocks is not None else [
                {"type": "text", "text": "hello"}
            ],
            "stop_reason": "end_turn",
        })

    def test_posts_to_v1_messages(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"

    def test_sends_x_api_key_and_version_headers(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                api_key="sk-ant",
            )
        headers = post.call_args.kwargs["headers"]
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers

    def test_system_message_is_hoisted_out_of_messages(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[
                    {"role": "system", "content": "be terse"},
                    {"role": "user", "content": "hi"},
                ],
                provider="anthropic",
                api_key="sk-ant",
            )
        sent = post.call_args.kwargs["json"]
        assert sent["system"] == "be terse"
        assert [m["role"] for m in sent["messages"]] == ["user"]

    def test_multiple_system_messages_are_joined(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[
                    {"role": "system", "content": "be terse"},
                    {"role": "system", "content": "be kind"},
                    {"role": "user", "content": "hi"},
                ],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert post.call_args.kwargs["json"]["system"] == "be terse\n\nbe kind"

    def test_max_tokens_is_always_present(self, no_saved_keys):
        """The Messages API 400s without it, unlike OpenAI's."""
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert post.call_args.kwargs["json"]["max_tokens"] > 0

    def test_empty_content_messages_are_dropped(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": ""},
                ],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert len(post.call_args.kwargs["json"]["messages"]) == 1

    def test_tools_are_converted_to_input_schema(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                tools=TOOL_SCHEMAS,
                api_key="sk-ant",
            )
        sent_tools = post.call_args.kwargs["json"]["tools"]
        assert sent_tools == [{
            "name": "run_command",
            "description": "Run a shell command",
            "input_schema": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
            },
        }]

    def test_tool_use_blocks_normalise_to_the_shared_shape(self, no_saved_keys):
        blocks = [
            {"type": "text", "text": "let me check"},
            {"type": "tool_use", "id": "toolu_1", "name": "run_command",
             "input": {"command": "uptime"}},
        ]
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok(blocks)):
            result = call_llm_chat(
                endpoint="https://api.anthropic.com",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert result["content"] == "let me check"
        assert result["tool_calls"] == [
            {"id": "toolu_1", "name": "run_command", "arguments": {"command": "uptime"}}
        ]

    def test_missing_key_raises_a_message_the_ui_can_show(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post") as post:
            with pytest.raises(ValueError, match="Settings"):
                call_llm_chat(
                    endpoint="https://api.anthropic.com",
                    model="m",
                    messages=[{"role": "user", "content": "hi"}],
                    provider="anthropic",
                )
        post.assert_not_called()

    def test_default_endpoint_when_none_saved(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=self._anthropic_ok()) as post:
            call_llm_chat(
                endpoint="",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                api_key="sk-ant",
            )
        assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"


# -----------------------------------------------------------------------------
# Providers with no chat adapter fail loudly instead of 404-ing
# -----------------------------------------------------------------------------

class TestUnsupportedProviders:

    @pytest.mark.parametrize("provider", ["google", "azure-openai", "cohere"])
    def test_rejected_before_any_http_call(self, provider, no_saved_keys):
        with patch("halbert_core.model.client.requests.post") as post:
            with pytest.raises(UnsupportedProviderError) as exc:
                call_llm_chat(
                    endpoint="https://api.example.test",
                    model="m",
                    messages=[{"role": "user", "content": "hi"}],
                    provider=provider,
                )
        post.assert_not_called()
        assert provider in str(exc.value)
        assert exc.value.provider == provider

    def test_every_chat_capable_provider_has_an_adapter(self):
        """Guards against adding a provider to the allowlist without wiring
        a branch for it in _do_llm_call."""
        assert CHAT_CAPABLE_PROVIDERS == (
            OPENAI_COMPATIBLE_PROVIDERS
            | {"ollama", "llamacpp", "mlx", "anthropic", "peer"}
        )


# -----------------------------------------------------------------------------
# Ollama is unchanged, and lm-studio now shares its GPU lock
# -----------------------------------------------------------------------------

class TestOllamaUnchanged:

    def test_still_posts_to_api_chat_with_no_auth(self, no_saved_keys):
        with patch("halbert_core.model.client.requests.post",
                   return_value=_ollama_ok()) as post:
            call_llm_chat(
                endpoint="http://localhost:11434",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert post.call_args.args[0] == "http://localhost:11434/api/chat"
        assert "headers" not in post.call_args.kwargs

    def test_a_key_is_never_leaked_to_a_local_endpoint(self, saved_config):
        """A key saved against localhost must not turn into a header Ollama
        does not expect."""
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "http://localhost:11434", "api_key": "sk-oops"}
        ]}})
        with patch("halbert_core.model.client.requests.post",
                   return_value=_ollama_ok()) as post:
            call_llm_chat(
                endpoint="http://localhost:11434",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
            )
        assert "headers" not in post.call_args.kwargs


class TestAdvisoryLock:

    @pytest.mark.parametrize("provider", ["ollama", "lm-studio", "llamacpp", "mlx"])
    def test_local_providers_take_the_gpu_lock(self, provider, no_saved_keys):
        assert provider in LOCAL_GPU_PROVIDERS
        payload = (
            {"choices": [{"message": {"content": "hi"}}]}
            if provider in OPENAI_COMPATIBLE_PROVIDERS
            else {"message": {"content": "hi"}}
        )
        with patch("halbert_core.model.client.llm_advisory_lock") as lock:
            lock.return_value.__enter__.return_value = True
            with patch("halbert_core.model.client.requests.post",
                       return_value=_response(payload)):
                call_llm_chat(
                    endpoint="http://localhost:1234",
                    model="m",
                    messages=[{"role": "user", "content": "hi"}],
                    provider=provider,
                )
        lock.assert_called_once()

    @pytest.mark.parametrize("provider", ["openai", "anthropic"])
    def test_cloud_providers_skip_the_gpu_lock(self, provider, no_saved_keys):
        assert provider not in LOCAL_GPU_PROVIDERS
        payload = (
            {"content": [{"type": "text", "text": "hi"}]}
            if provider == "anthropic"
            else {"choices": [{"message": {"content": "hi"}}]}
        )
        with patch("halbert_core.model.client.llm_advisory_lock") as lock:
            with patch("halbert_core.model.client.requests.post",
                       return_value=_response(payload)):
                call_llm_chat(
                    endpoint="https://api.example.test",
                    model="m",
                    messages=[{"role": "user", "content": "hi"}],
                    provider=provider,
                    api_key="sk",
                )
        lock.assert_not_called()


class TestToolFallbackStillWorksPerProvider:

    def test_openai_tool_rejection_retries_without_tools_and_keeps_auth(
        self, no_saved_keys
    ):
        err = requests.HTTPError()
        err.response = MagicMock(status_code=400)
        bad = _response({}, status=400)
        bad.raise_for_status.side_effect = err
        good = _response({"choices": [{"message": {"content": "no tools"}}]})

        with patch("halbert_core.model.client.requests.post",
                   side_effect=[bad, good]) as post:
            result = call_llm_chat(
                endpoint="https://api.example.test",
                model="m",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai",
                tools=TOOL_SCHEMAS,
                api_key="sk-secret",
            )

        assert post.call_count == 2
        assert "tools" in post.call_args_list[0].kwargs["json"]
        assert "tools" not in post.call_args_list[1].kwargs["json"]
        # The retry must not silently drop the credential.
        for call in post.call_args_list:
            assert call.kwargs["headers"]["Authorization"] == "Bearer sk-secret"
        assert result["content"] == "no tools"

    def test_a_401_is_not_retried(self, no_saved_keys):
        """A bad key fails the same way without tools; retrying just doubles
        the latency of every misconfigured endpoint."""
        err = requests.HTTPError()
        err.response = MagicMock(status_code=401)
        bad = _response({}, status=401)
        bad.raise_for_status.side_effect = err

        with patch("halbert_core.model.client.requests.post",
                   return_value=bad) as post:
            with pytest.raises(requests.HTTPError):
                call_llm_chat(
                    endpoint="https://api.example.test",
                    model="m",
                    messages=[{"role": "user", "content": "hi"}],
                    provider="openai",
                    tools=TOOL_SCHEMAS,
                    api_key="sk-bad",
                )
        assert post.call_count == 1


# -----------------------------------------------------------------------------
# provider_for: the companion lookup for call sites that know only a URL
# -----------------------------------------------------------------------------

class TestProviderFor:

    def test_returns_the_saved_provider(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "https://api.example.test", "provider": "openai"}
        ]}})
        from halbert_core.model.client import provider_for
        assert provider_for("https://api.example.test") == "openai"

    def test_unknown_url_falls_back_to_ollama(self, saved_config):
        saved_config({})
        from halbert_core.model.client import provider_for
        assert provider_for("https://nowhere.test") == "ollama"

    def test_default_is_overridable(self, saved_config):
        saved_config({})
        from halbert_core.model.client import provider_for
        assert provider_for("https://nowhere.test", default="openai") == "openai"

    def test_url_match_is_case_and_trailing_slash_insensitive(self, saved_config):
        saved_config({"llm_config": {"saved_endpoints": [
            {"url": "http://localhost:1234/", "provider": "lm-studio"}
        ]}})
        from halbert_core.model.client import provider_for
        assert provider_for("http://localhost:1234") == "lm-studio"


# -----------------------------------------------------------------------------
# The vision slot must be able to point at a cloud endpoint
# -----------------------------------------------------------------------------

class TestVisionCarriesProvider:

    def test_unified_slot_returns_model_endpoint_provider(self, monkeypatch):
        resolved = store.ResolvedModel(
            model="vm", url="https://api.example.test", provider="openai", api_key="sk-v"
        )
        monkeypatch.setattr(store, "resolve", lambda slot: resolved if slot == "vision_model" else None)
        from halbert_core.model.client import get_vision_model
        assert get_vision_model() == ("vm", "https://api.example.test", "openai")

    def test_legacy_vision_key_infers_provider_from_the_endpoint(self, models_config_dir):
        """A legacy vision key is migrated by the store; provider comes from the endpoint."""
        import yaml
        (models_config_dir / "models.yml").parent.mkdir(parents=True, exist_ok=True)
        (models_config_dir / "models.yml").write_text(yaml.safe_dump({
            "saved_endpoints": [
                {"id": "lms", "url": "http://localhost:1234", "provider": "lm-studio"}
            ],
            "vision": {"model": "vm", "endpoint": "http://localhost:1234"},
        }))
        from halbert_core.model.client import get_vision_model
        assert get_vision_model() == ("vm", "http://localhost:1234", "lm-studio")

    def test_unconfigured_vision_is_none_with_a_usable_default(self, monkeypatch):
        monkeypatch.setattr(store, "resolve", lambda slot: None)
        from halbert_core.model.client import get_vision_model
        model, endpoint, provider = get_vision_model()
        assert model is None
        assert endpoint == "http://localhost:11434"
        assert provider == "ollama"
