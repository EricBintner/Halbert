# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R05-F1: a turn routed to a peer has to produce an answer.

``_stream_turn`` dispatched OpenAI-compatible, anthropic, or else-Ollama.
``peer`` is in CHAT_CAPABLE_PROVIDERS but not OPENAI_COMPATIBLE_PROVIDERS, so
a peer turn fell to the Ollama arm and posted ``peer://host:8000/api/chat`` —
a scheme aiohttp refuses (NonHttpUrlClientError) at a path the compute
endpoint does not serve. The state machine prefers ``stream()``, so a home
node linked to a workstation failed on every turn.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self):
        return self._body

    async def text(self):
        return json.dumps(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Records the one request the peer path makes."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers or {}})
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _turn():
    """A TurnModel as the router hands one over."""
    return SimpleNamespace(
        model="qwen:7b", endpoint="peer://workstation.lan:8000", provider="peer",
        tier="guide", pinned=False, escalated=False, reason="",
    )


async def _run(client, session, monkeypatch, turn=None):
    import halbert_core.dashboard.routes.agent as agent_mod

    import aiohttp

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **kw: session)
    monkeypatch.setattr("halbert_core.model.client.api_key_for", lambda url: "peer-token")

    chunks = []
    async for chunk in client._answer_from_peer(
        turn or _turn(),
        [{"role": "user", "content": "what is 6 times 7"}],
        max_tokens=512, temperature=0.7,
        on_model_selected=lambda m: None, requested=None,
    ):
        chunks.append(chunk)
    return chunks


@pytest.fixture
def client():
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter.__new__(LLMClientAdapter)


class TestAPeerTurnAnswers:

    @pytest.mark.asyncio
    async def test_the_answer_comes_back(self, client, monkeypatch):
        session = _FakeSession(_FakeResponse(200, {
            "choices": [{"message": {"role": "assistant", "content": "42"}}],
        }))
        assert await _run(client, session, monkeypatch) == ["42"]

    @pytest.mark.asyncio
    async def test_it_goes_to_the_compute_endpoint_over_http(self, client, monkeypatch):
        from halbert_core.federation.compute_endpoint import COMPUTE_CHAT_PATH

        session = _FakeSession(_FakeResponse(200, {
            "choices": [{"message": {"content": "42"}}],
        }))
        await _run(client, session, monkeypatch)

        call = session.calls[0]
        assert call["url"] == f"http://workstation.lan:8000{COMPUTE_CHAT_PATH}"
        assert not call["url"].startswith("peer://"), "aiohttp cannot speak peer://"
        assert call["headers"]["Authorization"] == "Bearer peer-token"
        assert call["json"]["stream"] is False

    @pytest.mark.asyncio
    async def test_an_empty_answer_yields_nothing_rather_than_an_empty_chunk(
        self, client, monkeypatch,
    ):
        session = _FakeSession(_FakeResponse(200, {"choices": []}))
        assert await _run(client, session, monkeypatch) == []

    @pytest.mark.asyncio
    async def test_a_refusing_peer_is_unreachable_not_a_crash(self, client, monkeypatch):
        from halbert_core.dashboard.routes.agent import _ModelUnreachable

        session = _FakeSession(_FakeResponse(503, {"detail": "no model configured"}))
        with pytest.raises(_ModelUnreachable):
            await _run(client, session, monkeypatch)

    @pytest.mark.asyncio
    async def test_the_model_is_reported_only_once_the_response_is_good(
        self, client, monkeypatch,
    ):
        import halbert_core.dashboard.routes.agent as agent_mod

        reported = []
        monkeypatch.setattr(agent_mod, "_report_model",
                            lambda cb, turn, requested: reported.append(turn.model))

        import aiohttp

        session = _FakeSession(_FakeResponse(503, {"detail": "nope"}))
        monkeypatch.setattr(aiohttp, "ClientSession", lambda **kw: session)
        monkeypatch.setattr("halbert_core.model.client.api_key_for", lambda url: "t")

        with pytest.raises(agent_mod._ModelUnreachable):
            async for _ in client._answer_from_peer(
                _turn(), [{"role": "user", "content": "hi"}],
                max_tokens=16, temperature=0.0,
                on_model_selected=lambda m: None, requested=None,
            ):
                pass

        assert reported == [], "a model that never answered was credited"
