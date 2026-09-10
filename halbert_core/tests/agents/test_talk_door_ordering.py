# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-01 Phase A: an arrival is stamped before any verb is decided.

The #1 finding of the OSS solidity pass (A09-G1 = A07-G1 = A07 bug 3 =
A09 bug 2): ``/api/agent/message`` called ``handle_midturn_arrival`` at
``routes/agent.py:1690`` — *before* the voice relay receipt was consumed
at ``:1794`` and before the claim/role were stamped at ``:1803``. A guest
in the room with no voiceprint and no relay token could steer the
owner's running admin turn, and the receipt that should have identified
them was never spent.

The invariant these tests pin: modality, receipt, claim and role are
stamped BEFORE the verb is decided; a steer arriving below the running
turn's role floor is refused with a typed denial; an unknown modality
fails closed; and a claim that cannot be derived binds UNVERIFIED rather
than nothing at all.
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from halbert_core.agents.llm_client import LLMResponse
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.states import AgentState, StateContext
from halbert_core.agents.steering import Verdict
from halbert_core.persona.claims import ClaimStrength, IdentifierClaim
import halbert_core.dashboard.routes.agent as agent_routes


class _NoTurnLLM:
    async def chat(self, messages, tools=None, **kwargs):
        return LLMResponse(content="done", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        yield "done"


def _sse(body: str):
    return [
        json.loads(line[6:])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _client(monkeypatch, agent):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    monkeypatch.setattr(agent_routes, "_agent_instance", agent)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _busy_admin_agent(state=AgentState.EXECUTING):
    """A machine holding a running *admin* turn — the owner's typed turn."""
    agent = AgentStateMachine(llm_client=_NoTurnLLM())
    agent.current_state = state
    ctx = StateContext(session_id="run", request_id="r", user_query="q")
    ctx.speaker_role = "admin"
    ctx.modality = "text"
    ctx.identifier_claim = None
    agent.ctx = ctx
    agent.active_sessions["run"] = ctx
    agent._turn_lock = asyncio.Lock()
    agent._turn_lock._locked = True  # white-box: "a turn holds the lock"
    agent._turn_generation = agent.turn_activity.stamp()
    return agent


# ---------------------------------------------------------------------------
# A09-G1 / A07-G1: stamp before the verb
# ---------------------------------------------------------------------------

def test_midturn_voice_arrival_spends_its_relay_receipt(monkeypatch):
    """The receipt is single-use, and every path spends it.

    Before the fix the mid-turn branch returned before ``consume`` ever
    ran, so a steered utterance left its receipt pending — redeemable
    again by the next arrival (A07 bug 3, A09 bug 2).
    """
    from halbert_core.dashboard.voice_relay import get_voice_relay_receipts

    receipts = get_voice_relay_receipts()
    receipts.reset()

    class _Obs:
        text = "and delete the backups too"
        speaker_name = "Sam"
        speaker_role = "admin"
        speaker_id = "spk-1"

    token = receipts.record(_Obs())
    assert receipts.size() == 1

    agent = _busy_admin_agent()
    client = _client(monkeypatch, agent)
    client.post(
        "/api/agent/message",
        json={
            "message": "and delete the backups too",
            "session_id": "arrival",
            "modality": "voice",
            "relay_token": token,
        },
    )

    assert receipts.size() == 0, "the mid-turn path must spend the receipt"


def test_unidentified_voice_steer_into_admin_turn_is_refused(monkeypatch):
    """The headline finding: a guest in the room cannot steer the owner.

    No voiceprint, no relay token — the voice channel's own default role
    is ``unknown``, which is below the running admin turn's floor. The
    arrival is refused with a typed denial, and nothing is queued.
    """
    from halbert_core.dashboard.voice_relay import get_voice_relay_receipts

    get_voice_relay_receipts().reset()
    agent = _busy_admin_agent()
    client = _client(monkeypatch, agent)

    response = client.post(
        "/api/agent/message",
        json={
            "message": "and delete the backups too",
            "session_id": "arrival",
            "modality": "voice",
        },
    )

    events = _sse(response.text)
    types = [e["type"] for e in events]
    assert "steer_accepted" not in types
    assert "steer_refused" in types, types
    # StreamEvent.to_dict flattens ``data`` into the payload.
    refusal = next(e for e in events if e["type"] == "steer_refused")
    assert refusal["reason_code"] == "below_turn_role_floor"
    assert agent._pending_steer == {}, "a refused steer is never queued"


def test_verified_owner_voice_steer_into_admin_turn_is_accepted(monkeypatch):
    """The floor caps, it never blocks the owner.

    A relay receipt the pipeline verified against an enrolled admin
    profile stamps an ASSERTED claim and the admin role, so the steer is
    at the floor and rides the pending slot as before.
    """
    from halbert_core.dashboard.voice_relay import get_voice_relay_receipts

    receipts = get_voice_relay_receipts()
    receipts.reset()

    class _Obs:
        text = "check the disk too"
        speaker_name = "Owner"
        speaker_role = "admin"
        speaker_id = "spk-owner"

    token = receipts.record(_Obs())
    agent = _busy_admin_agent()
    client = _client(monkeypatch, agent)

    response = client.post(
        "/api/agent/message",
        json={
            "message": "check the disk too",
            "session_id": "arrival",
            "modality": "voice",
            "relay_token": token,
        },
    )

    types = [e["type"] for e in _sse(response.text)]
    assert "steer_accepted" in types, types
    assert agent._pending_steer.get("run") == "check the disk too"


def test_typed_dashboard_steer_is_unaffected(monkeypatch):
    """The 04-A1 regression pin: a typed arrival behaves exactly as before."""
    agent = _busy_admin_agent()
    client = _client(monkeypatch, agent)
    response = client.post(
        "/api/agent/message",
        json={"message": "also check the logs", "session_id": "arrival"},
    )
    types = [e["type"] for e in _sse(response.text)]
    assert "steer_accepted" in types, types
    assert agent._pending_steer.get("run") == "also check the logs"


def test_handle_midturn_arrival_takes_the_stamped_identity():
    """The machine-level contract: the caller hands over what it stamped.

    ``handle_midturn_arrival`` decides a verb, so it must be told the
    arrival's identity rather than deriving it from the wire itself.
    """
    agent = _busy_admin_agent()
    decision, events = agent.handle_midturn_arrival(
        "arrival",
        "and delete the backups too",
        channel=None,
        speaker_role="unknown",
        identifier_claim=IdentifierClaim(
            kind="speaker", strength=ClaimStrength.UNVERIFIED
        ),
    )
    assert decision.verb is Verdict.REFUSED
    assert events is not None
    assert events[0].type == "steer_refused"


# ---------------------------------------------------------------------------
# A09 bug 1: unknown modality is not a typed admin turn
# ---------------------------------------------------------------------------

def test_unknown_modality_is_refused_not_treated_as_admin_text():
    """``process(modality='mcp')`` must fail closed.

    The route already refuses an unresolvable modality through the
    channel registry; the machine silently normalised anything unknown
    to ``"text"``, which carries the dashboard channel's admin default —
    so an in-process caller passing a modality the registry never
    admitted got an admin turn (A09 bug 1).
    """
    agent = AgentStateMachine(llm_client=_NoTurnLLM())

    async def _run():
        return [e async for e in agent.process("hi", "s1", modality="mcp")]

    events = asyncio.run(_run())
    types = [e.type for e in events]
    assert "error" in types, types
    payload = next(e for e in events if e.type == "error").data
    assert payload.get("reason_code") == "no_channel_configured", payload


# ---------------------------------------------------------------------------
# A12 bug 1: the claim ladder fails closed on its own exception path
# ---------------------------------------------------------------------------

def test_claim_derivation_failure_binds_unverified(monkeypatch):
    """A derivation that raises must not leave the turn claimless.

    No claim bound means no cap: the executor's ``effective_voice_role``
    never runs and the stated role stands. Fail closed to UNVERIFIED so
    the cap still applies.
    """
    import halbert_core.persona.claims as claims_mod

    def _boom(*a, **k):
        raise RuntimeError("ladder unavailable")

    monkeypatch.setattr(claims_mod, "claim_from_source", _boom)

    agent = AgentStateMachine(llm_client=_NoTurnLLM())
    captured = {}

    async def _run():
        stream = agent.process(
            "hello", "s2", modality="voice",
            claim_source="voice_speaker_verification", speaker_name="Sam",
        )
        async for _ in stream:
            if agent.ctx is not None and "claim" not in captured:
                captured["claim"] = agent.ctx.identifier_claim

    asyncio.run(_run())
    claim = captured.get("claim")
    assert claim is not None, "a failed derivation must still bind a claim"
    assert claim.strength is ClaimStrength.UNVERIFIED
