# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
D-4 — vision inherits from the chat model.

`model/capabilities.py` already does generic + provider-level + runtime
capability detection; this wires it into `POST /api/llm/proxy/models` so each
`model_details` entry carries `vision` / `tool_use` / `reasoning`. The picker
package already filters `modelsForRole()` on `capabilities.vision` once the
transport forwards these fields — no frontend change is needed for the
filtering itself.

No cloud model-name prefix table is added here (the FRONTEND handoff
suggested one): the repository rule is "never name an AI model in any
string, comment, doc, or UI copy" (STATE handoff, S4; also the founder
directive recorded project-wide), and a table of model-name prefixes would
violate that. Cloud providers get generic token detection plus the existing
provider-level defaults in capabilities.py (e.g. every Anthropic model is
vision-capable); nothing new is hardcoded.
"""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import llm


def _resp(status=200, payload=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.text = text
    return r


class TestOllamaCapabilities:

    def test_runtime_capabilities_list_sets_vision_and_tool_use(self):
        """A model whose name gives no hint (no 'vision'/'vl' token) but whose
        live /api/show reports vision support must still be flagged."""
        def _get(url, **kwargs):
            if url.endswith("/api/tags"):
                return _resp(payload={"models": [{"name": "bakllava:7b"}]})
            raise AssertionError(f"unexpected GET {url}")

        def _post(url, **kwargs):
            if url.endswith("/api/show"):
                return _resp(payload={
                    "capabilities": ["completion", "vision", "tools"],
                    "parameters": "num_ctx 4096",
                })
            raise AssertionError(f"unexpected POST {url}")

        with patch.object(llm.requests, "get", side_effect=_get), \
             patch.object(llm.requests, "post", side_effect=_post):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="ollama", url="http://localhost:11434",
            ))

        detail = out["data"]["model_details"][0]
        assert detail["vision"] is True
        assert detail["tool_use"] is True

    def test_no_runtime_capabilities_falls_back_to_provider_default(self):
        """Older Ollama with no `capabilities` field in /api/show: tool_use
        still defaults True (existing provider-level fact for ollama), vision
        stays False without a name hint or runtime confirmation."""
        def _get(url, **kwargs):
            if url.endswith("/api/tags"):
                return _resp(payload={"models": [{"name": "mistral:7b"}]})
            raise AssertionError

        def _post(url, **kwargs):
            if url.endswith("/api/show"):
                return _resp(payload={"parameters": "num_ctx 4096"})
            raise AssertionError

        with patch.object(llm.requests, "get", side_effect=_get), \
             patch.object(llm.requests, "post", side_effect=_post):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="ollama", url="http://localhost:11434",
            ))

        detail = out["data"]["model_details"][0]
        assert detail["vision"] is False
        assert detail["tool_use"] is True

    def test_name_hint_sets_vision_even_when_show_fails(self):
        """/api/show can fail (offline, timeout) without losing the vision
        hint the model's own name already gives."""
        def _get(url, **kwargs):
            if url.endswith("/api/tags"):
                return _resp(payload={"models": [{"name": "qwen2.5-vl:7b"}]})
            raise AssertionError

        def _post(url, **kwargs):
            if url.endswith("/api/show"):
                raise OSError("timed out")
            raise AssertionError

        with patch.object(llm.requests, "get", side_effect=_get), \
             patch.object(llm.requests, "post", side_effect=_post):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="ollama", url="http://localhost:11434",
            ))

        assert out["data"]["model_details"][0]["vision"] is True


class TestCloudCapabilities:

    def test_anthropic_models_are_vision_and_tool_capable_by_provider_default(self):
        with patch.object(llm.requests, "get",
                           return_value=_resp(payload={"data": [{"id": "m-1"}]})):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="anthropic", url="https://api.anthropic.com",
                api_key="sk-ant",
            ))
        detail = out["data"]["model_details"][0]
        assert detail["vision"] is True
        assert detail["tool_use"] is True

    def test_openai_models_get_tool_use_but_not_vision_without_a_name_hint(self):
        """No hardcoded model-name table: an OpenAI model with no 'vision'
        token in its id is not claimed vision-capable."""
        with patch.object(llm.requests, "get",
                           return_value=_resp(payload={"data": [{"id": "gpt-text-only"}]})):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="openai", url="https://api.openai.test", api_key="sk-o",
            ))
        detail = out["data"]["model_details"][0]
        assert detail["tool_use"] is True
        assert detail["vision"] is False

    def test_openai_model_with_vision_in_its_name_is_flagged(self):
        with patch.object(llm.requests, "get",
                           return_value=_resp(payload={"data": [{"id": "gpt-4-vision-preview"}]})):
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="openai", url="https://api.openai.test", api_key="sk-o",
            ))
        assert out["data"]["model_details"][0]["vision"] is True
