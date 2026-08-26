# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""
B1: the Haloysius cognition tick must run exactly once per agent turn,
regardless of which states the loop visits, and PLANNING's terminal
branches must route through REFLECTING.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState, CRAGAction


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _mk_llm(tool_call=None):
    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value=MagicMock(content="ok", tool_calls=tool_call and [tool_call], plan=None)
    )

    async def _stream(messages, **kwargs):
        yield "hello"

    llm.stream = _stream
    return llm


class _Rag:
    def __init__(self, results):
        self.results = results

    async def search(self, q, limit=5):
        return self.results


class _RecordingTick:
    def __init__(self, raise_exc=None):
        self.calls = []
        self.raise_exc = raise_exc

    def __call__(self, cognition, user_message, assistant_response):
        self.calls.append(
            {
                "cognition": cognition,
                "user_message": user_message,
                "assistant_response": assistant_response,
            }
        )
        if self.raise_exc:
            raise self.raise_exc
        return MagicMock(thought=None)


def _crag(action, conf):
    crag = MagicMock()
    crag.evaluate = AsyncMock(
        return_value=MagicMock(confidence=conf, action=MagicMock(value=action))
    )
    return crag


@pytest.fixture
def mock_cognition(monkeypatch):
    cog = MagicMock()
    cog.worries.check_intrusions = MagicMock(return_value=[])
    monkeypatch.setattr(
        "halbert_core.integrations.cognition_wiring.get_cognition", lambda: cog
    )
    return cog


async def _run(agent, query="what is sshd_config"):
    events = []
    async for e in agent.process(query):
        events.append(e)
    states = [e.data["state"] for e in events if e.type == "state_change"]
    return events, states


# -----------------------------------------------------------------------------
# Tests (spec 1)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_direct_respond_turn_ticks_exactly_once(mock_cognition):
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick,
    )
    events, states = await _run(agent)

    assert states == [
        "planning", "searching", "observing", "planning",
        "reflecting", "responding", "idle",
    ]
    assert len(tick.calls) == 1
    assert tick.calls[0]["user_message"] == "what is sshd_config"
    assert tick.calls[0]["cognition"] is mock_cognition
    assert agent.ctx.cognition_ticked is True


@pytest.mark.asyncio
async def test_search_observe_reflect_respond_ticks_exactly_once(mock_cognition):
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([{"content": "x"}]),
        crag_evaluator=_crag("CORRECT", 0.9), max_loops=5, cognition_tick=tick,
    )
    events, states = await _run(agent)

    assert "reflecting" in states
    assert states.count("reflecting") == 1
    assert len(tick.calls) == 1
    assert agent.ctx.cognition_ticked is True


@pytest.mark.asyncio
async def test_max_loops_guard_path_ticks_exactly_once(mock_cognition):
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([{"content": "x"}]),
        crag_evaluator=_crag("INCORRECT", 0.2), max_loops=2, cognition_tick=tick,
    )
    events, states = await _run(agent)

    assert "reflecting" in states
    assert len(tick.calls) == 1
    assert agent.current_state == AgentState.IDLE


@pytest.mark.asyncio
async def test_error_give_up_path_ticks_once_with_real_reply(mock_cognition):
    """Failure exit: ERROR give-up (3 recovery attempts) jumps straight to
    RESPONDING, bypassing REFLECTING; the tick must still fire exactly once,
    from RESPONDING, with the real reply as assistant_response."""
    llm = _mk_llm()
    llm.chat = AsyncMock(side_effect=RuntimeError("planning exploded"))
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=llm, rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick,
    )
    events, states = await _run(agent)

    # ERROR is entered by direct assignment (no state_change event), so count
    # the recovery attempts via the error events instead.
    assert sum(1 for e in events if e.type == "error"
               and e.data.get("message") == "planning exploded") == 3
    assert "reflecting" not in states
    # RESPONDING now completes cleanly and transitions to IDLE (round 2, 5b).
    assert states[-2:] == ["responding", "idle"]
    assert agent.current_state == AgentState.IDLE
    assert any(e.type == "response_complete" and e.data["content"] == "hello" for e in events)
    assert len(tick.calls) == 1
    assert tick.calls[0]["assistant_response"] == "hello"
    assert tick.calls[0]["user_message"] == "what is sshd_config"
    # Round 2 (5b): the give-up path already set conversation status ERROR;
    # RESPONDING's success path must not then raise on ERROR -> SUCCESS and
    # emit an error event after the reply streamed.
    complete_idx = next(i for i, e in enumerate(events) if e.type == "response_complete")
    assert not any(e.type == "error" for e in events[complete_idx + 1:])
    assert any(e.type == "session_ended" for e in events)
    assert agent.ctx.conversation_status.current().value == "error"


@pytest.mark.asyncio
async def test_tick_exception_does_not_break_turn(mock_cognition):
    tick = _RecordingTick(raise_exc=RuntimeError("boom"))
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick,
    )
    events, states = await _run(agent)

    assert agent.current_state == AgentState.IDLE
    assert len(tick.calls) == 1
    assert any(
        e.type == "response_complete" and e.data["content"] == "hello" for e in events
    )
    assert any(e.type == "session_ended" for e in events)
    assert not any(e.type == "error" for e in events)


@pytest.mark.asyncio
async def test_no_tick_wired_does_not_set_flag():
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=None,
    )
    events, states = await _run(agent)

    assert agent.current_state == AgentState.IDLE
    assert agent.ctx.cognition_ticked is False
    assert any(e.type == "session_ended" for e in events)


# -----------------------------------------------------------------------------
# Tests (spec 5: PLANNING routes through REFLECTING)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_planning_default_routes_through_reflecting(mock_cognition):
    tick = MagicMock(return_value=None)
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), cognition_tick=tick, max_loops=5,
    )
    events, states = await _run(agent, "hello")

    assert states == [
        "planning", "searching", "observing", "planning",
        "reflecting", "responding", "idle",
    ]
    assert tick.call_count == 1


@pytest.mark.asyncio
async def test_planning_crag_correct_routes_through_reflecting(mock_cognition):
    tick = MagicMock(return_value=None)
    # OBSERVING sees the crag result first; force it to fall back to PLANNING
    # by making the first evaluation INCORRECT and the second (in PLANNING)
    # CORRECT.
    crag = MagicMock()
    crag.evaluate = AsyncMock(
        side_effect=[
            MagicMock(confidence=0.2, action=MagicMock(value="INCORRECT")),
            MagicMock(confidence=0.9, action=MagicMock(value="CORRECT")),
        ]
    )
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([{"content": "doc"}]),
        crag_evaluator=crag, cognition_tick=tick, max_loops=5,
    )
    events, states = await _run(agent, "hello")

    assert states.count("reflecting") == 1
    assert states.index("reflecting") < states.index("responding")
    assert states[states.index("reflecting") - 1] == "planning"
    assert agent.ctx.crag_action == CRAGAction.CORRECT
    assert tick.call_count == 1


# -----------------------------------------------------------------------------
# Round 2: greeting turns skip SEARCHING; max-loops guard falls through
# -----------------------------------------------------------------------------

class _StubIntake:
    def __init__(self, greeting):
        self.greeting = greeting

    def analyze(self, text):
        return MagicMock(
            intent="greeting" if self.greeting else "question",
            is_greeting=self.greeting,
            is_farewell=False,
            needs_retrieval=not self.greeting,
            complexity_score=0.1,
            recommended_model="fast",
            context_budget=500,
        )


@pytest.mark.asyncio
async def test_greeting_turn_skips_searching_and_ticks_once(mock_cognition):
    tick = _RecordingTick()
    rag = _Rag([{"content": "Zoom plist", "metadata": {}}])
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=rag, crag_evaluator=None,
        max_loops=5, cognition_tick=tick, intake_pipeline=_StubIntake(True),
    )
    events, states = await _run(agent, query="hi")

    assert "searching" not in states
    assert states == ["planning", "reflecting", "responding", "idle"]
    assert agent.ctx.retrieved_context == []
    assert len(tick.calls) == 1
    assert tick.calls[0]["user_message"] == "hi"
    assert any(e.type == "response_complete" for e in events)


@pytest.mark.asyncio
async def test_non_greeting_intake_still_searches(mock_cognition):
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick, intake_pipeline=_StubIntake(False),
    )
    events, states = await _run(agent)

    assert "searching" in states
    assert len(tick.calls) == 1


@pytest.mark.asyncio
async def test_max_loops_zero_guard_falls_through_to_responding(mock_cognition):
    """5a: the max-loops guard used to set RESPONDING then `continue`, which
    re-fired the guard forever. It must fall through so RESPONDING runs."""
    import asyncio
    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=0, cognition_tick=tick,
    )
    events, states = await asyncio.wait_for(_run(agent), timeout=3)

    assert sum(1 for e in events if e.type == "response_complete") == 1
    assert sum(1 for e in events if e.type == "loop_warning") == 1
    assert len(tick.calls) == 1
    assert agent.current_state == AgentState.IDLE
    assert any(e.type == "session_ended" for e in events)


# -----------------------------------------------------------------------------
# Round 2 review: the greeting skip must be conservative. signals.py's
# greeting regex is a prefix match, so "Halbert, what does ... ?" is
# is_greeting=True *and* is_question=True and must still search.
# -----------------------------------------------------------------------------

def _real_intake():
    from halbert_core.intake.budget import get_context_budget
    from halbert_core.intake.complexity import ComplexityRouter
    from halbert_core.intake.pipeline import IntakePipeline

    # Greeting-flagged messages take ComplexityRouter's no-LLM fast path, so
    # the LLM caller is never hit; stub it defensively anyway.
    router = ComplexityRouter(lambda *a, **k: {"response": "3"}, "guide", "http://x")
    return IntakePipeline(router, get_context_budget, {})


def _real_signals_agent(tick):
    return AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick, intake_pipeline=_real_intake(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "Halbert, what does PermitRootLogin accept in sshd_config?",
    "hi, how do I fix my sshd config on this host?",
    "hello, my nginx service failed",
    "hey halbert, is my disk full?",
])
async def test_greeting_prefixed_real_question_still_searches(mock_cognition, query):
    from halbert_core.intake.signals import analyze_message

    sig = analyze_message(query)
    assert sig.is_greeting is True, "precondition: prefix regex flags it as greeting"

    tick = _RecordingTick()
    agent = _real_signals_agent(tick)
    events, states = await _run(agent, query=query)

    assert agent.ctx.intake.is_greeting is True
    assert "searching" in states
    assert len(tick.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "hi",
    "hey halbert",
    "good morning!",
    "hello, what can you do?",   # capabilities question, <= 6 words, no host context
])
async def test_pure_greeting_skips_searching(mock_cognition, query):
    tick = _RecordingTick()
    agent = _real_signals_agent(tick)
    events, states = await _run(agent, query=query)

    assert "searching" not in states
    assert states == ["planning", "reflecting", "responding", "idle"]
    assert len(tick.calls) == 1


@pytest.mark.asyncio
async def test_greeting_question_over_word_limit_searches(mock_cognition):
    """Other side of the capabilities rule: a greeting-flagged question longer
    than 6 words goes through SEARCHING even with no host domain detected."""
    from halbert_core.intake.signals import analyze_message

    query = "hello, what can you actually help me with?"
    sig = analyze_message(query)
    assert sig.is_greeting and sig.is_question and not sig.detected_domains

    tick = _RecordingTick()
    agent = _real_signals_agent(tick)
    events, states = await _run(agent, query=query)
    assert "searching" in states


@pytest.mark.asyncio
async def test_stub_intake_greeting_and_question_still_searches(mock_cognition):
    """Stub reproducing is_greeting=True, is_question=True on a long query."""
    class _Stub:
        def analyze(self, text):
            return MagicMock(
                intent="greeting", is_greeting=True, is_question=True,
                is_farewell=False, is_troubleshooting=False,
                has_error_indicators=False, detected_domains=[],
                needs_retrieval=False, complexity_score=0.1,
                recommended_model="fast", context_budget=500,
            )

    tick = _RecordingTick()
    agent = AgentStateMachine(
        llm_client=_mk_llm(), rag_service=_Rag([]), crag_evaluator=None,
        max_loops=5, cognition_tick=tick, intake_pipeline=_Stub(),
    )
    events, states = await _run(
        agent, query="Halbert, what does PermitRootLogin accept in sshd_config?"
    )
    assert "searching" in states
