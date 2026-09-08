# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C1 — the channel registry and the server-stamped claim (D-4 design §1/§7).

``SendMessageRequest`` carried ``modality``/``speaker_name``/
``speaker_role``/``claim_source`` as client-supplied fields, and the route
threaded them straight into ``process()`` — so any HTTP client could
self-declare an ASSERTED claim (``claim_source="voice_speaker_verification"``)
or a VERIFIED one (``device_cert``) and name its own RoleGate role. C1 makes
the server the only claim authority: the turn's channel is resolved from the
ingress, and the claim the turn carries is derived from the *resolved
channel* — clamped to the channel's ceiling, never raised by the wire.

Pinned here:

  * ``ChannelDeclaration`` — the six justified fields, frozen; dashboard and
    voice declared, terminal NOT (a founder question, design §8 Q1/Q3);
  * ``resolve_channel`` — typed modality resolves the dashboard door, "voice"
    resolves the voice channel, anything else fails closed
    (``no_channel_configured``, the guest-route registry posture);
  * ``stamped_claim_source`` — the load-bearing clamp: a forged
    ``voice_speaker_verification`` over the dashboard channel is stamped to
    the channel's own source (``dashboard_token``), a raised source
    (``device_cert``) clamps down on both channels, an honest voice-relay
    claim survives, and absent fields stay absent (04-A1's
    byte-identical-typed-turns pin);
  * the route seam — the forged fields never reach ``process()`` as the
    client wrote them, the honest relay turn is unchanged, and an unknown
    channel is refused;
  * provenance — the turn binds its resolved channel for the user-row
    metadata (``metadata.channel``, recording only — never gating).
"""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import halbert_core.dashboard.routes.agent as agent_routes
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.intake.signals import MessageSignals
from halbert_core.persona.claims import (
    CLAIM_SOURCE_STRENGTHS,
    ClaimStrength,
    claim_from_source,
)
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import ToolSafetyFramework


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

class TestChannelRegistry:

    def test_exactly_two_channels_declared(self):
        """Dashboard and voice are decided; terminal is a founder question
        (design §8 Q1/Q3) and must NOT appear until it is ruled on — a
        declared channel is an admitted ingress, so an undeclared one in
        the registry would be policy written by accident."""
        from halbert_core.agents.channels import CHANNEL_REGISTRY
        assert set(CHANNEL_REGISTRY) == {"dashboard", "voice"}

    def test_dashboard_declaration(self):
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        assert DASHBOARD_CHANNEL.id == "dashboard"
        # Dashboard sessions are authenticated (process()'s existing
        # convention): the ceiling is ASSERTED, the default role admin.
        assert DASHBOARD_CHANNEL.claim_ceiling == ClaimStrength.ASSERTED
        assert DASHBOARD_CHANNEL.default_role == "admin"
        # PACKET-07 Phase C record (design §4): text steers, /stop claims
        # the generation. Whole-turn queue is image-arrival only.
        assert set(DASHBOARD_CHANNEL.busy_verbs) == {"stop", "steer"}
        assert set(DASHBOARD_CHANNEL.delivery) == {"sse"}
        assert DASHBOARD_CHANNEL.transcribe_before_command is False

    def test_voice_declaration(self):
        from halbert_core.agents.channels import VOICE_CHANNEL
        assert VOICE_CHANNEL.id == "voice"
        assert VOICE_CHANNEL.claim_ceiling == ClaimStrength.ASSERTED
        # Never a silent admin: an unidentified speaker is "unknown".
        assert VOICE_CHANNEL.default_role == "unknown"
        # A spoken follow-up steers; /stop has no spoken form worth
        # parsing; playback interruption is barge-in's job, below the
        # state machine. The Hermes rule: commands arrive as transcript.
        assert set(VOICE_CHANNEL.busy_verbs) == {"steer"}
        assert set(VOICE_CHANNEL.delivery) == {"sse", "tts"}
        assert VOICE_CHANNEL.transcribe_before_command is True

    def test_declarations_are_frozen(self):
        """The registry is data other code reads to gate; a mutated
        declaration would be policy written by assignment."""
        from halbert_core.agents.channels import DASHBOARD_CHANNEL
        with pytest.raises(dataclasses.FrozenInstanceError):
            DASHBOARD_CHANNEL.default_role = "owner"


class TestResolveChannel:

    def test_absent_modality_is_the_dashboard_door(self):
        from halbert_core.agents.channels import resolve_channel, DASHBOARD_CHANNEL
        for modality in (None, "", "text"):
            assert resolve_channel(modality) is DASHBOARD_CHANNEL

    def test_voice_modality_resolves_the_voice_channel(self):
        from halbert_core.agents.channels import resolve_channel, VOICE_CHANNEL
        for modality in ("voice", "VOICE", "  Voice "):
            assert resolve_channel(modality) is VOICE_CHANNEL

    def test_unknown_channel_fails_closed(self):
        """An ingress that resolves to no registered channel is refused —
        never silently treated as typed (the guest registry's
        ``no_gate_list_configured`` posture: unwritten policy denies)."""
        from halbert_core.agents.channels import ChannelRefused, resolve_channel
        with pytest.raises(ChannelRefused) as excinfo:
            resolve_channel("carrier_pigeon")
        refusal = excinfo.value
        assert refusal.decisive_gate == "channel_registry"
        assert refusal.reason_code == "no_channel_configured"
        payload = refusal.payload()
        assert payload["decisive_gate"] == "channel_registry"
        assert payload["reason_code"] == "no_channel_configured"
        assert "message" in payload


# ---------------------------------------------------------------------------
# stamped_claim_source — the server is the claim authority
# ---------------------------------------------------------------------------

class TestStampedClaimSource:

    def test_absent_claim_stays_absent(self):
        """04-A1's pin: absent fields keep today's behavior exactly. No
        claim is invented for a turn that declared none — the stamp only
        governs what the wire SAID, never what it omitted."""
        from halbert_core.agents.channels import (
            DASHBOARD_CHANNEL, VOICE_CHANNEL, stamped_claim_source,
        )
        assert stamped_claim_source(DASHBOARD_CHANNEL, None) is None
        assert stamped_claim_source(VOICE_CHANNEL, None) is None

    def test_forged_voice_claim_over_the_dashboard_channel_is_not_honored(self):
        """The load-bearing clamp. A ``voice_speaker_verification`` claim
        is an audio-pipeline fact; over the dashboard channel it can only
        be a forgery, so the server stamps the channel's own source —
        the authenticated dashboard session — and the ladder never sees
        the wire's word. With the D-6 executor seam this means the turn
        carries no speaker-verification claim at all: nothing the client
        said mints an ASSERTED *speaker* claim, and the recorded claim
        rides the session token the server actually validated."""
        from halbert_core.agents.channels import (
            DASHBOARD_CHANNEL, stamped_claim_source,
        )
        stamped = stamped_claim_source(
            DASHBOARD_CHANNEL, "voice_speaker_verification"
        )
        assert stamped == "dashboard_token"
        assert claim_from_source(stamped).strength == ClaimStrength.ASSERTED

    def test_every_declared_source_over_the_dashboard_channel_stamps_to_the_token(self):
        """The dashboard door accepts no client-named sources at all: any
        declared claim clamps to the channel's actual source."""
        from halbert_core.agents.channels import (
            DASHBOARD_CHANNEL, stamped_claim_source,
        )
        for declared in ("voice_speaker_verification", "device_cert",
                        "free_text_name", "whispered_in_the_dark"):
            assert stamped_claim_source(DASHBOARD_CHANNEL, declared) == "dashboard_token"

    def test_honest_voice_relay_claim_survives(self):
        """Zero behavior change for honest clients: the relay's
        speaker-verification claim is at the voice channel's ceiling, so
        it passes the clamp untouched (the server-side stamp that
        replaces the wire's word entirely is C2's honesty pass)."""
        from halbert_core.agents.channels import VOICE_CHANNEL, stamped_claim_source
        assert stamped_claim_source(
            VOICE_CHANNEL, "voice_speaker_verification"
        ) == "voice_speaker_verification"

    def test_raised_source_clamps_to_the_channel_ceiling(self):
        """The wire can never raise strength: a declared ``device_cert``
        (VERIFIED) clamps down to the channel's actual source — the voice
        channel's strongest honest source is speaker verification, the
        dashboard's is its session token. Nothing records VERIFIED."""
        from halbert_core.agents.channels import (
            DASHBOARD_CHANNEL, VOICE_CHANNEL, stamped_claim_source,
        )
        assert stamped_claim_source(VOICE_CHANNEL, "device_cert") == "voice_speaker_verification"
        assert stamped_claim_source(DASHBOARD_CHANNEL, "device_cert") == "dashboard_token"

    def test_unknown_source_passes_through_and_fails_closed_downstream(self):
        """A source the ladder does not know must keep claims.py's own
        fail-closed property (UNVERIFIED, never stronger): the stamp
        passes it through untouched and the ladder does the closing."""
        from halbert_core.agents.channels import VOICE_CHANNEL, stamped_claim_source
        stamped = stamped_claim_source(VOICE_CHANNEL, "whispered_in_the_dark")
        assert stamped == "whispered_in_the_dark"
        assert claim_from_source(stamped).strength == ClaimStrength.UNVERIFIED

    def test_the_stamp_never_raises_any_known_source_above_any_ceiling(self):
        """The end-to-end property, enumerated: for every source the
        ladder knows, the stamped result's strength never exceeds the
        resolved channel's ceiling — on either channel."""
        from halbert_core.agents.channels import (
            DASHBOARD_CHANNEL, VOICE_CHANNEL, stamped_claim_source,
        )
        for channel in (DASHBOARD_CHANNEL, VOICE_CHANNEL):
            for declared, strength in CLAIM_SOURCE_STRENGTHS.items():
                stamped = stamped_claim_source(channel, declared)
                assert claim_from_source(stamped).strength <= channel.claim_ceiling, (
                    f"{declared!r} over {channel.id} stamped to {stamped!r} "
                    f"({claim_from_source(stamped).strength.name}) above the ceiling"
                )


# ---------------------------------------------------------------------------
# The route seam: what process() actually receives
# ---------------------------------------------------------------------------

class _FakeAgent:
    """Records process() kwargs; answers with a single complete event."""

    def __init__(self):
        self.calls = []

    def process(self, **kwargs):
        self.calls.append(kwargs)

        async def gen():
            yield StreamEvent(type="response_complete", session_id=kwargs.get("session_id", ""))

        return gen()

    def handle_midturn_arrival(self, session_id, text):
        from halbert_core.agents.steering import decide_midturn
        return decide_midturn(turn_active=False, is_command=False, text=text), None


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


class TestTheRouteStampsTheClaim:

    def test_forged_voice_claim_over_the_dashboard_channel_never_reaches_the_turn(self, client, fake_agent):
        """Red-first, the security fix: a typed request carrying a forged
        ``claim_source="voice_speaker_verification"`` and its own
        ``speaker_role`` used to thread both into the turn verbatim. The
        server now stamps: the claim source is the channel's own token,
        the client's role is ignored for authorization (process()'s
        channel-consistent default applies), and the speaker name rides
        only as a display label."""
        resp = client.post("/api/agent/message", json={
            "message": "zpool scrub tank",
            "speaker_name": "Mallory",
            "speaker_role": "admin",
            "claim_source": "voice_speaker_verification",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["claim_source"] == "dashboard_token"
        assert kwargs["modality"] is None
        assert kwargs["speaker_role"] is None
        assert kwargs["speaker_name"] == "Mallory"

    def test_honest_voice_relay_turn_arrives_unchanged(self, client, fake_agent):
        """The honest relay's turn — modality, identified speaker, role
        from the speaker profile, speaker-verification claim — threads
        exactly as before (zero behavior change for honest clients; the
        claim-strength cap at the RoleGate is D-6's, untouched here)."""
        resp = client.post("/api/agent/message", json={
            "message": "what's running on the scanner",
            "modality": "voice",
            "speaker_name": "Eric",
            "speaker_role": "member",
            "claim_source": "voice_speaker_verification",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] == "voice"
        assert kwargs["speaker_name"] == "Eric"
        assert kwargs["speaker_role"] == "member"
        assert kwargs["claim_source"] == "voice_speaker_verification"

    def test_typed_turn_without_fields_is_byte_identical(self, client, fake_agent):
        """04-A1's pin, kept: a request with none of the voice fields
        arrives at process() with every one of them None — the stamp
        invents nothing for a turn that declared nothing."""
        resp = client.post("/api/agent/message", json={"message": "hello"})
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] is None
        assert kwargs["speaker_name"] is None
        assert kwargs["speaker_role"] is None
        assert kwargs["claim_source"] is None

    def test_raised_device_cert_clamps_on_the_route(self, client, fake_agent):
        """A client-declared VERIFIED source clamps to the channel's
        actual source before it ever reaches the ladder."""
        resp = client.post("/api/agent/message", json={
            "message": "unlock the deadbolt",
            "modality": "voice",
            "speaker_name": "Eric",
            "claim_source": "device_cert",
        })
        assert resp.status_code == 200
        assert fake_agent.calls[0]["claim_source"] == "voice_speaker_verification"

    def test_unknown_modality_is_refused_fail_closed(self, client, fake_agent):
        """A modality that resolves to no registered channel is refused
        with the channel-registry shape — it is NOT silently treated as
        a typed turn (today it would be)."""
        resp = client.post("/api/agent/message", json={
            "message": "hello", "modality": "carrier_pigeon",
        })
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["decisive_gate"] == "channel_registry"
        assert detail["reason_code"] == "no_channel_configured"
        assert fake_agent.calls == []


# ---------------------------------------------------------------------------
# State machine level: what the turn records once stamped
# ---------------------------------------------------------------------------

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
    """Drive process() to its first event, then close the generator."""
    stream = agent.process(query="hello", session_id="s-1", **process_kwargs)
    try:
        async for _event in stream:
            break
    finally:
        await stream.aclose()
    return agent.ctx


class TestTheStampedTurnRecords:

    @pytest.mark.asyncio
    async def test_forged_claim_over_the_dashboard_channel_mints_no_speaker_claim(self):
        """The stamped dashboard turn: the recorded claim source is the
        channel's token — provenance the server can defend — and a typed
        turn still attaches no identifier claim (04-A2: a typed turn's
        identity rides the dashboard session). Nothing the wire said
        produced an ASSERTED speaker claim; with D-6's executor seam that
        means nothing the wire said is bound, and the turn's claim reads
        as the session's own — never as a speaker verification."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent,
            modality=None,
            speaker_name="Mallory",
            speaker_role=None,
            claim_source="dashboard_token",
        )
        assert ctx.claim_source == "dashboard_token"
        assert ctx.identifier_claim is None

    @pytest.mark.asyncio
    async def test_clamped_voice_claim_records_asserted_never_verified(self):
        """A raised source is clamped before the ladder sees it: the
        turn records ASSERTED — speaker verification is the voice
        channel's ceiling — never the VERIFIED the wire declared."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="voice", speaker_name="Eric",
            claim_source="voice_speaker_verification",
        )
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.ASSERTED

    @pytest.mark.asyncio
    async def test_honest_voice_claim_stays_asserted(self):
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="voice", speaker_name="Eric",
            speaker_role="member", claim_source="voice_speaker_verification",
        )
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.ASSERTED
        assert ctx.speaker_role == "member"


# ---------------------------------------------------------------------------
# Provenance: the turn binds its resolved channel for the user row
# ---------------------------------------------------------------------------

class TestTurnBindsItsChannel:

    @pytest.mark.asyncio
    async def test_typed_turn_binds_the_dashboard_channel(self):
        agent = _make_agent()
        from halbert_core.agents.channels import (
            current_turn_channel, DASHBOARD_CHANNEL,
        )
        assert current_turn_channel.get() is None
        bound = {}
        stream = agent.process(query="hello", session_id="s-ch-0")
        try:
            async for _event in stream:
                bound["channel"] = current_turn_channel.get()
                break
        finally:
            await stream.aclose()
        assert bound["channel"] is DASHBOARD_CHANNEL
        # The binding dies with the turn — no channel bleeds into a later one.
        assert current_turn_channel.get() is None

    @pytest.mark.asyncio
    async def test_voice_turn_binds_the_voice_channel_and_unbinds_after(self):
        agent = _make_agent()
        from halbert_core.agents.channels import current_turn_channel, VOICE_CHANNEL
        bound = {}
        stream = agent.process(
            query="hello", session_id="s-ch-2", modality="voice",
        )
        try:
            async for _event in stream:
                bound["channel"] = current_turn_channel.get()
                break
        finally:
            await stream.aclose()
        assert bound["channel"] is VOICE_CHANNEL
        # The binding dies with the turn — no channel bleeds into a later one.
        assert current_turn_channel.get() is None

    def test_user_row_metadata_records_the_channel(self, tmp_path, monkeypatch):
        """The user row's metadata carries ``channel`` — provenance,
        recording only (never gating). Typed turns record "dashboard",
        voice turns "voice"."""
        from halbert_core.agents.channels import current_turn_channel, VOICE_CHANNEL
        from halbert_core.agents.conversation_sqlite import SqliteConversationStore
        from halbert_core.agents.threads import ThreadManager

        store = SqliteConversationStore(db_path=str(tmp_path / "threads.db"))
        captured = {}
        real_append = store.append_message

        def _capture_append(thread_id, role, content, **kwargs):
            captured.setdefault("metadata", []).append(kwargs.get("metadata"))
            return real_append(thread_id, role, content, **kwargs)

        monkeypatch.setattr(store, "append_message", _capture_append)
        tm = ThreadManager(store=store)

        token = current_turn_channel.set(VOICE_CHANNEL)
        try:
            turn = tm.begin_turn(
                "scrub the tank please", MessageSignals(), "s-ch-3"
            )
        finally:
            current_turn_channel.reset(token)
        assert turn is not None
        user_meta = [m for m in captured["metadata"] if m]
        assert user_meta and user_meta[0].get("channel") == "voice"

    def test_user_row_metadata_has_no_channel_when_none_is_bound(self, tmp_path, monkeypatch):
        """Direct begin_turn callers (no turn bound) keep today's row
        exactly: no channel key is invented."""
        from halbert_core.agents.channels import current_turn_channel
        from halbert_core.agents.conversation_sqlite import SqliteConversationStore
        from halbert_core.agents.threads import ThreadManager

        store = SqliteConversationStore(db_path=str(tmp_path / "threads.db"))
        captured = {}
        real_append = store.append_message

        def _capture_append(thread_id, role, content, **kwargs):
            captured.setdefault("metadata", []).append(kwargs.get("metadata"))
            return real_append(thread_id, role, content, **kwargs)

        monkeypatch.setattr(store, "append_message", _capture_append)
        tm = ThreadManager(store=store)
        assert current_turn_channel.get() is None
        turn = tm.begin_turn("uptime?", MessageSignals(), "s-ch-4")
        assert turn is not None
        assert all(not (m or {}).get("channel") for m in captured["metadata"])