# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Plan A / A9d: a model that rejects tool schemas is remembered once per
process; the clients expose tools_supported=False so the prompt layer can
drop the tool instruction from the continuity preamble (spec §7).

The memory is per model and is evidence, not a latch: it is written only
after the no-tools retry has answered (a 4xx has other causes — an unpulled
model 404s), it is cleared again once the model accepts schemas, and one
model's rejection never speaks for another model the same client routes to.
"""

import logging
from types import SimpleNamespace

import aiohttp
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

    def test_a_failing_no_tools_retry_records_nothing(self, caplog):
        """A 404 for an unpulled model must not be remembered as "cannot call
        tools": only a retry that answers without the schemas proves that."""
        caplog.set_level(logging.WARNING, logger="halbert.model.client")
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_rejecting(404), _rejecting(404)]):
            with pytest.raises(requests.HTTPError):
                call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is None
        assert not [r for r in caplog.records if "rejected tool schemas" in r.getMessage()]
        # once the model is pulled, the same call works and stays unknown
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_ok({"message": {"content": "a"}})]):
            call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is None

    def test_an_accepted_tools_call_clears_an_earlier_rejection(self):
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_rejecting(400), _ok({"message": {"content": "a"}})]):
            call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is False
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_ok({"message": {"content": "b"}})]):
            call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        assert model_supports_tools("m:7b") is None

    def test_a_call_without_tools_leaves_the_registry_alone(self):
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_rejecting(400), _ok({"message": {"content": "a"}})]):
            call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS, tools=TOOLS)
        with patch("halbert_core.model.client.requests.post",
                   side_effect=[_ok({"message": {"content": "b"}})]):
            call_llm_chat(endpoint="http://localhost:11434", model="m:7b", messages=MSGS)
        assert model_supports_tools("m:7b") is False


# --- OllamaClient (aiohttp) --------------------------------------------------

_REQUEST_INFO = SimpleNamespace(real_url="http://localhost:11434/api/chat")


class _Resp:
    def __init__(self, status, payload):
        self.status, self._payload = status, payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        # aiohttp's own error type, so a failing retry reaches OllamaClient's
        # `except aiohttp.ClientError` the way it does against a real server.
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                _REQUEST_INFO, (), status=self.status, message=f"HTTP {self.status}"
            )

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


@pytest.fixture
def ollama_client(monkeypatch):
    from halbert_core.agents.llm_client import OllamaClient
    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    _Session.posted.clear()
    _Session.responses.clear()
    return OllamaClient(model="m:7b")


@pytest.mark.asyncio
async def test_ollama_client_retries_without_tools_and_sets_the_flag(ollama_client):
    client = ollama_client
    _Session.responses[:] = [_Resp(400, {}), _Resp(200, {"message": {"content": "plain"}})]
    assert client.tools_supported is None
    out = await client.chat(MSGS, tools=TOOLS)
    assert out.content == "plain" and client.tools_supported is False
    assert "tools" in _Session.posted[0] and "tools" not in _Session.posted[1]
    # a plain call afterwards does not reset the flag
    _Session.responses[:] = [_Resp(200, {"message": {"content": "again"}})]
    assert (await client.chat(MSGS)).content == "again"
    assert client.tools_supported is False


@pytest.mark.asyncio
async def test_ollama_client_logs_the_fallback_once_per_model(ollama_client, caplog):
    caplog.set_level(logging.WARNING, logger="halbert.agents.llm_client")
    client = ollama_client
    _Session.responses[:] = [
        _Resp(400, {}), _Resp(200, {"message": {"content": "one"}}),
        _Resp(400, {}), _Resp(200, {"message": {"content": "two"}}),
    ]
    assert (await client.chat(MSGS, tools=TOOLS)).content == "one"
    assert (await client.chat(MSGS, tools=TOOLS)).content == "two"
    assert client.tools_supported is False
    warnings = [r for r in caplog.records if "rejected tool schemas" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_ollama_client_records_nothing_when_the_retry_fails_too(ollama_client, caplog):
    """404 is also how Ollama answers for a model that is not pulled: the
    turn fails, and the client must not remember it as tool-blind."""
    caplog.set_level(logging.WARNING, logger="halbert.agents.llm_client")
    client = ollama_client
    _Session.responses[:] = [_Resp(404, {}), _Resp(404, {})]
    with pytest.raises(aiohttp.ClientResponseError):
        await client.chat(MSGS, tools=TOOLS)
    assert client.tools_supported is None
    assert not [r for r in caplog.records if "rejected tool schemas" in r.getMessage()]


@pytest.mark.asyncio
async def test_ollama_client_forgets_the_rejection_once_the_schemas_are_accepted(ollama_client):
    client = ollama_client
    _Session.responses[:] = [_Resp(400, {}), _Resp(200, {"message": {"content": "plain"}})]
    await client.chat(MSGS, tools=TOOLS)
    assert client.tools_supported is False
    _Session.responses[:] = [_Resp(200, {"message": {"content": "with tools"}})]
    assert (await client.chat(MSGS, tools=TOOLS)).content == "with tools"
    assert client.tools_supported is None


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


@pytest.fixture
def dual_adapter(monkeypatch):
    """An adapter that routes between a guide and a specialist model."""
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "guide:7b")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model",
                        lambda: ("specialist:70b", "http://localhost:11434", "ollama"))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model", lambda: (None, "http://localhost:11434"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_a_specialist_rejection_does_not_speak_for_the_guide_model(dual_adapter):
    """The adapter routes per turn, so one model's rejection must not mute
    the tool instruction for the other one (review: Plan A / A9d)."""
    complex_turn = SimpleNamespace(recommended_model="specialist")
    simple_turn = SimpleNamespace(recommended_model="guide")

    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(400), _ok({"message": {"content": "ok"}})]):
        await dual_adapter.chat(MSGS, tools=TOOLS, intake_result=complex_turn)
    assert model_supports_tools("specialist:70b") is False
    assert model_supports_tools("guide:7b") is None
    # the guide model can still call tools, so the preamble keeps the instruction
    assert dual_adapter.tools_supported is None

    # ... and a later simple turn routed to the guide model still gets it
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_ok({"message": {"content": "ok"}})]):
        await dual_adapter.chat(MSGS, tools=TOOLS, intake_result=simple_turn)
    assert dual_adapter.tools_supported is None

    # only once no configured model can call one does it drop
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(400), _ok({"message": {"content": "ok"}})]):
        await dual_adapter.chat(MSGS, tools=TOOLS, intake_result=simple_turn)
    assert dual_adapter.tools_supported is False


# -----------------------------------------------------------------------------
# The merge seam: P3's per-turn pin meets A9d's per-model memory
# -----------------------------------------------------------------------------


@pytest.fixture
def pinning_adapter(monkeypatch):
    """``dual_adapter`` with a vision slot the pin path can unpack."""
    monkeypatch.setattr("halbert_core.model.client.get_configured_model", lambda: "guide:7b")
    monkeypatch.setattr("halbert_core.model.client.get_ollama_endpoint", lambda: "http://localhost:11434")
    monkeypatch.setattr("halbert_core.model.client.get_specialist_model",
                        lambda: ("specialist:70b", "http://localhost:11434", "ollama"))
    monkeypatch.setattr("halbert_core.model.client.get_vision_model",
                        lambda: (None, "http://localhost:11434", "ollama"))
    from halbert_core.dashboard.routes.agent import LLMClientAdapter
    return LLMClientAdapter()


@pytest.mark.asyncio
async def test_a_pinned_model_that_rejects_tools_still_mutes_the_instruction(pinning_adapter):
    """A pin bypasses routing (P3), so the configured slots cannot answer for it.

    ``tools_supported`` asks about the guide and the specialist. A model
    pinned for one turn is neither, so a pinned model that had rejected tool
    schemas read as "unknown" and the continuity preamble went on telling it
    to call ``recall_thread`` — the one instruction A9d exists to withhold.
    """
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(400), _ok({"message": {"content": "ok"}})]):
        await pinning_adapter.chat(MSGS, tools=TOOLS, model_override="pinned:3b")
    assert model_supports_tools("pinned:3b") is False

    # The configured slots are untouched: an unpinned turn is unaffected.
    assert model_supports_tools("guide:7b") is None
    assert pinning_adapter.tools_supported is None
    assert pinning_adapter.tools_supported_for() is None

    # The turn that pinned it is told the truth, and only that turn.
    assert pinning_adapter.tools_supported_for(model_override="pinned:3b") is False
    assert pinning_adapter.tools_supported_for(model_override="guide:7b") is None


@pytest.mark.asyncio
async def test_a_tier_pin_resolves_the_same_model_the_answer_will_use(pinning_adapter):
    """A specialist tier pin is narrowed too: ``all()`` over guide+specialist
    says "unknown" while the tier the user pinned cannot call anything."""
    with patch("halbert_core.model.client.requests.post",
               side_effect=[_rejecting(400), _ok({"message": {"content": "ok"}})]):
        await pinning_adapter.chat(
            MSGS, tools=TOOLS, intake_result=SimpleNamespace(recommended_model="specialist")
        )
    assert model_supports_tools("specialist:70b") is False
    assert pinning_adapter.tools_supported is None          # the guide can still
    assert pinning_adapter.tools_supported_for(tier_override="specialist") is False
    assert pinning_adapter.tools_supported_for(tier_override="guide") is None


def test_the_state_machine_asks_about_the_turns_own_model():
    """``_continuity_tail`` narrows through the adapter, off ``StateContext``.

    The pin lives on the context (E-2), never on the shared adapter, so the
    state machine is the only place that can put the two together — and a
    client without the hook (every test double, MockLLMClient) still gets the
    plain property.
    """
    from halbert_core.agents.state_machine import AgentStateMachine
    from halbert_core.agents.states import StateContext
    from halbert_core.prompts.agent_prompts import AgentPromptBuilder

    class _Adapter:
        tools_supported = None

        def __init__(self):
            self.asked = []

        def tools_supported_for(self, model_override=None, tier_override=None):
            self.asked.append((model_override, tier_override))
            return False

    llm = _Adapter()
    agent = AgentStateMachine(llm_client=llm, prompt_builder=AgentPromptBuilder())
    agent.ctx = StateContext(
        session_id="s", request_id="r", user_query="carry on",
        continuity_hint="<continuity>\nThread: the samba share\n</continuity>",
        model_override="pinned:3b",
    )
    tail = agent._continuity_tail()
    assert llm.asked == [("pinned:3b", None)]
    assert tail.startswith(AgentPromptBuilder.CONTINUITY_PREAMBLE_NO_TOOLS["first_person"])
    assert "recall_thread" not in tail

    # An unpinned turn never asks, and keeps the full preamble.
    llm.asked.clear()
    agent.ctx.model_override = None
    assert agent._continuity_tail().startswith(
        AgentPromptBuilder.CONTINUITY_PREAMBLE["first_person"]
    )
    assert llm.asked == []

    # A client with no hook at all falls back to the property.
    agent.llm = SimpleNamespace(tools_supported=False)
    agent.ctx.model_override = "pinned:3b"
    assert agent._tools_supported() is False
