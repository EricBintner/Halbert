# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Agent memory between turns (E-3).

Covers the whole path: prior turns are loaded from the store, reach the model
as a real ``messages[]`` array instead of prose, the finished turn is written
back, and one turn at a time touches the shared agent.
"""

import asyncio
import itertools
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from halbert_core.agents import AgentStateMachine
from halbert_core.agents.conversation import Conversation, ConversationStore
from halbert_core.context.assembler import (
    AssembledContext,
    ContextAssembler,
    DEFAULT_CONVERSATION_TOKENS,
    build_conversation_window,
)
from halbert_core.context.watermark import ContextWatermark
from halbert_core.dashboard.routes import agent as agent_routes


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class _Reply:
    def __init__(self, content=""):
        self.content = content
        self.tool_calls = None
        self.plan = None


class RecordingLLM:
    """Records the messages[] array each call site sends."""

    def __init__(self, reply="Nginx is stopped.", mid_stream=None):
        self.reply = reply
        self.mid_stream = mid_stream
        self.chat_calls = []
        self.stream_calls = []
        self.max_tokens = 8192
        self.temperature = 0.7

    async def chat(self, messages, tools=None, **kwargs):
        self.chat_calls.append(messages)
        return _Reply(self.reply)

    async def stream(self, messages, **kwargs):
        self.stream_calls.append(messages)
        yield self.reply
        if self.mid_stream is not None:
            self.mid_stream()
            yield " (continued)"


class ExplodingLLM(RecordingLLM):
    async def stream(self, messages, **kwargs):
        self.stream_calls.append(messages)
        raise RuntimeError("model unreachable")
        yield  # pragma: no cover - makes this an async generator


def make_agent(llm=None):
    """An agent that plans once and responds once — one call per call site."""
    return AgentStateMachine(llm_client=llm or RecordingLLM(), max_loops=2)


def sse_events(body: str):
    return [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def conversation_with(*turns):
    conv = Conversation(conversation_id="c1")
    for role, content in turns:
        conv.add_message(role, content)
    return conv


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = ConversationStore(storage_path=str(tmp_path / "conversations"))
    monkeypatch.setattr("halbert_core.agents.conversation._conversation_store", s)
    return s


@pytest.fixture
def client(monkeypatch, store):
    """TestClient over the agent router with a recording agent behind it."""
    agent = make_agent()
    app = FastAPI()
    app.include_router(agent_routes.router)
    monkeypatch.setattr(agent_routes, "_agent_instance", agent)
    agent_routes._session_conversations.clear()
    return TestClient(app), agent


# ---------------------------------------------------------------------------
# The conversation window: what history a turn can afford
# ---------------------------------------------------------------------------

class TestConversationWindow:

    def test_prior_turns_come_back_as_role_content(self):
        conv = conversation_with(
            ("user", "Check nginx"), ("assistant", "Nginx is stopped."),
        )
        window = build_conversation_window(conv, query="Start it", max_tokens=800)
        assert window == [
            {"role": "user", "content": "Check nginx"},
            {"role": "assistant", "content": "Nginx is stopped."},
        ]

    def test_below_the_watermark_history_is_verbatim(self):
        conv = conversation_with(*[("user", f"turn {i}") for i in range(12)])
        window = build_conversation_window(conv, query="next", max_tokens=800)
        # Twelve short turns clear the old message-count trigger and still fit,
        # so nothing is summarised away.
        assert len(window) == 12
        assert not any(m["role"] == "system" for m in window)

    def test_budget_is_a_ceiling(self):
        conv = conversation_with(*[("user", "word " * 200) for _ in range(20)])
        counter_budget = 300
        window = build_conversation_window(
            conv, query="next", max_tokens=counter_budget
        )
        cost = sum(len(m["content"]) // 4 + 5 for m in window)
        assert cost <= counter_budget
        assert len(window) < 20

    def test_empty_messages_are_dropped(self):
        conv = conversation_with(
            ("user", "Check nginx"), ("assistant", "   "), ("user", "Start it"),
        )
        window = build_conversation_window(conv, query="now", max_tokens=800)
        assert [m["content"] for m in window] == ["Check nginx", "Start it"]

    def test_zero_budget_carries_nothing(self):
        conv = conversation_with(("user", "Check nginx"))
        assert build_conversation_window(conv, query="x", max_tokens=0) == []

    def test_watermark_compaction_summarises_and_stamps(self):
        conv = conversation_with(*[
            ("user" if i % 2 == 0 else "assistant", f"disk usage detail {i} " * 20)
            for i in range(16)
        ])
        window = build_conversation_window(
            conv, query="unrelated firewall question", max_tokens=400, now=10_000.0
        )
        assert conv.metadata["last_compaction_ts"] == 10_000.0
        assert any(m["role"] == "system" for m in window)

    def test_closed_gate_trims_instead_of_summarising(self):
        conv = conversation_with(*[
            ("user" if i % 2 == 0 else "assistant", f"disk usage detail {i} " * 20)
            for i in range(16)
        ])
        conv.metadata["last_compaction_ts"] = 9_990.0
        window = build_conversation_window(
            conv,
            # Same topic as the stored turns, so no topic boundary reopens the
            # 2h gate that the recent compaction closed.
            query="more disk usage detail please",
            max_tokens=400,
            now=10_000.0,
        )
        assert conv.metadata["last_compaction_ts"] == 9_990.0
        assert not any(m["role"] == "system" for m in window)
        assert sum(len(m["content"]) // 4 + 5 for m in window) <= 400

    def test_a_window_never_opens_on_an_assistant_turn(self):
        """The Anthropic Messages API rejects an array whose first message is
        not ``user``, and since E-3 this window *is* that array. Twenty-seven
        long-conversation shapes at the production default budget; fourteen of
        them used to hand the model an assistant turn first."""
        for count, user_len, reply_len in itertools.product(
            (60, 100, 120), (6, 12, 25), (6, 12, 25)
        ):
            conv = Conversation(conversation_id="c1")
            for i in range(count):
                role = "user" if i % 2 == 0 else "assistant"
                length = user_len if role == "user" else reply_len
                conv.add_message(role, f"systemd unit detail {i} " * length)

            window = build_conversation_window(
                conv, query="and the timer?", max_tokens=DEFAULT_CONVERSATION_TOKENS
            )
            turns = [m for m in window if m["role"] in ("user", "assistant")]
            shape = (count, user_len, reply_len, [m["role"] for m in window])
            assert turns, shape
            assert turns[0]["role"] == "user", shape

    def test_an_answer_the_budget_drops_takes_its_question_with_it(self):
        conv = conversation_with(
            ("user", "which masked unit blocks the boot? " * 60),
            ("assistant", "postgresql.service"),
            ("user", "which masked unit is left?"),
            ("assistant", "redis.service"),
        )
        # Same topic as the newest question and a recent stamp, so the
        # compaction gates stay shut and this is the plain trim path.
        conv.metadata["last_compaction_ts"] = 9_990.0
        window = build_conversation_window(
            conv, query="which masked unit is left, unmask it",
            max_tokens=60, now=10_000.0,
        )
        # The first answer is two words and fits on its own; it is dropped
        # anyway, because the long question it answered does not.
        assert [m["role"] for m in window] == ["user", "assistant"]
        assert window[0]["content"] == "which masked unit is left?"
        assert not any("postgresql" in m["content"] for m in window)

    def test_a_history_that_opens_on_an_assistant_turn_is_trimmed_to_fit(self):
        conv = conversation_with(
            ("assistant", "Good morning."),
            ("user", "Check nginx"),
            ("assistant", "Nginx is stopped."),
        )
        window = build_conversation_window(conv, query="Start it", max_tokens=800)
        assert [m["role"] for m in window] == ["user", "assistant"]

    def test_one_trigger_is_the_watermark_not_the_count(self):
        """Twelve tiny turns fit; six long ones do not. A count says the
        opposite of both."""
        wm = ContextWatermark()
        tiny = conversation_with(*[("user", "ok") for _ in range(12)])
        assert len(build_conversation_window(tiny, max_tokens=800, watermark=wm)) == 12

        heavy = conversation_with(*[("user", "detail " * 400) for _ in range(6)])
        window = build_conversation_window(heavy, max_tokens=800, watermark=wm)
        assert len(window) < 6


# ---------------------------------------------------------------------------
# The messages[] array
# ---------------------------------------------------------------------------

class TestMessagesArray:

    def test_shape_is_instructions_history_then_question(self):
        agent = make_agent()
        agent.ctx = _ctx(
            "Start it",
            [{"role": "user", "content": "Check nginx"},
             {"role": "assistant", "content": "Nginx is stopped."}],
        )
        messages = agent._build_messages("INSTRUCTIONS")
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert messages[0]["content"] == "INSTRUCTIONS"
        assert messages[-1]["content"] == "Start it"

    def test_history_summary_folds_into_the_instructions(self):
        agent = make_agent()
        agent.ctx = _ctx(
            "Start it",
            [{"role": "system", "content": "Previous conversation summary: nginx"},
             {"role": "user", "content": "Check nginx"},
             {"role": "assistant", "content": "Nginx is stopped."}],
        )
        messages = agent._build_messages("INSTRUCTIONS")
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert "Previous conversation summary: nginx" in messages[0]["content"]

    def test_unanswered_turn_does_not_produce_two_user_messages(self):
        agent = make_agent()
        agent.ctx = _ctx(
            "Start it",
            [{"role": "user", "content": "Check nginx"}],  # turn was cancelled
        )
        messages = agent._build_messages("INSTRUCTIONS")
        assert [m["role"] for m in messages] == ["system", "user"]
        assert "Check nginx" in messages[-1]["content"]
        assert "Start it" in messages[-1]["content"]

    def test_empty_history_is_a_single_question(self):
        agent = make_agent()
        agent.ctx = _ctx("Check nginx", [])
        assert agent._build_messages("INSTRUCTIONS") == [
            {"role": "system", "content": "INSTRUCTIONS"},
            {"role": "user", "content": "Check nginx"},
        ]

    async def test_both_call_sites_receive_the_history(self):
        llm = RecordingLLM()
        agent = make_agent(llm)
        history = [
            {"role": "user", "content": "Check nginx"},
            {"role": "assistant", "content": "Nginx is stopped."},
        ]
        async for _ in agent.process(
            query="Start it", session_id="s1", conversation_history=history
        ):
            pass

        assert llm.chat_calls and llm.stream_calls
        for messages in (llm.chat_calls[0], llm.stream_calls[0]):
            contents = [m["content"] for m in messages]
            assert "Check nginx" in contents
            assert "Nginx is stopped." in contents
            assert messages[-1] == {"role": "user", "content": "Start it"}

    async def test_history_is_sent_once_not_twice(self):
        """The assembler must not also flatten the turns into the prompt, and
        must be told which session is asking so its memory source can leave out
        the same turns it stored as interactions."""
        seen = {}

        class FakeAssembler:
            async def assemble(self, **kwargs):
                seen.update(kwargs)
                return AssembledContext(content="", sources=[], total_tokens=0)

        llm = RecordingLLM()
        agent = AgentStateMachine(
            llm_client=llm, context_assembler=FakeAssembler(), max_loops=2
        )
        async for _ in agent.process(
            query="Start it",
            session_id="s1",
            conversation_history=[
                {"role": "user", "content": "Check nginx"},
                {"role": "assistant", "content": "Nginx is stopped."},
            ],
        ):
            pass

        assert seen.get("conversation") is None
        assert seen.get("session_id") == "s1"
        planning = llm.chat_calls[0]
        assert "Nginx is stopped." not in planning[0]["content"]
        assert "Nginx is stopped." in [m["content"] for m in planning]

    async def test_images_reach_planning_as_well_as_responding(self):
        llm = RecordingLLM()

        class Spy(RecordingLLM):
            def __init__(self):
                super().__init__()
                self.image_kwargs = []

            async def chat(self, messages, tools=None, **kwargs):
                self.image_kwargs.append(kwargs.get("images"))
                return await super().chat(messages, tools=tools, **kwargs)

            async def stream(self, messages, **kwargs):
                self.image_kwargs.append(kwargs.get("images"))
                async for chunk in super().stream(messages, **kwargs):
                    yield chunk

        spy = Spy()
        agent = make_agent(spy)
        async for _ in agent.process(
            query="what is this", session_id="s1", images=["b64"]
        ):
            pass
        assert spy.image_kwargs == [["b64"], ["b64"]]


def _ctx(query, history):
    from halbert_core.agents.states import StateContext

    return StateContext(
        session_id="s1",
        request_id="r1",
        user_query=query,
        conversation_history=history,
    )


# ---------------------------------------------------------------------------
# Route wiring: load, persist, serialise
# ---------------------------------------------------------------------------

class TestRouteMemory:

    def test_stored_history_reaches_the_model(self, client, store):
        api, agent = client
        conv = store.get_or_create("conv-1")
        conv.add_message("user", "Check nginx")
        conv.add_message("assistant", "Nginx is stopped.")
        store.save(conv)

        api.post("/api/agent/message",
                 json={"message": "Start it", "conversation_id": "conv-1"})

        planning = agent.llm.chat_calls[0]
        assert "Nginx is stopped." in [m["content"] for m in planning]

    def test_finished_turn_is_written_back(self, client, store):
        api, agent = client
        api.post("/api/agent/message",
                 json={"message": "Check nginx", "conversation_id": "conv-1"})

        conv = store.get("conv-1")
        assert [(m.role, m.content) for m in conv.messages] == [
            ("user", "Check nginx"),
            ("assistant", "Nginx is stopped."),
        ]

    def test_conversation_id_falls_back_to_the_session(self, client, store):
        api, agent = client
        api.post("/api/agent/message",
                 json={"message": "Check nginx", "session_id": "sess-9"})
        assert store.get("sess-9") is not None

    def test_a_failed_turn_still_leaves_no_hole(self, monkeypatch, store):
        agent = make_agent(ExplodingLLM())
        app = FastAPI()
        app.include_router(agent_routes.router)
        monkeypatch.setattr(agent_routes, "_agent_instance", agent)
        agent_routes._session_conversations.clear()

        TestClient(app).post(
            "/api/agent/message",
            json={"message": "Check nginx", "conversation_id": "conv-1"},
        )

        conv = store.get("conv-1")
        assert [m.role for m in conv.messages] == ["user"]
        assert conv.messages[0].content == "Check nginx"

    def test_a_cancelled_turn_still_leaves_no_hole(self, monkeypatch, store):
        agent = make_agent()
        # cancel_session() is what POST /cancel calls, from a second request
        # while this stream is mid-flight. Nothing else stops a running turn,
        # so setting the flag by hand here would prove nothing about the button.
        agent.llm.mid_stream = lambda: agent.cancel_session("sess-c")
        app = FastAPI()
        app.include_router(agent_routes.router)
        monkeypatch.setattr(agent_routes, "_agent_instance", agent)
        agent_routes._session_conversations.clear()

        body = TestClient(app).post(
            "/api/agent/message",
            json={"message": "Check nginx", "session_id": "sess-c"},
        ).text

        assert any(e["type"] == "cancelled" for e in sse_events(body))
        conv = store.get("sess-c")
        assert [m.role for m in conv.messages] == ["user", "assistant"]
        assert conv.messages[1].content.strip()

    def test_cancelling_raises_the_flag_the_stream_polls(self, client):
        api, agent = client
        agent.active_sessions["sess-c"] = _ctx("Check nginx", [])

        assert api.post("/api/agent/cancel/sess-c").json()["cancelled"] is True
        assert agent.cancelled["sess-c"] is True

    def test_a_finished_turn_leaves_no_cancellation_flag_behind(self, client, store):
        api, agent = client
        api.post("/api/agent/message",
                 json={"message": "Check nginx", "session_id": "sess-9"})
        assert "sess-9" not in agent.cancelled

    def test_two_turns_build_on_each_other(self, client, store):
        """V-05: the follow-up must carry its own referent."""
        api, agent = client
        api.post("/api/agent/message",
                 json={"message": "Check nginx", "conversation_id": "conv-1"})
        api.post("/api/agent/message",
                 json={"message": "Start it", "conversation_id": "conv-1"})

        second_turn = agent.llm.stream_calls[1]
        contents = [m["content"] for m in second_turn]
        assert "Check nginx" in contents
        assert "Nginx is stopped." in contents
        assert second_turn[-1] == {"role": "user", "content": "Start it"}

    def test_the_route_holds_the_turn_lock(self, monkeypatch, store):
        agent = make_agent()
        watched = _WatchedLock()
        monkeypatch.setattr(
            AgentStateMachine, "turn_lock", property(lambda self: watched)
        )
        app = FastAPI()
        app.include_router(agent_routes.router)
        monkeypatch.setattr(agent_routes, "_agent_instance", agent)
        agent_routes._session_conversations.clear()

        TestClient(app).post("/api/agent/message", json={"message": "Check nginx"})
        assert watched.acquisitions == 1


def _pretend_configured_model(monkeypatch, model):
    """Stand in for models.yml resolution; returns the kwargs it was asked."""
    asked = []

    def resolve(prompt, **kwargs):
        asked.append(kwargs)
        return agent_routes.TurnModel(
            model, "http://localhost:11434", "ollama", "guide",
            bool(kwargs.get("model_override")), False, "test",
        )

    monkeypatch.setattr(agent_routes, "_resolve_turn_model", resolve)
    return asked


def _record_history_budgets(monkeypatch):
    """Collect the budget every turn hands to the conversation window."""
    budgets = []
    real = agent_routes._load_history

    def spy(conversation_id, query, budget):
        budgets.append(budget)
        return real(conversation_id, query, budget)

    monkeypatch.setattr(agent_routes, "_load_history", spy)
    return budgets


class _WatchedLock:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.acquisitions = 0

    async def __aenter__(self):
        await self._lock.acquire()
        self.acquisitions += 1
        return self

    async def __aexit__(self, *exc):
        self._lock.release()


# ---------------------------------------------------------------------------
# The turn lock
# ---------------------------------------------------------------------------

class TestTurnLock:

    async def test_one_lock_per_loop(self):
        agent = make_agent()
        assert agent.turn_lock is agent.turn_lock

    async def test_turns_queue_instead_of_interleaving(self):
        agent = make_agent()
        order = []

        async def turn(name):
            async with agent.turn_lock:
                order.append(f"{name}-start")
                await asyncio.sleep(0.01)
                order.append(f"{name}-end")

        await asyncio.gather(turn("a"), turn("b"))
        assert order in (
            ["a-start", "a-end", "b-start", "b-end"],
            ["b-start", "b-end", "a-start", "a-end"],
        )

    async def test_a_queued_turn_keeps_its_own_context(self):
        """Without serialisation the second turn overwrites ``agent.ctx`` and
        both answers describe the same question."""
        llm = RecordingLLM()
        agent = make_agent(llm)

        async def turn(query, session_id):
            async with agent.turn_lock:
                async for _ in agent.process(query=query, session_id=session_id):
                    await asyncio.sleep(0)

        await asyncio.gather(turn("Check nginx", "a"), turn("Start it", "b"))

        asked = [messages[-1]["content"] for messages in llm.stream_calls]
        assert sorted(asked) == ["Check nginx", "Start it"]


# ---------------------------------------------------------------------------
# Budget selection and adapter shape
# ---------------------------------------------------------------------------

class TestBudgetAndAdapter:

    def test_budget_tracks_the_model_tier(self):
        assert agent_routes._history_budget("some-model:3b") < \
            agent_routes._history_budget("some-model:70b")

    def test_unknown_model_gets_the_default_budget(self):
        assert agent_routes._history_budget(None) == DEFAULT_CONVERSATION_TOKENS

    def test_an_unpinned_turn_is_budgeted_for_the_configured_model(
        self, client, store, monkeypatch
    ):
        """The picker sends no ``model`` unless the user pinned one, so
        budgeting off the pin sized every ordinary turn for the empty string —
        a constant, whatever models.yml actually names."""
        api, agent = client
        _pretend_configured_model(monkeypatch, "some-model:3b")
        budgets = _record_history_budgets(monkeypatch)

        api.post("/api/agent/message", json={"message": "Check nginx"})

        assert budgets == [agent_routes._history_budget("some-model:3b")]
        assert budgets[0] != DEFAULT_CONVERSATION_TOKENS

    def test_a_pinned_model_is_budgeted_for_itself(
        self, client, store, monkeypatch
    ):
        api, agent = client
        asked = _pretend_configured_model(monkeypatch, "some-model:70b")
        budgets = _record_history_budgets(monkeypatch)

        api.post("/api/agent/message", json={
            "message": "Check nginx",
            "model": "some-model:70b",
            "endpoint_id": "endpoint-2",
        })

        assert asked[0]["model_override"] == "some-model:70b"
        assert asked[0]["endpoint_id"] == "endpoint-2"
        assert budgets == [agent_routes._history_budget("some-model:70b")]

    def test_a_turn_survives_a_model_it_cannot_resolve(
        self, client, store, monkeypatch
    ):
        """No model configured yet is a bad answer; it must not be no answer."""
        api, agent = client

        def unconfigured(*args, **kwargs):
            raise HTTPException(400, "no model configured")

        monkeypatch.setattr(agent_routes, "_resolve_turn_model", unconfigured)
        budgets = _record_history_budgets(monkeypatch)

        response = api.post("/api/agent/message",
                            json={"message": "Check nginx", "conversation_id": "conv-1"})

        assert response.status_code == 200
        assert budgets == [DEFAULT_CONVERSATION_TOKENS]
        assert store.get("conv-1") is not None

    def test_images_land_on_the_newest_question(self):
        messages = [
            {"role": "user", "content": "Check nginx"},
            {"role": "assistant", "content": "Nginx is stopped."},
            {"role": "user", "content": "and this screenshot?"},
        ]
        agent_routes._attach_images(messages, ["b64"])
        assert "images" not in messages[0]
        assert messages[2]["images"] == ["b64"]

    async def test_this_conversation_is_not_recalled_back_as_prose(self):
        """Every answered turn is also stored as an ``interaction`` memory, so
        without this the assembler handed the model a paraphrase of the same
        exchange its ``messages[]`` array already carried verbatim."""

        class FakeMemory:
            async def recall(self, query, limit=5):
                return [
                    {"content": "Q: Check nginx\nA: Nginx is stopped.",
                     "type": "interaction", "metadata": {"session_id": "s1"}},
                    {"content": "Q: Check nginx\nA: You restarted it last week.",
                     "type": "interaction", "metadata": {"session_id": "older"}},
                    {"content": "The user runs nginx behind a reverse proxy.",
                     "type": "fact", "metadata": {}},
                ]

        assembled = await ContextAssembler(memory_service=FakeMemory()).assemble(
            query="nginx", session_id="s1", use_compression=False,
        )

        assert "Nginx is stopped." not in assembled.content
        # Another conversation's interaction is new information, not an echo.
        assert "You restarted it last week." in assembled.content
        assert "reverse proxy" in assembled.content

    async def test_every_system_message_reaches_the_model(self, monkeypatch):
        sent = {}

        def fake_call(**kwargs):
            sent.update(kwargs)
            return {"content": "ok"}

        monkeypatch.setattr("halbert_core.model.client.call_llm_chat", fake_call)
        monkeypatch.setattr(
            agent_routes, "_resolve_turn_model",
            lambda *a, **k: agent_routes.TurnModel(
                "model-a", "http://localhost:11434", "ollama", "guide",
                False, False, "test",
            ),
        )

        await agent_routes.LLMClientAdapter().chat(messages=[
            {"role": "system", "content": "INSTRUCTIONS"},
            {"role": "user", "content": "Check nginx"},
            {"role": "system", "content": "EARLIER SUMMARY"},
            {"role": "user", "content": "Start it"},
        ])

        systems = [m for m in sent["messages"] if m["role"] == "system"]
        assert len(systems) == 1
        assert "INSTRUCTIONS" in systems[0]["content"]
        assert "EARLIER SUMMARY" in systems[0]["content"]
