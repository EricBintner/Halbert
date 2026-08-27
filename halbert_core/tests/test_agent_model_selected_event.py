# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
The ``model_selected`` stream event (D-3, backend half).

``_resolve_turn_model`` already knew which model answered and why — pinned,
escalated, or quietly swapped for the guide because the pin was unreachable —
and none of it reached the frontend. These cover the transport: the factory's
shape, the adapter reporting what it actually used through a per-call callback
(never state on the process-wide shared adapter), and RESPONDING announcing it
exactly once, ahead of the first chunk.

The streaming path carries the graceful fallback too (D-2.1). While it lived
only in chat(), a pinned model on a dead port put the connection error in the
assistant's bubble, and ``fallback_from`` — the amber "was unavailable" chip —
could not be set on any turn the user actually read.
"""

import json

import pytest
from unittest.mock import patch

pytest.importorskip("fastapi")
aiohttp = pytest.importorskip("aiohttp")

from halbert_core.agents.events import StreamEvent
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.dashboard.routes import agent as agent_routes

GUIDE = ("guide-model", "http://localhost:11434", "ollama")
SPECIALIST = ("specialist-model", "https://api.cloud.test", "openai")
VISION = ("vision-model", "http://localhost:11434", "ollama")

TRIVIAL = "hi"
# Long, multi-clause, keyword-heavy: scores above the 0.5 legacy threshold.
COMPLEX = (
    "diagnose why the nginx service failed to restart after the certificate "
    "renewal hook ran, then analyse the systemd journal and explain the root "
    "cause step by step and recommend how to troubleshoot and optimize it"
)


@pytest.fixture
def slots(monkeypatch):
    """Install the three configured slots; returns a mutator for each."""
    state = {"guide": GUIDE, "specialist": SPECIALIST, "vision": VISION,
             "endpoints": {}}
    import halbert_core.model.client as client

    monkeypatch.setattr(client, "get_configured_model",
                        lambda: state["guide"][0] if state["guide"] else "")
    monkeypatch.setattr(client, "get_ollama_endpoint",
                        lambda: state["guide"][1] if state["guide"] else "http://localhost:11434")
    monkeypatch.setattr(client, "get_specialist_model",
                        lambda: state["specialist"] or (None, None, None))
    monkeypatch.setattr(client, "get_vision_model",
                        lambda: state["vision"] or (None, "http://localhost:11434", "ollama"))
    monkeypatch.setattr(client, "provider_for",
                        lambda url, default="ollama":
                            state["guide"][2] if state["guide"] and url == state["guide"][1] else default)
    monkeypatch.setattr(client, "resolve_endpoint_by_id",
                        lambda eid: state["endpoints"].get(eid))
    monkeypatch.setattr(client, "api_key_for", lambda url: "")
    return state


ANSWER = "The answer is forty-two, and here is why."


def _ollama_lines(text):
    yield json.dumps({"message": {"content": text}}).encode()
    yield json.dumps({"done": True}).encode()


def _openai_lines(text):
    body = {"choices": [{"delta": {"content": text}}]}
    yield f"data: {json.dumps(body)}".encode()
    yield b"data: [DONE]"


class _Body:
    """A response body; ``drops_after`` cuts the wire that many lines in."""

    def __init__(self, lines, drops_after=None):
        self._lines = list(lines)
        self._drops_after = drops_after

    def __aiter__(self):
        return self._read()

    async def _read(self):
        for i, line in enumerate(self._lines):
            if self._drops_after is not None and i >= self._drops_after:
                raise ConnectionResetError("the runtime dropped the connection")
            yield line


class _Response:
    def __init__(self, status, body, text=""):
        self.status = status
        self.content = body
        self._text = text

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Refusal:
    """A request whose connection never opens."""

    def __init__(self, model):
        self._model = model

    async def __aenter__(self):
        raise ConnectionError(f"Cannot connect to host serving {self._model}")

    async def __aexit__(self, *exc):
        return False


class _Session:
    """Answers on behalf of whichever model the payload names."""

    def __init__(self, plan):
        self._plan = plan

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        model = (json or {}).get("model")
        self._plan["asked"].append(model)
        failure = self._plan["fails"].get(model)
        if failure == "refused":
            return _Refusal(model)
        if failure == "rejected":
            return _Response(503, _Body([]), text="that model is not loaded")
        lines = _ollama_lines if url.endswith("/api/chat") else _openai_lines
        return _Response(200, _Body(
            lines(self._plan["answer"]),
            drops_after=1 if failure == "drops" else None,
        ))


@pytest.fixture
def runtime(monkeypatch):
    """A scripted runtime under ``stream()``, recording who was asked.

    Nothing here touches the network: a test that reached a real runtime on
    the developer's machine would prove nothing about either. Name a model in
    ``fails`` to make it refuse the connection, reject the request, or drop the
    wire once the answer has started.
    """
    plan = {"answer": ANSWER, "fails": {}, "asked": []}
    monkeypatch.setattr(aiohttp, "ClientSession",
                        lambda *args, **kwargs: _Session(plan))
    return plan


async def _run_stream(**kwargs):
    """Run ``stream()`` to exhaustion, returning its text and its reports."""
    chunks, captured = [], []
    adapter = agent_routes.LLMClientAdapter()
    async for chunk in adapter.stream(
        messages=[{"role": "user", "content": kwargs.pop("prompt")}],
        on_model_selected=captured.append,
        **kwargs,
    ):
        chunks.append(chunk)
    return "".join(chunks), captured


async def _drain_stream(**kwargs):
    """Run ``stream()`` to exhaustion, returning the reported payloads."""
    _text, captured = await _run_stream(**kwargs)
    return captured


# -----------------------------------------------------------------------------
# The factory
# -----------------------------------------------------------------------------

class TestFactory:

    def test_shape(self):
        ev = StreamEvent.model_selected(
            "s1", model="model-a", endpoint="http://localhost:11434",
            provider="ollama", tier="specialist", pinned=False,
            escalated=True, reason="Complexity score 0.80 (threshold 0.50)",
        )
        assert ev.type == "model_selected"
        assert ev.session_id == "s1"
        assert ev.data["model"] == "model-a"
        assert ev.data["endpoint"] == "http://localhost:11434"
        assert ev.data["provider"] == "ollama"
        assert ev.data["tier"] == "specialist"
        assert ev.data["pinned"] is False
        assert ev.data["escalated"] is True
        assert ev.data["reason"].startswith("Complexity score")

    def test_to_dict_flattens_onto_the_envelope(self):
        payload = StreamEvent.model_selected(
            "s1", "model-a", "http://x", "ollama", "guide").to_dict()
        assert payload["type"] == "model_selected"
        assert payload["session_id"] == "s1"
        assert payload["model"] == "model-a"

    def test_serialises_to_sse(self):
        sse = StreamEvent.model_selected(
            "s1", "model-a", "http://x", "ollama", "guide").to_sse()
        assert sse.startswith("data: ")
        assert "model_selected" in sse
        assert sse.endswith("\n\n")

    def test_fallback_from_is_absent_when_nothing_fell_back(self):
        ev = StreamEvent.model_selected(
            "s1", "model-a", "http://x", "ollama", "guide")
        assert "fallback_from" not in ev.data

    def test_fallback_from_is_carried_when_something_did(self):
        ev = StreamEvent.model_selected(
            "s1", "model-a", "http://x", "ollama", "guide",
            fallback_from="model-b")
        assert ev.data["fallback_from"] == "model-b"


# -----------------------------------------------------------------------------
# The adapter reports what it resolved — streaming path
# -----------------------------------------------------------------------------

class TestStreamReports:

    async def test_reports_exactly_once(self, slots, runtime):
        captured = await _drain_stream(prompt=TRIVIAL)
        assert len(captured) == 1

    async def test_a_pinned_turn_is_pinned_and_not_escalated(self, slots, runtime):
        captured = await _drain_stream(prompt=COMPLEX, model_override="pinned-x")
        assert captured[0]["model"] == "pinned-x"
        assert captured[0]["pinned"] is True
        assert captured[0]["escalated"] is False

    async def test_a_tier_pin_is_pinned_and_not_escalated(self, slots, runtime):
        captured = await _drain_stream(prompt=TRIVIAL, tier_override="specialist")
        assert captured[0]["model"] == SPECIALIST[0]
        assert captured[0]["tier"] == "specialist"
        assert captured[0]["pinned"] is True
        assert captured[0]["escalated"] is False

    async def test_an_escalated_turn_reports_the_reason(self, slots, runtime):
        captured = await _drain_stream(prompt=COMPLEX)
        assert captured[0]["model"] == SPECIALIST[0]
        assert captured[0]["escalated"] is True
        assert captured[0]["pinned"] is False
        assert "0.50" in captured[0]["reason"]

    async def test_a_routine_turn_is_neither(self, slots, runtime):
        captured = await _drain_stream(prompt=TRIVIAL)
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["pinned"] is False
        assert captured[0]["escalated"] is False

    async def test_nothing_fell_back(self, slots, runtime):
        captured = await _drain_stream(prompt=TRIVIAL)
        assert "fallback_from" not in captured[0]

    async def test_the_payload_feeds_the_factory_unchanged(self, slots, runtime):
        """The state machine splats the payload straight into the factory, so
        an extra or renamed key here is a TypeError in production."""
        captured = await _drain_stream(prompt=COMPLEX)
        ev = StreamEvent.model_selected("s1", **captured[0])
        assert ev.data["model"] == SPECIALIST[0]

    async def test_a_raising_callback_does_not_cost_the_user_the_answer(
        self, slots, runtime
    ):
        adapter = agent_routes.LLMClientAdapter()
        def _explode(_payload):
            raise ValueError("bookkeeping is not the user's problem")
        chunks = [c async for c in adapter.stream(
            messages=[{"role": "user", "content": TRIVIAL}],
            on_model_selected=_explode,
        )]
        assert "".join(chunks) == ANSWER

    async def test_omitting_the_callback_is_still_supported(self, slots, runtime):
        adapter = agent_routes.LLMClientAdapter()
        chunks = [c async for c in adapter.stream(
            messages=[{"role": "user", "content": TRIVIAL}],
        )]
        assert "".join(chunks) == ANSWER


# -----------------------------------------------------------------------------
# An unreachable model costs the user that model, never the turn — streaming
# -----------------------------------------------------------------------------

class TestStreamFallsBackToTheGuide:
    """stream(), not chat(), produces the text the user reads. While the
    fallback lived only in chat(), a pinned model on a dead port put the
    connection error itself in the assistant's bubble."""

    async def test_a_pinned_offline_model_is_answered_by_the_guide(
        self, slots, runtime
    ):
        runtime["fails"]["pinned-x"] = "refused"
        text, _captured = await _run_stream(prompt=TRIVIAL,
                                            model_override="pinned-x")
        assert text == ANSWER
        assert runtime["asked"] == ["pinned-x", GUIDE[0]]

    async def test_the_report_names_the_model_that_could_not_be_reached(
        self, slots, runtime
    ):
        runtime["fails"]["pinned-x"] = "refused"
        _text, captured = await _run_stream(prompt=TRIVIAL,
                                            model_override="pinned-x")
        assert len(captured) == 1
        assert captured[0]["fallback_from"] == "pinned-x"
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["tier"] == "guide"

    async def test_the_guide_is_not_reported_as_pinned(self, slots, runtime):
        """"Pinned" over a model the user never chose is the exact confusion
        this event exists to remove."""
        runtime["fails"]["pinned-x"] = "refused"
        _text, captured = await _run_stream(prompt=TRIVIAL,
                                            model_override="pinned-x")
        assert captured[0]["pinned"] is False
        assert captured[0]["escalated"] is False

    async def test_a_rejected_request_falls_back_as_well(self, slots, runtime):
        """A configured but unloaded model answers with a status, not a dead
        socket, and strands the turn just the same."""
        runtime["fails"][SPECIALIST[0]] = "rejected"
        text, captured = await _run_stream(prompt=COMPLEX)
        assert text == ANSWER
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["fallback_from"] == SPECIALIST[0]

    async def test_a_missing_credential_falls_back_as_well(self, slots, runtime):
        """The key is checked before the request is sent, which is still before
        the first byte — the turn can still change hands."""
        slots["specialist"] = (SPECIALIST[0], "https://api.anthropic.test",
                               "anthropic")
        text, captured = await _run_stream(prompt=COMPLEX)
        assert text == ANSWER
        assert runtime["asked"] == [GUIDE[0]]
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["fallback_from"] == SPECIALIST[0]

    async def test_the_guide_failing_too_does_not_loop(self, slots, runtime):
        runtime["fails"] = {"pinned-x": "refused", GUIDE[0]: "refused"}
        text, captured = await _run_stream(prompt=TRIVIAL,
                                           model_override="pinned-x")
        assert runtime["asked"] == ["pinned-x", GUIDE[0]]
        assert captured == []
        assert "[Error:" in text

    async def test_a_dead_guide_is_not_asked_to_stand_in_for_itself(
        self, slots, runtime
    ):
        runtime["fails"][GUIDE[0]] = "refused"
        text, captured = await _run_stream(prompt=TRIVIAL)
        assert runtime["asked"] == [GUIDE[0]]
        assert captured == []
        assert "[Error:" in text

    async def test_a_failure_after_the_first_chunk_is_not_restarted(
        self, slots, runtime
    ):
        """The user has already read text from the pinned model; a second model
        taking over would rewrite what is on screen, so the turn keeps the one
        it has and says what went wrong."""
        runtime["fails"]["pinned-x"] = "drops"
        text, captured = await _run_stream(prompt=TRIVIAL,
                                           model_override="pinned-x")
        assert runtime["asked"] == ["pinned-x"]
        assert text.startswith(ANSWER[:20])
        assert "[Error:" in text
        assert captured[0]["model"] == "pinned-x"
        assert "fallback_from" not in captured[0]

    async def test_a_healthy_turn_reports_before_it_yields(self, slots, runtime):
        """The report waits for the response headers so it can tell the truth
        about a failure; it must still land ahead of the first chunk."""
        order = []
        adapter = agent_routes.LLMClientAdapter()
        async for _chunk in adapter.stream(
            messages=[{"role": "user", "content": TRIVIAL}],
            on_model_selected=lambda p: order.append("reported"),
        ):
            order.append("chunk")
        assert order[0] == "reported"


# -----------------------------------------------------------------------------
# The adapter reports what it resolved — chat path, including the fallback
# -----------------------------------------------------------------------------

def _caller(fails_for=()):
    """A ``call_llm_chat`` stand-in that refuses the named models."""
    def _call(**kwargs):
        if kwargs.get("model") in fails_for:
            raise ConnectionError(f"{kwargs.get('model')} is unreachable")
        return {"content": "answered", "tool_calls": None}
    return _call


class TestChatReports:

    async def test_reports_the_model_that_answered(self, slots):
        captured = []
        with patch("halbert_core.model.client.call_llm_chat", _caller()):
            await agent_routes.LLMClientAdapter().chat(
                messages=[{"role": "user", "content": COMPLEX}],
                on_model_selected=captured.append,
            )
        assert len(captured) == 1
        assert captured[0]["model"] == SPECIALIST[0]
        assert "fallback_from" not in captured[0]

    async def test_a_graceful_fallback_names_what_the_user_did_not_get(self, slots):
        captured = []
        with patch("halbert_core.model.client.call_llm_chat",
                   _caller(fails_for=(SPECIALIST[0],))):
            await agent_routes.LLMClientAdapter().chat(
                messages=[{"role": "user", "content": COMPLEX}],
                on_model_selected=captured.append,
            )
        assert len(captured) == 1
        assert captured[0]["fallback_from"] == SPECIALIST[0]
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["tier"] == "guide"

    async def test_a_fallback_from_a_pin_is_no_longer_reported_as_pinned(self, slots):
        """"Pinned" over a model the user never chose is the exact confusion
        this event exists to remove."""
        captured = []
        with patch("halbert_core.model.client.call_llm_chat",
                   _caller(fails_for=("pinned-x",))):
            await agent_routes.LLMClientAdapter().chat(
                messages=[{"role": "user", "content": TRIVIAL}],
                model_override="pinned-x",
                on_model_selected=captured.append,
            )
        assert captured[0]["fallback_from"] == "pinned-x"
        assert captured[0]["model"] == GUIDE[0]
        assert captured[0]["pinned"] is False
        assert captured[0]["escalated"] is False

    async def test_nothing_is_reported_when_nothing_answered(self, slots):
        captured = []
        with patch("halbert_core.model.client.call_llm_chat",
                   _caller(fails_for=(GUIDE[0],))):
            with pytest.raises(ConnectionError):
                await agent_routes.LLMClientAdapter().chat(
                    messages=[{"role": "user", "content": TRIVIAL}],
                    on_model_selected=captured.append,
                )
        assert captured == []

    async def test_a_vision_turn_reports_the_vision_model(self, slots):
        captured = []
        with patch("halbert_core.model.client.call_llm_chat", _caller()):
            await agent_routes.LLMClientAdapter().chat(
                messages=[{"role": "user", "content": TRIVIAL}],
                images=["b64"],
                on_model_selected=captured.append,
            )
        assert captured[0]["model"] == VISION[0]
        assert captured[0]["tier"] == "vision"


# -----------------------------------------------------------------------------
# Nothing lands on the shared adapter
# -----------------------------------------------------------------------------

class TestNothingIsStoredOnTheAdapter:

    def test_no_selection_attributes_exist(self):
        adapter = agent_routes.LLMClientAdapter()
        assert not hasattr(adapter, "on_model_selected")
        assert not hasattr(adapter, "last_turn")
        assert not hasattr(adapter, "selected_model")

    @pytest.mark.parametrize("method", ["chat", "stream"])
    def test_the_callback_is_a_per_call_parameter(self, method):
        import inspect
        params = inspect.signature(
            getattr(agent_routes.LLMClientAdapter, method)).parameters
        assert "on_model_selected" in params

    async def test_a_chat_call_adds_no_instance_state(self, slots):
        """One adapter serves every concurrent request; a model remembered on
        it would surface in someone else's session."""
        adapter = agent_routes.LLMClientAdapter()
        before = set(vars(adapter))
        with patch("halbert_core.model.client.call_llm_chat",
                   _caller(fails_for=(SPECIALIST[0],))):
            await adapter.chat(
                messages=[{"role": "user", "content": COMPLEX}],
                on_model_selected=lambda p: None,
            )
        assert set(vars(adapter)) == before

    async def test_a_stream_call_adds_no_instance_state(self, slots, runtime):
        adapter = agent_routes.LLMClientAdapter()
        before = set(vars(adapter))
        async for _chunk in adapter.stream(
            messages=[{"role": "user", "content": COMPLEX}],
            on_model_selected=lambda p: None,
        ):
            pass
        assert set(vars(adapter)) == before


# -----------------------------------------------------------------------------
# RESPONDING announces it once, before the answer
# -----------------------------------------------------------------------------

PAYLOAD = {
    "model": "model-a",
    "endpoint": "http://localhost:11434",
    "provider": "ollama",
    "tier": "specialist",
    "pinned": False,
    "escalated": True,
    "reason": "Complexity score 0.80 (threshold 0.50)",
}


class _ReportingLLM:
    """An LLM that reports its selection only when asked to."""

    def __init__(self, payload=None):
        self._payload = payload
        self.chat_callbacks = []

    async def chat(self, messages, tools=None, on_model_selected=None, **kwargs):
        self.chat_callbacks.append(on_model_selected)
        if on_model_selected and self._payload:
            on_model_selected(dict(self._payload))
        return LLMResponse(content="The answer is 42.", tool_calls=None, plan=None)

    async def stream(self, messages, on_model_selected=None, **kwargs):
        if on_model_selected and self._payload:
            on_model_selected(dict(self._payload))
        for word in ("The", "answer", "is", "42."):
            yield word + " "


class _NonStreamingLLM:
    """Same, minus ``stream`` — the state machine picks its path by
    ``hasattr(self.llm, 'stream')``, so the branch only exists for a client
    that genuinely has no streaming method."""

    def __init__(self, payload=None):
        self._payload = payload
        self.chat_callbacks = []

    async def chat(self, messages, tools=None, on_model_selected=None, **kwargs):
        self.chat_callbacks.append(on_model_selected)
        if on_model_selected and self._payload:
            on_model_selected(dict(self._payload))
        return LLMResponse(content="The answer is 42.", tool_calls=None, plan=None)


class _Empty:
    async def search(self, query, limit=5):
        return []

    async def recall(self, query, limit=5):
        return []

    async def store_interaction(self, **kw):
        return None


def _build_agent(llm):
    from halbert_core.tools import ToolSafetyFramework, ToolExecutor
    from halbert_core.context import ContextAssembler, TokenCounter
    from halbert_core.prompts import AgentPromptBuilder

    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        context_assembler=ContextAssembler(
            rag_service=_Empty(),
            memory_service=_Empty(),
            discovery_service=_Empty(),
            token_counter=TokenCounter(),
        ),
        prompt_builder=AgentPromptBuilder(),
        max_loops=3,
    )


class TestRespondingAnnouncesTheTurn:

    async def test_emitted_exactly_once_per_turn(self):
        agent = _build_agent(_ReportingLLM(PAYLOAD))
        events = [e async for e in agent.process("hello")]
        assert len([e for e in events if e.type == "model_selected"]) == 1

    async def test_carries_the_reported_selection(self):
        agent = _build_agent(_ReportingLLM(PAYLOAD))
        events = [e async for e in agent.process("hello")]
        ev = next(e for e in events if e.type == "model_selected")
        assert ev.data["model"] == "model-a"
        assert ev.data["escalated"] is True
        assert ev.data["reason"] == PAYLOAD["reason"]
        assert ev.session_id == agent.ctx.session_id

    async def test_precedes_the_first_response_chunk(self):
        """The banner has to be on screen before the text it explains."""
        agent = _build_agent(_ReportingLLM(PAYLOAD))
        types = [e.type async for e in agent.process("hello")]
        assert types.index("model_selected") < types.index("response_chunk")

    async def test_planning_is_not_asked_to_report(self):
        """PLANNING resolves against a different prompt and can land on a
        different tier; announcing its choice would credit the answer to a
        model that never saw the question."""
        llm = _ReportingLLM(PAYLOAD)
        agent = _build_agent(llm)
        [e async for e in agent.process("hello")]
        assert llm.chat_callbacks  # PLANNING did call chat()
        assert all(cb is None for cb in llm.chat_callbacks)

    async def test_the_non_streaming_branch_announces_too(self):
        agent = _build_agent(_NonStreamingLLM(PAYLOAD))
        events = [e async for e in agent.process("hello")]
        selected = [e for e in events if e.type == "model_selected"]
        assert len(selected) == 1
        assert selected[0].data["model"] == "model-a"

    async def test_a_client_that_reports_nothing_emits_nothing(self):
        agent = _build_agent(_ReportingLLM(payload=None))
        events = [e async for e in agent.process("hello")]
        assert not [e for e in events if e.type == "model_selected"]


# -----------------------------------------------------------------------------
# End to end: the real adapter behind the real state machine
# -----------------------------------------------------------------------------

class TestTheFallbackChipReachesTheStream:
    """RESPONDING is the only place ``model_selected`` is emitted, and it takes
    what stream() reports. With the fallback in chat() alone, no production
    turn could ever carry ``fallback_from`` — the amber chip was dead code."""

    async def test_a_pinned_offline_turn_is_announced_as_a_fallback(
        self, slots, runtime
    ):
        runtime["fails"]["pinned-x"] = "refused"
        agent = _build_agent(agent_routes.LLMClientAdapter())
        with patch("halbert_core.model.client.call_llm_chat", _caller()):
            events = [e async for e in agent.process("hello",
                                                     model_override="pinned-x")]
        selected = [e for e in events if e.type == "model_selected"]
        assert len(selected) == 1
        assert selected[0].data["model"] == GUIDE[0]
        assert selected[0].data["fallback_from"] == "pinned-x"

    async def test_the_chip_precedes_the_text_it_explains(self, slots, runtime):
        runtime["fails"]["pinned-x"] = "refused"
        agent = _build_agent(agent_routes.LLMClientAdapter())
        with patch("halbert_core.model.client.call_llm_chat", _caller()):
            types = [e.type async for e in agent.process(
                "hello", model_override="pinned-x")]
        assert types.index("model_selected") < types.index("response_chunk")

    async def test_the_user_reads_the_answer_and_not_the_error(
        self, slots, runtime
    ):
        runtime["fails"]["pinned-x"] = "refused"
        agent = _build_agent(agent_routes.LLMClientAdapter())
        with patch("halbert_core.model.client.call_llm_chat", _caller()):
            events = [e async for e in agent.process("hello",
                                                     model_override="pinned-x")]
        body = "".join(e.data.get("content", "") for e in events
                       if e.type == "response_chunk")
        assert body == ANSWER
