# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
GET /api/llm/discover — server-side probing of the standard local ports (E-4).

Served from a browser at localhost:8000, the frontend cannot probe :11434
itself whenever OLLAMA_ORIGINS is restricted. These cover the loopback probe
that replaces it, plus the Anthropic auth shape the neighbouring proxy routes
were getting wrong.
"""

import pytest
from unittest.mock import MagicMock, patch

pytest.importorskip("fastapi")

from halbert_core.dashboard.routes import llm


def _resp(status=200, payload=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.text = ""
    return r


def _routed(url, **kwargs):
    """Dispatch a fake GET by URL suffix so both probes can be driven at once."""
    if url.endswith("/api/version"):
        return _resp(payload={"version": "0.14.2"})
    if url.endswith("/api/tags"):
        return _resp(payload={"models": [{"name": "a:1"}, {"name": "b:2"}]})
    if url.endswith("/v1/models"):
        return _resp(payload={"data": [{"id": "lm-a"}, {"id": "lm-b"}]})
    raise AssertionError(f"unexpected probe URL: {url}")


# -----------------------------------------------------------------------------
# Route registration — the router carries no prefix, so the decorator must
# spell the full path or this lands on /discover.
# -----------------------------------------------------------------------------

class TestRouteRegistration:

    def test_registered_at_the_full_api_path(self):
        paths = {
            r.path for r in llm.router.routes
            if getattr(r, "endpoint", None) is llm.discover_local_engines
        }
        assert paths == {"/api/llm/discover"}

    def test_is_a_get(self):
        route = next(
            r for r in llm.router.routes
            if getattr(r, "endpoint", None) is llm.discover_local_engines
        )
        assert route.methods == {"GET"}


# -----------------------------------------------------------------------------
# Probe behaviour
# -----------------------------------------------------------------------------

class TestOllamaProbe:

    def test_reports_version_and_models_when_running(self):
        with patch.object(llm.requests, "get", side_effect=_routed):
            out = llm._probe_ollama()
        assert out["running"] is True
        assert out["version"] == "0.14.2"
        assert out["models"] == ["a:1", "b:2"]

    def test_not_running_when_the_connection_is_refused(self):
        with patch.object(llm.requests, "get",
                          side_effect=OSError("connection refused")):
            out = llm._probe_ollama()
        assert out == {
            "running": False, "url": llm.OLLAMA_DISCOVERY_URL,
            "version": None, "models": [],
        }

    def test_non_200_is_treated_as_not_running(self):
        with patch.object(llm.requests, "get", return_value=_resp(status=500)):
            assert llm._probe_ollama()["running"] is False

    def test_still_running_when_only_the_tag_listing_fails(self):
        """A daemon that is up but slow to enumerate must not be reported
        offline — that is the worse of the two wrong answers."""
        def _flaky(url, **kwargs):
            if url.endswith("/api/version"):
                return _resp(payload={"version": "0.14.2"})
            raise OSError("timed out")

        with patch.object(llm.requests, "get", side_effect=_flaky):
            out = llm._probe_ollama()
        assert out["running"] is True
        assert out["version"] == "0.14.2"
        assert out["models"] == []

    def test_malformed_model_entries_are_skipped(self):
        def _junk(url, **kwargs):
            if url.endswith("/api/version"):
                return _resp(payload={"version": "x"})
            return _resp(payload={"models": ["bare-string", {}, {"name": "ok:1"}]})

        with patch.object(llm.requests, "get", side_effect=_junk):
            assert llm._probe_ollama()["models"] == ["ok:1"]


class TestLMStudioProbe:

    def test_model_list_doubles_as_the_liveness_check(self):
        with patch.object(llm.requests, "get", side_effect=_routed):
            out = llm._probe_lm_studio()
        assert out["running"] is True
        assert out["models"] == ["lm-a", "lm-b"]

    def test_not_running_when_refused(self):
        with patch.object(llm.requests, "get", side_effect=OSError("refused")):
            out = llm._probe_lm_studio()
        assert out["running"] is False
        assert out["models"] == []

    def test_malformed_entries_are_skipped(self):
        with patch.object(llm.requests, "get",
                          return_value=_resp(payload={"data": [{}, {"id": "ok"}]})):
            assert llm._probe_lm_studio()["models"] == ["ok"]


# -----------------------------------------------------------------------------
# The route itself
# -----------------------------------------------------------------------------

class TestDiscoverRoute:

    def test_returns_both_engines_in_a_data_envelope(self):
        with patch.object(llm.requests, "get", side_effect=_routed):
            out = llm.discover_local_engines()
        assert set(out) == {"data"}
        assert set(out["data"]) == {"ollama", "lm_studio"}
        assert out["data"]["ollama"]["running"] is True
        assert out["data"]["lm_studio"]["running"] is True

    def test_one_dead_engine_does_not_hide_the_other(self):
        def _half(url, **kwargs):
            if ":1234" in url:
                raise OSError("refused")
            return _routed(url, **kwargs)

        with patch.object(llm.requests, "get", side_effect=_half):
            data = llm.discover_local_engines()["data"]
        assert data["ollama"]["running"] is True
        assert data["lm_studio"]["running"] is False

    def test_never_raises_even_on_an_unexpected_error(self):
        with patch.object(llm.requests, "get",
                          side_effect=RuntimeError("something odd")):
            data = llm.discover_local_engines()["data"]
        assert data["ollama"]["running"] is False
        assert data["lm_studio"]["running"] is False

    def test_probes_the_standard_ports(self):
        seen = []

        def _record(url, **kwargs):
            seen.append(url)
            return _routed(url, **kwargs)

        with patch.object(llm.requests, "get", side_effect=_record):
            llm.discover_local_engines()
        assert any(":11434" in u for u in seen)
        assert any(":1234/" in u or u.endswith(":1234/v1/models") for u in seen)

    def test_is_read_only(self):
        """The discover route reports what is running and never writes config."""
        with patch.object(llm.requests, "get", side_effect=_routed), \
             patch.object(llm.llm_store, "save") as save, \
             patch.object(llm.llm_store, "update") as update:
            llm.discover_local_engines()
        save.assert_not_called()
        update.assert_not_called()

    def test_timeout_is_a_tuple_so_it_bounds_connect_and_read_separately(self):
        """requests applies a scalar timeout to both phases, which would make
        the effective worst case double the intended budget."""
        assert isinstance(llm._DISCOVER_TIMEOUT, tuple)
        connect, read = llm._DISCOVER_TIMEOUT
        assert connect <= 0.5
        assert read >= connect

    def test_every_probe_call_passes_the_budget(self):
        calls = []

        def _record(url, **kwargs):
            calls.append(kwargs.get("timeout"))
            return _routed(url, **kwargs)

        with patch.object(llm.requests, "get", side_effect=_record):
            llm.discover_local_engines()
        assert calls
        assert all(t == llm._DISCOVER_TIMEOUT for t in calls)


# -----------------------------------------------------------------------------
# Anthropic auth on the neighbouring proxy routes — Bearer is a guaranteed 401
# -----------------------------------------------------------------------------

class TestCloudAuthHeaders:

    def test_anthropic_uses_x_api_key_and_a_version(self):
        headers = llm._cloud_auth_headers("anthropic", "sk-ant")
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers

    @pytest.mark.parametrize("provider", ["openai", "openai-compatible", "lm-studio"])
    def test_openai_family_uses_bearer(self, provider):
        assert llm._cloud_auth_headers(provider, "sk") == {
            "Authorization": "Bearer sk"
        }

    def test_no_key_means_no_headers(self):
        assert llm._cloud_auth_headers("anthropic", None) == {}
        assert llm._cloud_auth_headers("openai", "") == {}

    @pytest.mark.parametrize("url,expected", [
        ("https://api.anthropic.com", "https://api.anthropic.com/v1"),
        ("https://api.anthropic.com/v1", "https://api.anthropic.com/v1"),
        ("https://api.anthropic.com/v1/", "https://api.anthropic.com/v1"),
        ("http://localhost:1234", "http://localhost:1234/v1"),
    ])
    def test_v1_is_added_once_and_only_once(self, url, expected):
        assert llm._openai_style_base(url) == expected


class TestAnthropicProxyRoutes:

    def test_proxy_models_sends_the_anthropic_headers(self):
        with patch.object(llm.requests, "get",
                          return_value=_resp(payload={"data": [{"id": "m-1"}]})) as get:
            out = llm.proxy_models(llm.LLMProxyRequest(
                provider="anthropic", url="https://api.anthropic.com",
                api_key="sk-ant",
            ))
        headers = get.call_args.kwargs["headers"]
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"] == "2023-06-01"
        assert get.call_args.args[0] == "https://api.anthropic.com/v1/models"
        assert out["data"]["models"] == ["m-1"]

    def test_proxy_test_sends_the_anthropic_headers(self):
        with patch.object(llm.requests, "get",
                          return_value=_resp(payload={"data": [{"id": "m-1"}]})) as get:
            out = llm.proxy_test(llm.LLMProxyRequest(
                provider="anthropic", url="https://api.anthropic.com",
                api_key="sk-ant",
            ))
        assert get.call_args.kwargs["headers"]["x-api-key"] == "sk-ant"
        assert out["data"]["success"] is True

    def test_proxy_test_model_no_longer_falls_through_silently(self):
        """It previously matched no branch and returned success:false with an
        empty message."""
        with patch.object(llm.requests, "post",
                          return_value=_resp(payload={"content": []})) as post:
            out = llm.proxy_test_model(llm.LLMModelTestRequest(
                provider="anthropic", url="https://api.anthropic.com",
                model="m", api_key="sk-ant",
            ))
        assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
        assert post.call_args.kwargs["headers"]["x-api-key"] == "sk-ant"
        assert post.call_args.kwargs["json"]["max_tokens"] == 5
        assert out["data"]["success"] is True
        assert out["data"]["model_status"] == "ready"

    def test_proxy_test_model_reports_a_bad_key(self):
        bad = _resp(status=401)
        bad.text = "invalid x-api-key"
        with patch.object(llm.requests, "post", return_value=bad):
            out = llm.proxy_test_model(llm.LLMModelTestRequest(
                provider="anthropic", url="https://api.anthropic.com",
                model="m", api_key="sk-bad",
            ))
        assert out["data"]["success"] is False
        assert "401" in out["data"]["message"]

    def test_openai_still_gets_bearer(self):
        with patch.object(llm.requests, "get",
                          return_value=_resp(payload={"data": [{"id": "gpt"}]})) as get:
            llm.proxy_models(llm.LLMProxyRequest(
                provider="openai", url="https://api.openai.test", api_key="sk-o",
            ))
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-o"
