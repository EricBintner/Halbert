# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C3 — busy-mode unification (D-4 design §4, the C3 row).

PACKET-07's Phase C record, made to hold: busy behavior is a **capability
of the channel**, declared per channel (``ChannelDeclaration.busy_verbs``
— dashboard ``{stop, steer}``, voice ``{steer}``, terminal
``{queue, steer}``), and enforced in ``handle_midturn_arrival``: a verb
the arrival's channel does not declare degrades — stop→steer — so a
spoken or terminal ``/stop`` while a turn runs steers into it instead of
claiming the generation. The dashboard's own ``/stop`` is unchanged.

The honest-queue half: a whole turn that queues on the state machine's
turn lock mints a ``turn_queued`` event, so the lock wait is an
observable, honest state ("this turn is queued behind the running one"),
not just a "waiting" badge. The dashboard's image arrivals are the
declared whole-turn-queue case (no mid-turn seam for images yet); the
terminal channel declares queue first-class.

REDIRECT stays dormant — no channel declares it.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import halbert_core.dashboard.routes.agent as agent_routes
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.steering import Verdict
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.persona.claims import ClaimStrength, IdentifierClaim


class _SlowLLM:
    """Answers directly but sleeps, so an arrival can land mid-turn."""

    def __init__(self, delay=0.15):
        self.delay = delay

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(self.delay)
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        for _chunk in ("done",):
            await asyncio.sleep(self.delay)
            yield _chunk


def _agent(llm=None, **kw):
    return AgentStateMachine(
        llm_client=llm or _SlowLLM(),
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=5,
        **kw,
    )


async def _collect(stream):
    return [e async for e in stream]


def _owner_voice():
    """An identified owner speaking: the stamped identity the talk door
    derives from a redeemed relay receipt.

    R-01 Phase A added a role-floor gate ahead of the verb rules: an
    arrival stamped below the running turn's floor is REFUSED before any
    busy-verb question is asked. The degradation these tests pin is a
    property of the *channel*, not of the speaker, so they hand over an
    owner-class identity and keep testing the verb table.
    """
    return {
        "speaker_role": "admin",
        "identifier_claim": IdentifierClaim(
            kind="speaker", strength=ClaimStrength.ASSERTED
        ),
    }



# ---------------------------------------------------------------------------
# busy_verbs enforced in handle_midturn_arrival: stop→steer degradation
# ---------------------------------------------------------------------------

class TestBusyVerbsAreEnforced:

    @pytest.mark.asyncio
    async def test_dashboard_stop_while_busy_still_claims_the_generation(self):
        """The dashboard declares stop: a typed ``/stop`` while a turn
        runs claims the running turn's activity generation — unchanged
        (the pre-C3 behavior, now pinned as the channel's own verb)."""
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "/stop", channel=DASHBOARD_CHANNEL,
        )
        assert decision.verb is Verdict.STOP
        assert [e.type for e in events] == ["cancelled", "session_ended"]
        assert agent.cancelled["busy"] is True
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_dashboard_text_while_busy_still_steers(self):
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "also check the logs", channel=DASHBOARD_CHANNEL,
        )
        assert decision.verb is Verdict.STEER
        assert [e.type for e in events] == ["steer_accepted"]
        assert agent._pending_steer["busy"] == ["also check the logs"]
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_voice_stop_degrades_to_steer(self):
        """The design §4 table's voice row: the voice channel declares
        {steer} — a spoken follow-up while the agent works is corrective,
        and ``/stop`` has no spoken form worth parsing. A spoken
        ``/stop`` arrival therefore degrades: the verb the channel does
        not declare is never honored as itself, and the arrival steers
        (the request_stop path is never taken)."""
        from halbert_core.agents.channels import VOICE_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "/stop", channel=VOICE_CHANNEL, **_owner_voice(),
        )
        assert decision.verb is Verdict.STEER
        assert [e.type for e in events] == ["steer_accepted"]
        # The generation was NOT claimed: no stop outcome at all.
        assert agent.cancelled == {}
        assert agent._pending_steer["busy"] == ["/stop"]
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_voice_text_while_busy_steers_as_declared(self):
        from halbert_core.agents.channels import VOICE_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "actually check the logs instead",
            channel=VOICE_CHANNEL, **_owner_voice(),
        )
        assert decision.verb is Verdict.STEER
        assert [e.type for e in events] == ["steer_accepted"]
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_terminal_stop_degrades_to_steer(self):
        """The terminal channel declares {queue, steer} — /stop stays
        unclaimed there (design §4, the C5 row's own note), so a terminal
        ``/stop`` arrival degrades to steer exactly like the voice one."""
        from halbert_core.agents.channels import TERMINAL_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "/stop", channel=TERMINAL_CHANNEL, **_owner_voice(),
        )
        assert decision.verb is Verdict.STEER
        assert [e.type for e in events] == ["steer_accepted"]
        assert agent.cancelled == {}
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_no_channel_defaults_to_the_dashboard_verbs(self):
        """Back-compat pin: callers that pass no channel (the Wyoming
        seam and any embedder predating the channel layer) keep exactly
        today's behavior — the dashboard's verb set, stop included."""
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival("arr-1", "/stop")
        assert decision.verb is Verdict.STOP
        assert [e.type for e in events] == ["cancelled", "session_ended"]
        await asyncio.wait_for(task, timeout=5)

    @pytest.mark.asyncio
    async def test_degraded_stop_is_observable_as_a_steer_event(self):
        """The degrade is honest, not silent: the arrival's own stream
        answers steer_accepted (the same never-silently-dropped invariant
        as B2), and the steer slot carries the spoken text."""
        from halbert_core.agents.channels import VOICE_CHANNEL
        agent = _agent()
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="busy")))
        await asyncio.sleep(0.03)

        decision, events = agent.handle_midturn_arrival(
            "arr-1", "/stop", channel=VOICE_CHANNEL, **_owner_voice(),
        )
        assert events[0].type == "steer_accepted"
        assert events[0].data["replaced"] is False
        assert events[0].data["demoted"] is False
        await asyncio.wait_for(task, timeout=5)


# ---------------------------------------------------------------------------
# The route seam: the arrival's resolved channel reaches the algebra
# ---------------------------------------------------------------------------

class _RecordingAgent:
    """Fake agent that records the midturn call's channel argument."""

    def __init__(self):
        self.midturn_calls = []
        self.process_calls = []

    def handle_midturn_arrival(
        self, session_id, text, channel=None,
        speaker_role=None, identifier_claim=None,
    ):
        self.midturn_calls.append((session_id, text, channel))
        from halbert_core.agents.steering import decide_midturn
        return decide_midturn(turn_active=False, is_command=False, text=text), None

    def process(self, **kwargs):
        self.process_calls.append(kwargs)

        async def gen():
            yield StreamEvent(type="response_complete", session_id=kwargs.get("session_id", ""))

        return gen()


@pytest.fixture
def recording_agent():
    return _RecordingAgent()


@pytest.fixture
def client(monkeypatch, recording_agent):
    monkeypatch.setattr(agent_routes, "get_agent", lambda: recording_agent)
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


class TestTheRoutePassesTheResolvedChannel:

    def test_a_voice_arrival_reaches_the_algebra_with_the_voice_channel(self, client, recording_agent):
        """The route resolves the arrival's channel from its modality and
        hands it to handle_midturn_arrival — the voice arrival is governed
        by the voice channel's verbs, not the dashboard's."""
        from halbert_core.agents.channels import VOICE_CHANNEL
        resp = client.post("/api/agent/message", json={
            "message": "stop that", "modality": "voice",
        })
        assert resp.status_code == 200
        assert len(recording_agent.midturn_calls) == 1
        _sid, text, channel = recording_agent.midturn_calls[0]
        assert text == "stop that"
        assert channel is VOICE_CHANNEL

    def test_a_typed_arrival_reaches_the_algebra_with_the_dashboard_channel(self, client, recording_agent):
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        resp = client.post("/api/agent/message", json={
            "message": "also check the logs",
        })
        assert resp.status_code == 200
        _sid, _text, channel = recording_agent.midturn_calls[0]
        assert channel is DASHBOARD_CHANNEL

    def test_a_terminal_arrival_reaches_the_algebra_with_the_terminal_channel(self, client, recording_agent):
        from halbert_core.agents.channels import TERMINAL_CHANNEL
        resp = client.post("/api/agent/message", json={
            "message": "status of the tank", "modality": "terminal",
        })
        assert resp.status_code == 200
        _sid, _text, channel = recording_agent.midturn_calls[0]
        assert channel is TERMINAL_CHANNEL

    def test_an_image_arrival_skips_the_algebra_entirely(self, client, recording_agent):
        """Images have no mid-turn seam (the design §4 table's dashboard
        row): the arrival runs as a whole turn and queues on the lock —
        no channel is passed because no verb is consulted."""
        resp = client.post("/api/agent/message", json={
            "message": "what is this", "images": ["aGVsbG8="],
        })
        assert resp.status_code == 200
        assert recording_agent.midturn_calls == []
        assert len(recording_agent.process_calls) == 1


# ---------------------------------------------------------------------------
# turn_queued: the honest event for the lock wait
# ---------------------------------------------------------------------------

class TestTurnQueuedEvent:

    def test_the_event_factory_exists_with_the_queued_shape(self):
        event = StreamEvent.turn_queued("s-1", waiting_for="previous turn")
        assert event.type == "turn_queued"
        assert event.session_id == "s-1"
        assert event.data["waiting_for"] == "previous turn"

    @pytest.mark.asyncio
    async def test_a_turn_that_blocks_on_the_lock_mints_turn_queued(self):
        """The design's honest addition: a whole-turn arrival that waits
        for the running turn tells the client so with a dedicated event —
        not just the generic waiting badge."""
        agent = _agent(_SlowLLM(delay=0.2))
        first = asyncio.ensure_future(_collect(agent.process("hello", session_id="first")))
        await asyncio.sleep(0.05)

        second = asyncio.ensure_future(_collect(agent.process("second", session_id="second")))
        events = await asyncio.wait_for(second, timeout=10)
        types = [e.type for e in events]
        assert "turn_queued" in types
        # The waiting badge still rides (existing consumers unchanged);
        # turn_queued is the honest addition, not a replacement.
        assert "conversation_status" in types
        queued = next(e for e in events if e.type == "turn_queued")
        assert queued.data["waiting_for"] == "previous turn"
        assert queued.session_id == "second"
        await asyncio.wait_for(first, timeout=10)

    @pytest.mark.asyncio
    async def test_an_uncontended_turn_mints_no_turn_queued(self):
        agent = _agent(_SlowLLM(delay=0.0))
        events = await _collect(agent.process("hello", session_id="solo"))
        assert "turn_queued" not in [e.type for e in events]


# ---------------------------------------------------------------------------
# The declarations this enforcement reads (the §4 table, as data)
# ---------------------------------------------------------------------------

class TestTheDeclarationsTheEnforcementReads:

    def test_no_channel_declares_redirect(self):
        """REDIRECT awaits a cancellable provider client (no channel's
        verb set contains it — the design §4's own line)."""
        from halbert_core.agents.channels import CHANNEL_REGISTRY
        for channel in CHANNEL_REGISTRY.values():
            assert "redirect" not in channel.busy_verbs

    def test_only_the_dashboard_declares_stop(self):
        from halbert_core.agents.channels import CHANNEL_REGISTRY
        declarers = [
            c.id for c in CHANNEL_REGISTRY.values() if "stop" in c.busy_verbs
        ]
        assert declarers == ["dashboard"]