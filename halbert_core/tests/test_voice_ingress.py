# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 A1: typed voice turn ingress.

A voice turn must arrive as a VOICE turn with its speaker claim — never as
a defaulted-admin text turn. OpenClaw lesson: one typed ingress, no
implicit side channel that silently drops identity. The dashboard relay
(VM-STT) hands the browser a transcript that already carries the
identified speaker; before this, the HTTP turn dropped both the modality
and the identity and ``process()`` defaulted ``speaker_role`` to "admin" —
so RoleGate treated every spoken command as the owner's.

Two levels are pinned:

  * the route threads the new optional request fields into ``process()``;
  * ``process()`` records them on the turn context, and the defaulting
    rule holds: explicit role wins, text defaults to "admin" (unchanged
    behavior), voice with no role defaults to "unknown" — never admin.

Plus the regression pin: ``_relay_voice_turn`` stays the single production
setter of ``on_voice_turn`` and its broadcast shape is the frontend
contract.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import re
from fastapi import FastAPI
from fastapi.testclient import TestClient

import halbert_core.dashboard.routes.agent as agent_routes
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.tools.safety import ToolSafetyFramework
from halbert_core.tools.executor import ToolExecutor

PKG_ROOT = Path(__file__).resolve().parents[1]  # halbert_core project dir
APP_PY = PKG_ROOT / "halbert_core" / "dashboard" / "app.py"


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
def fake_agent():
    return _FakeAgent()


@pytest.fixture
def client(monkeypatch, fake_agent):
    monkeypatch.setattr(agent_routes, "get_agent", lambda: fake_agent)
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


# -----------------------------------------------------------------------------
# Route level: the request fields reach process()
# -----------------------------------------------------------------------------

class TestRouteThreadsVoiceFields:

    def test_voice_turn_carries_modality_and_speaker(self, client, fake_agent):
        resp = client.post("/api/agent/message", json={
            "message": "what's running on the scanner",
            "modality": "voice",
            "speaker_name": "Eric",
            "speaker_role": "member",
            "claim_source": "voice_speaker_verification",
        })
        assert resp.status_code == 200
        assert len(fake_agent.calls) == 1
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] == "voice"
        assert kwargs["speaker_name"] == "Eric"
        assert kwargs["speaker_role"] == "member"
        assert kwargs["claim_source"] == "voice_speaker_verification"

    def test_text_turn_sends_no_voice_defaults(self, client, fake_agent):
        """A request without the new fields is byte-identical to today.

        The route must not invent a modality or a role: the defaults are
        process()'s to apply, so an absent field arrives as None.
        """
        resp = client.post("/api/agent/message", json={"message": "hello"})
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] is None
        assert kwargs["speaker_name"] is None
        assert kwargs["speaker_role"] is None
        assert kwargs["claim_source"] is None

    def test_unknown_speaker_role_is_threaded_not_rewritten(self, client, fake_agent):
        resp = client.post("/api/agent/message", json={
            "message": "delete everything",
            "modality": "voice",
            "speaker_role": "unknown",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["speaker_role"] == "unknown"


# -----------------------------------------------------------------------------
# State machine level: the turn context records modality + speaker claim
# -----------------------------------------------------------------------------

def _make_agent():
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


async def _ctx_after_turn_start(agent, **process_kwargs):
    """Drive process() to its first event, then close the generator.

    The StateContext is built before anything is yielded, so this is
    enough to assert what the turn recorded — without paying for a full
    mocked LLM round trip.
    """
    stream = agent.process(query="hello", session_id="s-1", **process_kwargs)
    try:
        async for _event in stream:
            break
    finally:
        await stream.aclose()
    return agent.ctx


class TestTurnContextDefaulting:

    @pytest.mark.asyncio
    async def test_voice_turn_carries_modality_and_speaker(self):
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent,
            modality="voice",
            speaker_name="Eric",
            speaker_role="member",
            claim_source="voice_speaker_verification",
        )
        assert ctx.modality == "voice"
        assert ctx.speaker_name == "Eric"
        assert ctx.speaker_role == "member"
        assert ctx.claim_source == "voice_speaker_verification"

    @pytest.mark.asyncio
    async def test_text_turn_unchanged(self):
        """Absent fields keep today's behavior exactly: text, admin."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(agent)
        assert ctx.modality == "text"
        assert ctx.speaker_role == "admin"

    @pytest.mark.asyncio
    async def test_voice_turn_with_no_role_never_becomes_admin(self):
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(agent, modality="voice")
        assert ctx.modality == "voice"
        assert ctx.speaker_role == "unknown"

    @pytest.mark.asyncio
    async def test_explicit_role_wins_on_a_voice_turn(self):
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(agent, modality="voice", speaker_role="restricted")
        assert ctx.speaker_role == "restricted"

    @pytest.mark.asyncio
    async def test_explicit_role_on_a_text_turn_is_recorded(self):
        """The typed path may name a role too; the route just does not."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(agent, modality="text", speaker_role="member")
        assert ctx.speaker_role == "member"


# -----------------------------------------------------------------------------
# Modality context: the voice turn's identified speaker rides as an
# unverified claim — never a role grant
# -----------------------------------------------------------------------------

def _engine_available() -> bool:
    try:
        import haloysius.modality.types  # noqa: F401
        return True
    except ImportError:
        return False


class TestModalityContextCarriesTheClaim:

    @pytest.mark.asyncio
    async def test_voice_claim_is_unverified_never_a_role_grant(self):
        if not _engine_available():
            pytest.skip("Haloysius modality engine not installed")
        from halbert_core.integrations.modality_wiring import build_modality_context
        ctx = build_modality_context(
            user_query="what's running",
            speaker_role="member",
            ingress_modality="voice",
            speaker_name="Eric",
        )
        assert ctx is not None
        assert ctx.speaker is not None
        assert ctx.speaker.speaker_role == "member"
        assert ctx.speaker.speaker_id == "Eric"
        # The claim, not the grant: unverified means the engine applies
        # the most restrictive policy regardless of the claimed role.
        assert ctx.speaker.verified is False

    @pytest.mark.asyncio
    async def test_text_turn_still_opts_out_of_biometrics(self):
        """Decision 51 unchanged: text turns pass speaker=None."""
        if not _engine_available():
            pytest.skip("Haloysius modality engine not installed")
        from halbert_core.integrations.modality_wiring import build_modality_context
        ctx = build_modality_context(
            user_query="hello",
            speaker_role="admin",
            ingress_modality="text",
        )
        assert ctx is not None
        assert ctx.speaker is None


# -----------------------------------------------------------------------------
# Regression pin: the relay stays the single on_voice_turn setter
# -----------------------------------------------------------------------------

class TestRelayRegressionPin:

    def _production_sources(self):
        for path in sorted((PKG_ROOT / "halbert_core").rglob("*.py")):
            if "tests" in path.parts:
                continue
            yield path

    def test_relay_is_the_single_production_on_voice_turn_setter(self):
        """Removing the relay re-creates the dead-turn defect with no
        backend test failing (the resolved VM-STT landmine), so the pin
        lives here: exactly one real assignment, in app.py. AST, not
        regex: the coordinator's class docstring shows a usage example
        (`coordinator.on_voice_turn = handle_voice_turn`) that a text scan
        would count."""
        hits = []
        for path in self._production_sources():
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "on_voice_turn"
                    ):
                        hits.append(str(path.relative_to(PKG_ROOT)))
        assert hits == ["halbert_core/dashboard/app.py"], (
            f"expected app.py's relay as the only production setter, got: {hits}"
        )

    def test_relay_broadcast_shape_is_the_frontend_contract(self):
        """The browser consumes {type, text, speaker_name, speaker_role,
        area_id}; the shape must not drift (and the claim fields already
        ride it — that is what A1 threads through)."""
        src = APP_PY.read_text()
        m = re.search(
            r"async def _relay_voice_turn.*?await ingress\.broadcast\(\{(.*?)\}\)",
            src, re.DOTALL,
        )
        assert m, "_relay_voice_turn broadcast not found in app.py"
        keys = re.findall(r'"(\w+)":', m.group(1))
        assert keys == ["type", "text", "speaker_name", "speaker_role", "area_id"]