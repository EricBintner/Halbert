# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9d: a model that rejects tool schemas is remembered once per
process; the clients expose tools_supported=False so the prompt layer can
drop the tool instruction from the continuity preamble (spec §7)."""

import logging
import pytest
import requests
from unittest.mock import MagicMock, patch

import halbert_core.model.client as mc
from halbert_core.model.client import call_llm_chat, model_supports_tools

TOOLS = [{"type": "function", "function": {"name": "t", "parameters": {"type": "object", "properties": {}}}}]
MSGS = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def _clear_registry():
    mc._TOOLS_REJECTED.clear()
    yield
    mc._TOOLS_REJECTED.clear()


def _ok(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _rejecting(status):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}", response=resp)
    return resp


class TestRegistry:
    def test_unknown_until_a_rejection(self):
        assert model_supports_tools("m:7b") is None

    def test_rejection_marks_model_retries_without_tools_and_logs_once(self, caplog):
        caplog.set_level(logging.WARNING, logger="halbert.model.client")
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_rejecting(400), _ok({"message": {"content": "a"}}),
                                _rejecting(400), _ok({"message": {"content": "b"}})]) as post:
            first = call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
            second = call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert first["content"] == "a" and second["content"] == "b"
        assert model_supports_tools("m:7b") is False
        assert model_supports_tools("other") is None
        payloads = [c.kwargs["json"] for c in post.call_args_list]
        assert "tools" in payloads[0] and "tools" not in payloads[1]
        assert "tools" in payloads[2] and "tools" not in payloads[3]
        warnings = [r for r in caplog.records if "rejected tool schemas" in r.getMessage()]
        assert len(warnings) == 1

    def test_other_http_errors_still_raise(self):
        with patch("halbert_core.model.client.requests.post", side_effect=[_rejecting(500)]):
            with pytest.raises(requests.HTTPError):
                call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is None


# --- OllamaClient (aiohttp) --------------------------------------------------

class _Resp:
    def __init__(self, status, payload):
        self.status, self._payload = status, payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self._payload


class _Session:
    posted = []
    responses = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, url, json=None, **k):
        # Snapshot the body the way a real session serialises it at post
        # time: the retry reuses (and mutates) the same payload dict.
        _Session.posted.append(dict(json) if json is not None else json)
        return _Session.responses.pop(0)


@pytest.mark.asyncio
async def test_ollama_client_retries_without_tools_and_sets_the_flag(monkeypatch):
    from halbert_core.agents.llm_client import OllamaClient
    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    _Session.posted.clear()
    _Session.responses[:] = [_Resp(400, {}), _Resp(200, {"message": {"content": "plain"}})]
    client = OllamaClient(model="m:7b")
    assert client.tools_supported is None
    out = await client.chat(MSGS, tools=TOOLS)
    assert out.content == "plain" and client.tools_supported is False
    assert "tools" in _Session.posted[0] and "tools" not in _Session.posted[1]
    # a plain call afterwards does not reset the flag
    _Session.responses[:] = [_Resp(200, {"message": {"content": "again"}})]
    assert (await client.chat(MSGS)).content == "again"
    assert client.tools_supported is False


# --- LLMClientAdapter (dashboard) -------------------------------------------

fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "m:7b")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model", lambda: (None, None, None))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model", lambda: (None, "http://localhost:11434"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_adapter_learns_tools_supported_from_the_fallback(adapter):
    assert adapter.tools_supported is None
    with patch("halbert_core.model.client.requests.post", side_effect=[_ok({"message": {"content": "ok"}})]):
        await adapter.chat(MSGS, tools=TOOLS)
    assert adapter.tools_supported is None          # accepted: still unknown
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(422), _ok({"message": {"content": "ok"}})]):
        r = await adapter.chat(MSGS, tools=TOOLS)
    assert r.content == "ok" and adapter.tools_supported is False
    # a later call without tools does not flip it back
    with patch("halbert_core.model.client.requests.post", side_effect=[_ok({"message": {"content": "ok"}})]):
        await adapter.chat(MSGS, tools=None)
    assert adapter.tools_supported is False
