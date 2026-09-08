# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C4 — the turn-event tee (D-4 design §6, the C4 row).

Today a turn's events reach exactly one HTTP response — the SSE of
whoever posted it. Everything else that should be able to *see* a turn
(the voice HUD reflecting a dashboard turn, a second screen in the room,
the future terminal client) cannot. The tee is the thin fix: one
process-wide hub the state machine publishes a REDUCED event set to
(state transitions, statuses, terminal-block markers, tool-call
markers, the verdict events) — never the token stream — and observe-only
subscribers receive.

Three hard rules from the design, all pinned here:

  * **Through the echo-guard seam**: every string field in a tee payload
    passes the packet-05 display-redact seam (the echo guard scan +
    variant registry redaction — the same two calls
    ``_echo_guard_egress`` makes) before fan-out, so a subscriber in the
    room sees only what the answer stream was cleared to show.
  * **Observe-only**: subscribing confers no steer/stop rights — the tee
    exposes no verb, no queue, no slot; the busy verbs stay behind the
    channel declarations (C3).
  * **Reduced**: no payload carries turn content — no tokens, no
    response text, no tool args. The full turn stream stays behind a
    future opt-in (design §8 Q4; not built here — the reduced set is the
    recommendation the design ships).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.tools import ToolExecutor, ToolSafetyFramework


def _tee():
    from halbert_core.agents.turn_event_tee import get_turn_event_tee
    tee = get_turn_event_tee()
    tee.reset()
    return tee


def _collecting_agent():
    llm = AsyncMock()
    llm.chat = AsyncMock(return_value=MagicMock(
        content="Test response", tool_calls=None, plan=None,
    ))
    llm.stream = AsyncMock()
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=1,
    )


async def _run_turn(agent, **process_kwargs):
    events = []
    stream = agent.process(query="hello", session_id="s-tee", **process_kwargs)
    try:
        async for event in stream:
            events.append(event)
    finally:
        await stream.aclose()
    return events


# ---------------------------------------------------------------------------
# The hub: subscribe, publish, unsubscribe — observe-only
# ---------------------------------------------------------------------------

class TestTheTeeHub:

    def test_a_subscriber_receives_what_was_published(self):
        tee = _tee()
        seen = []
        unsub = tee.subscribe(seen.append)
        tee.publish({"event": "state_change", "from": "planning", "to": "searching"})
        unsub()
        assert seen == [{"event": "state_change", "from": "planning", "to": "searching"}]

    def test_unsubscribe_stops_delivery(self):
        tee = _tee()
        seen = []
        unsub = tee.subscribe(seen.append)
        unsub()
        tee.publish({"event": "state_change"})
        assert seen == []

    def test_every_subscriber_receives_the_payload(self):
        tee = _tee()
        a, b = [], []
        tee.subscribe(a.append)
        tee.subscribe(b.append)
        tee.publish({"event": "conversation_status", "status": "in_progress"})
        assert a == b == [{"event": "conversation_status", "status": "in_progress"}]

    def test_a_failing_subscriber_never_breaks_the_turn(self):
        """Observe-only, both directions: a subscriber that raises must
        never cost the turn anything — the exception is swallowed and the
        other subscribers still receive the payload."""
        tee = _tee()
        def broken(_payload):
            raise RuntimeError("subscriber exploded")
        ok = []
        tee.subscribe(broken)
        tee.subscribe(ok.append)
        tee.publish({"event": "state_change"})
        assert ok == [{"event": "state_change"}]

    def test_the_tee_exposes_no_verb(self):
        """The observe-only rule, as a surface pin: the hub has no
        request_stop/request_steer/queue method — subscribing confers
        nothing that acts on a turn."""
        tee = _tee()
        for verb in ("request_stop", "request_steer", "stop", "steer", "queue", "publish_steer"):
            assert not hasattr(tee, verb), f"the tee grew a {verb} verb"

    def test_the_tee_redacts_payload_text_through_the_echo_guard_seam(self):
        """The design's first hard rule: payload strings pass the
        packet-05 display-redact seam (echo guard scan + registry
        redaction) before fan-out. With sensitive material noted in the
        global echo guard, a payload string reproducing it is redacted —
        the subscriber never sees the verbatim material."""
        tee = _tee()
        from halbert_core.security import echo_guard as echo_guard_mod
        from halbert_core.ingestion.redaction_registry import (
            get_global_registry,
        )
        guard = echo_guard_mod.get_global_echo_guard()
        registry = get_global_registry()
        secret_material = (
            "SUPERSECRET-OPEN-SESAME-KEY-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789-0123456789"
        )  # > the guard's 80-char window, so its full windows are the
        # registered chunks find_match recognizes inside a longer payload
        try:
            # The seam's production pairing: the guard holds the window,
            # the registry the value to redact (noted at the egress site).
            guard.note_injected(secret_material, session="tee-test")
            registry.register(secret_material)
            seen = []
            tee.subscribe(seen.append)
            tee.publish({
                "event": "state_change",
                "detail": f"the key was {secret_material}",
            })
            assert seen, "the payload never reached the subscriber"
            assert secret_material not in seen[0]["detail"], (
                "the tee fanned out a payload string that had not passed "
                "the echo-guard seam"
            )
        finally:
            guard.clear_session(session="tee-test")

    def test_publish_without_subscribers_is_a_no_op(self):
        tee = _tee()
        tee.publish({"event": "state_change"})  # must not raise


# ---------------------------------------------------------------------------
# The state machine publishes the reduced set
# ---------------------------------------------------------------------------

class TestTheStateMachinePublishes:

    @pytest.mark.asyncio
    async def test_a_turn_publishes_state_changes_and_lifecycle(self):
        """The reduced set reaches subscribers: a running turn publishes
        its turn lifecycle (turn_started/turn_ended) and its state
        transitions — without any response content."""
        tee = _tee()
        agent = _collecting_agent()
        seen = []
        unsub = tee.subscribe(seen.append)
        try:
            await _run_turn(agent)
        finally:
            unsub()
        kinds = [p["event"] for p in seen]
        assert "turn_started" in kinds
        assert "state_change" in kinds
        assert "turn_ended" in kinds
        # No payload carries the answer text (reduced, not the stream).
        assert "response_chunk" not in kinds
        assert "response_complete" not in kinds

    @pytest.mark.asyncio
    async def test_the_payload_carries_the_turn_and_channel_not_the_content(self):
        """Payload shape: the event name, the turn's session id, and the
        channel it arrived on (the voice HUD's "is this MY turn or a
        dashboard turn" question) — statuses and ids only, never query or
        answer text."""
        tee = _tee()
        agent = _collecting_agent()
        seen = []
        unsub = tee.subscribe(seen.append)
        try:
            await _run_turn(agent, modality="voice")
        finally:
            unsub()
        started = next(p for p in seen if p["event"] == "turn_started")
        assert started["session_id"] == "s-tee"
        assert started["channel"] == "voice"
        transition = next(p for p in seen if p["event"] == "state_change")
        assert set(transition) >= {"event", "session_id", "from", "to"}
        # Nothing anywhere carries the turn's words.
        for payload in seen:
            assert "hello" not in str(payload)

    @pytest.mark.asyncio
    async def test_a_verdict_publishes_to_the_tee(self):
        """The verdict events (C3's rendered truth) reach subscribers too:
        a steer accepted mid-turn is observable on the tee."""
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        tee = _tee()
        agent = _collecting_agent()

        async def slow_chat(messages, tools=None, **kwargs):
            await asyncio.sleep(0.15)
            return LLMResponse(content="done", tool_calls=[], plan=[])

        agent.llm.chat = AsyncMock(side_effect=slow_chat)
        seen = []
        unsub = tee.subscribe(seen.append)
        task = asyncio.ensure_future(_collect(agent.process("hello", session_id="s-verdict")))
        try:
            await asyncio.sleep(0.05)
            agent.handle_midturn_arrival(
                "arr-1", "also check the logs", channel=DASHBOARD_CHANNEL,
            )
            await asyncio.wait_for(task, timeout=10)
        finally:
            unsub()
        kinds = [p["event"] for p in seen]
        assert "steer_accepted" in kinds


async def _collect(stream):
    return [e async for e in stream]


# ---------------------------------------------------------------------------
# The WS bridge: the first consumer's wire (app-side)
# ---------------------------------------------------------------------------

class TestTheDashboardBridge:

    def test_app_subscribes_a_bridge_to_the_tee(self):
        """The first consumer wiring: app.py subscribes a bridge that
        re-broadcasts tee payloads on the dashboard's /ws fan-out as
        {'type': 'turn_event', 'data': ...} — the voice HUD (and any
        second screen) reads turns off the same authenticated WS the
        system status already rides."""
        from pathlib import Path
        import halbert_core
        app_py = (
            Path(halbert_core.__file__).parent / "dashboard" / "app.py"
        )
        src = app_py.read_text()
        assert "turn_event" in src, (
            "app.py does not bridge the tee onto the /ws fan-out"
        )
        assert "get_turn_event_tee" in src, (
            "app.py does not subscribe to the turn-event tee"
        )