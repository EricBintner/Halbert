# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""TASK-07 voice-turn plumbing: speaker_role, conversation threading, turn UUID.

The Wyoming voice path is an UNAUTHENTICATED ingress compared to dashboard
chat: a transcript arriving over the satellite protocol has no verified
speaker. Two of the four TASK-07 fixes were shipped as docstring claims
only — ``_process_agent_turn`` said it passed ``speaker_role="unknown"``
and threaded ``conversation_id``, but the ``agent.process()`` call passed
neither, and ``process()`` did not accept a speaker_role at all, so every
voice turn inherited the dashboard-chat default ``"admin"`` — the RoleGate
tightening for unidentified speakers never applied.

These tests pin the real plumbing:

  1. ``agent.process(speaker_role=...)`` reaches StateContext (the field the
     tool executor reads when classifying tool risk).
  2. The Wyoming turn passes ``speaker_role="unknown"`` — never "admin".
  3. The Wyoming turn threads ``conversation_id`` as the agent ``thread_id``
     so voice turns group by HA conversation.
  4. The per-turn session UUID stays unique across consecutive turns (the
     collision fix that was already shipped).
"""
from __future__ import annotations

import pytest

import halbert_core.agents.state_machine as sm
from halbert_core.agents.events import StreamEvent
from halbert_core.integrations.wyoming_agent import HalbertWyomingAgent


class _FakeAgent:
    """Records process() kwargs; answers with a single complete event."""

    def __init__(self):
        self.calls = []

    def process(self, **kwargs):
        self.calls.append(kwargs)

        async def gen():
            yield StreamEvent(type="response_complete", session_id=kwargs.get("session_id", ""))

        return gen()


@pytest.fixture
def wyoming():
    return HalbertWyomingAgent()


@pytest.fixture
def fake_agent():
    return _FakeAgent()


class TestWyomingTurnPlumbing:
    async def test_speaker_role_is_unknown_not_admin(self, wyoming, fake_agent):
        await wyoming._process_agent_turn(fake_agent, "turn on the lights", "")
        assert fake_agent.calls, "the agent was never invoked"
        assert fake_agent.calls[0].get("speaker_role") == "unknown"

    async def test_conversation_id_threads_as_thread_id(self, wyoming, fake_agent):
        await wyoming._process_agent_turn(fake_agent, "hello", "", conversation_id="ha-conv-42")
        assert fake_agent.calls[0].get("thread_id") == "ha-conv-42"

    async def test_no_conversation_id_passes_no_thread(self, wyoming, fake_agent):
        await wyoming._process_agent_turn(fake_agent, "hello", "")
        assert not fake_agent.calls[0].get("thread_id")

    async def test_session_id_is_unique_per_turn(self, wyoming, fake_agent):
        await wyoming._process_agent_turn(fake_agent, "first turn", "")
        await wyoming._process_agent_turn(fake_agent, "second turn", "")
        first, second = (c["session_id"] for c in fake_agent.calls)
        assert first != second
        assert first.startswith("wyoming-")
        assert second.startswith("wyoming-")


class TestProcessSpeakerRolePlumbing:
    async def test_process_forwards_speaker_role_to_context(self, monkeypatch):
        """process(speaker_role=...) must reach StateContext — the field the
        tool executor reads when the RoleGate classifies tool risk."""
        agent = sm.AgentStateMachine(llm_client=None, prompt_builder=None)
        captured = {}
        real_ctx = sm.StateContext

        def factory(**kwargs):
            captured.update(kwargs)
            return real_ctx(**kwargs)

        monkeypatch.setattr(sm, "StateContext", factory)
        try:
            async for _ in agent.process("hi", speaker_role="guest"):
                pass
        except Exception:
            pass  # llm_client is None; the turn fails AFTER ctx construction
        assert captured.get("speaker_role") == "guest"

    async def test_process_defaults_to_dashboard_admin(self, monkeypatch):
        """A chat turn that passes nothing keeps the 'admin' default."""
        agent = sm.AgentStateMachine(llm_client=None, prompt_builder=None)
        captured = {}
        real_ctx = sm.StateContext

        def factory(**kwargs):
            captured.update(kwargs)
            return real_ctx(**kwargs)

        monkeypatch.setattr(sm, "StateContext", factory)
        try:
            async for _ in agent.process("hi"):
                pass
        except Exception:
            pass
        # Absent from the call means the dataclass default ("admin") applies.
        assert "speaker_role" not in captured or captured.get("speaker_role") in (None, "admin")