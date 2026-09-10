# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 07 B1/B2: the dashboard surface of the interrupt algebra.

POST /api/agent/stop/{session_id} is the generation-claimed stop (a stop
that loses the race to a finishing turn declines), and /api/agent/message
routes an arrival that lands while a turn is in flight through
decide_midturn instead of queueing it as a whole second turn: the arrival's
own stream always carries its verdict (steer_accepted, or the stop
outcome), so no mid-turn arrival is ever silently dropped."""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState, StateContext
import halbert_core.dashboard.routes.agent as agent_routes


class _NoTurnLLM:
    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "done"


def _sse_types(body: str):
    return [
        json.loads(line[6:])["type"]
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _client(monkeypatch, agent):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    monkeypatch.setattr(agent_routes, "_agent_instance", agent)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _busy_agent(state=AgentState.PLANNING):
    """A real machine with a hand-held lock slot, standing in for the
    running turn. ``_locked`` is set directly because the test thread has
    no event loop to acquire on; ``_turn_in_flight`` only ever reads it.
    The start stamp stands in for the one process() takes under the lock."""
    agent = AgentStateMachine(llm_client=_NoTurnLLM())
    agent.current_state = state
    agent.ctx = StateContext(session_id="run", request_id="r", user_query="q")
    agent.active_sessions["run"] = agent.ctx
    agent._turn_lock = asyncio.Lock()
    agent._turn_lock._locked = True  # white-box: "a turn holds the lock"
    agent._turn_generation = agent.turn_activity.stamp()
    return agent


class TestStopRoute:
    def test_a_paused_session_stops_through_the_teardown(self, monkeypatch):
        agent = AgentStateMachine(llm_client=_NoTurnLLM())
        agent.active_sessions["s"] = StateContext(
            session_id="s", request_id="r", user_query="q"
        )
        api = _client(monkeypatch, agent)
        body = api.post("/api/agent/stop/s").json()
        assert body == {"stopped": True, "outcome": "stopped", "session_id": "s"}
        assert "s" not in agent.active_sessions

    def test_an_unknown_session_declines_instead_of_404(self, monkeypatch):
        agent = AgentStateMachine(llm_client=_NoTurnLLM())
        api = _client(monkeypatch, agent)
        r = api.post("/api/agent/stop/nobody")
        assert r.status_code == 200
        assert r.json()["stopped"] is False
        assert r.json()["outcome"] == "turn completed, stop declined"

    def test_a_running_turn_stops_by_generation_claim(self, monkeypatch):
        agent = _busy_agent()
        api = _client(monkeypatch, agent)
        body = api.post("/api/agent/stop/run").json()
        assert body["stopped"] is True
        assert agent.cancelled["run"] is True

    def test_a_stop_after_the_generation_was_claimed_declines(self, monkeypatch):
        agent = _busy_agent()
        assert agent.request_stop("run") == "stopped"
        api = _client(monkeypatch, agent)
        # The claim is single-shot: the second stop observes the flag the
        # first raised and reports the same truth ("the turn is stopping"),
        # without firing anything twice.
        assert api.post("/api/agent/stop/run").json()["stopped"] is True


class TestMidturnArrivals:
    def test_text_while_busy_steers_instead_of_queueing_a_turn(self, monkeypatch):
        agent = _busy_agent()
        api = _client(monkeypatch, agent)
        r = api.post("/api/agent/message", json={"message": "also check the logs"})
        assert r.status_code == 200
        assert _sse_types(r.text) == ["steer_accepted"]
        # The text rode the single replace-not-grow slot for the RUNNING
        # turn's session, not the arrival's own id.
        assert agent._pending_steer == {"run": ["also check the logs"]}

    def test_a_second_arrival_replaces_the_slot(self, monkeypatch):
        agent = _busy_agent()
        api = _client(monkeypatch, agent)
        api.post("/api/agent/message", json={"message": "first"})
        r = api.post("/api/agent/message", json={"message": "second"})
        events = [
            json.loads(line[6:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        assert events[0]["type"] == "steer_accepted"
        assert events[0]["replaced"] is True
        # A07-G6: steers concatenate -- the second no longer erases the first.
        assert agent._pending_steer == {"run": ["first", "second"]}

    def test_stop_while_busy_cancels_with_existing_event_vocabulary(self, monkeypatch):
        agent = _busy_agent()
        api = _client(monkeypatch, agent)
        r = api.post("/api/agent/message", json={"message": "/stop"})
        assert _sse_types(r.text) == ["cancelled", "session_ended"]
        assert agent.cancelled["run"] is True

    def test_stop_while_a_tool_batch_is_in_flight_still_stops(self, monkeypatch):
        """R-01 Phase B (A07-G2): Rule 1 is unconditional.

        This used to assert the opposite -- that ``/stop`` during a tool
        batch demoted to a steer. The demotion rule ("never kill a tool
        to deliver guidance") belongs to plain text, which steers anyway;
        applied to the stop verb it meant the user could not stop a
        running command with the verb named stop.
        """
        agent = _busy_agent(state=AgentState.READING)
        api = _client(monkeypatch, agent)
        r = api.post("/api/agent/message", json={"message": "/stop"})
        types = _sse_types(r.text)
        assert "cancelled" in types
        assert agent._pending_steer == {}
        assert agent.cancelled.get("run") is True

    def test_guidance_while_a_tool_batch_is_in_flight_steers(self, monkeypatch):
        """The rule the demotion was always about, kept."""
        agent = _busy_agent(state=AgentState.READING)
        api = _client(monkeypatch, agent)
        r = api.post(
            "/api/agent/message", json={"message": "actually check the logs"}
        )
        events = [
            json.loads(line[6:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        assert events[0]["type"] == "steer_accepted"
        assert agent._pending_steer == {"run": ["actually check the logs"]}
        assert agent.cancelled == {}      # the tool was never killed

    def test_an_arrival_with_images_keeps_the_queue_a_turn_path(self, monkeypatch):
        # Images ride the per-turn context; there is no mid-turn seam for
        # them yet, so they are not steered — the arrival falls through to
        # an ordinary (queued) turn.
        agent = _busy_agent()
        api = _client(monkeypatch, agent)
        agent._turn_lock._locked = False   # let the queued turn actually run
        r = api.post("/api/agent/message", json={"message": "look at this", "images": ["x"]})
        types = _sse_types(r.text)
        assert "steer_accepted" not in types
        assert "session_started" in types
        assert agent._pending_steer == {}