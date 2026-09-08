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

  * ``ChannelDeclaration`` — the six justified fields, frozen; dashboard
    and voice declared since C1, terminal declared since C5 (founder
    ruling 2026-09-07: the terminal is a third talk channel, ASSERTED
    via the dashboard token — design §8 Q1's recommendation accepted,
    Q3 answered yes);
  * ``resolve_channel`` — typed modality resolves the dashboard door, "voice"
    resolves the voice channel, "terminal" resolves the terminal talk
    channel, anything else fails closed
    (``no_channel_configured``, the guest-route registry posture);
  * ``stamped_claim_source`` — the load-bearing clamp: a forged
    ``voice_speaker_verification`` over the dashboard channel is stamped to
    the channel's own source (``dashboard_token``), a raised source
    (``device_cert``) clamps down on every channel, an honest voice-relay
    claim survives, and absent fields stay absent (04-A1's
    byte-identical-typed-turns pin);
  * the route seam — the forged fields never reach ``process()`` as the
    client wrote them, the honest relay turn is unchanged, a terminal
    turn is stamped to the channel's own dashboard-token identity
    (claimed whether the wire declared a source or none), and an
    unknown channel is refused;
  * the terminal TOOL surface stays a tool surface — the terminal
    routes' request models carry no channel/claim fields, so no
    request through them can be admitted as a talk ingress;
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

    def test_exactly_three_channels_declared(self):
        """Dashboard and voice were decided in C1; the terminal was ruled
        on 2026-09-07 (founder: "the terminal becomes a third talk
        channel, ASSERTED via dashboard token" — design §8 Q1 accepted,
        Q3 yes). The registry stays closed otherwise: a declared channel
        is an admitted ingress, so anything beyond these three is
        policy written by accident."""
        from halbert_core.agents.channels import CHANNEL_REGISTRY
        assert set(CHANNEL_REGISTRY) == {"dashboard", "voice", "terminal"}

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

    def test_terminal_declaration(self):
        """C5, the founder ruling and the design's C5 row, as data: the
        ceiling is the dashboard-token ASSERTED strength (no
        ``local_console`` VERIFIED source exists — the ruling declined
        it: an OS uid is not a cryptographic device credential); the
        default role is admin (the owner's shell on the owner's
        machine, its credential the same dashboard token); busy verbs
        are queue+steer (design §4 table: a CLI user accepts whole-turn
        queuing as the first-class mode; steer rides the same slot);
        delivery is the door's own SSE (C4's event tee extends the set
        when that dispatch lands); commands are typed, never
        transcribed."""
        from halbert_core.agents.channels import TERMINAL_CHANNEL
        assert TERMINAL_CHANNEL.id == "terminal"
        assert TERMINAL_CHANNEL.claim_ceiling == ClaimStrength.ASSERTED
        assert TERMINAL_CHANNEL.default_role == "admin"
        assert set(TERMINAL_CHANNEL.busy_verbs) == {"queue", "steer"}
        assert set(TERMINAL_CHANNEL.delivery) == {"sse"}
        assert TERMINAL_CHANNEL.transcribe_before_command is False

    def test_terminal_channel_stamps_the_dashboard_token(self):
        """The ruling's identity mapping: the terminal's claim source is
        the SAME dashboard token the door validates — ASSERTED via the
        existing token, and no fourth source is invented."""
        from halbert_core.agents.channels import CHANNEL_CLAIM_STAMP
        assert CHANNEL_CLAIM_STAMP["terminal"] == "dashboard_token"
        from halbert_core.persona.claims import claim_from_source
        stamped = claim_from_source(CHANNEL_CLAIM_STAMP["terminal"])
        assert stamped.strength == ClaimStrength.ASSERTED

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

    def test_terminal_modality_resolves_the_terminal_channel(self):
        """C5: a turn typed at the machine's terminal surface resolves
        the terminal talk channel — normalized the same way the voice
        modality is, so the route and the state machine can never
        disagree about which channel a turn arrived on."""
        from halbert_core.agents.channels import resolve_channel, TERMINAL_CHANNEL
        for modality in ("terminal", "TERMINAL", "  Terminal "):
            assert resolve_channel(modality) is TERMINAL_CHANNEL

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

    def test_every_declared_source_over_the_terminal_channel_stamps_to_the_token(self):
        """C5: the terminal channel holds the dashboard door's rule — its
        identity IS the dashboard token, so nothing the wire names can
        mint a different (or stronger) claim over it. A forged speaker
        verification or a declared device cert both clamp to the one
        credential the server actually validated."""
        from halbert_core.agents.channels import (
            TERMINAL_CHANNEL, stamped_claim_source,
        )
        for declared in ("voice_speaker_verification", "device_cert",
                        "free_text_name", "local_console", "whispered_in_the_dark"):
            assert stamped_claim_source(TERMINAL_CHANNEL, declared) == "dashboard_token"

    def test_absent_claim_over_the_terminal_channel_stamps_nothing_here(self):
        """stamped_claim_source keeps its uniform contract (nothing
        declared stamps nothing); the terminal channel's unconditional
        identity is stamped at the route/process seam (the founder
        ruling made the token the channel's claim whether or not the
        wire declared a source). Pinned here so the seam stamp never
        silently moves into the generic clamp."""
        from halbert_core.agents.channels import (
            TERMINAL_CHANNEL, stamped_claim_source,
        )
        assert stamped_claim_source(TERMINAL_CHANNEL, None) is None

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
            DASHBOARD_CHANNEL, TERMINAL_CHANNEL, VOICE_CHANNEL,
            stamped_claim_source,
        )
        for channel in (DASHBOARD_CHANNEL, VOICE_CHANNEL, TERMINAL_CHANNEL):
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

    def test_terminal_turn_is_stamped_with_the_channels_own_identity(self, client, fake_agent):
        """C5, the ingress seam: a terminal-originated turn routes
        through the same stamped seam as dashboard/voice — the modality
        threads as the channel's own value ("terminal") so process()
        resolves the same channel for provenance, the claim is the
        channel's dashboard-token identity ASSERTED whether the wire
        declared a source or none, and the wire cannot name its own
        RoleGate role (the channel's admin default applies)."""
        resp = client.post("/api/agent/message", json={
            "message": "status of the tank",
            "modality": "terminal",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] == "terminal"
        assert kwargs["claim_source"] == "dashboard_token"
        assert kwargs["speaker_role"] is None
        assert kwargs["speaker_name"] is None

    def test_terminal_turn_claims_cannot_be_forged_or_weakened(self, client, fake_agent):
        """Over the terminal channel every declared source clamps to the
        dashboard token (a forged speaker verification mints nothing),
        the client's role is ignored, and an absent claim_source still
        carries the channel's own identity — the ruling made the token
        the terminal channel's claim unconditionally; absent cannot
        weaken it (there is no pre-C5 terminal turn to preserve)."""
        resp = client.post("/api/agent/message", json={
            "message": "unlock the deadbolt",
            "modality": "terminal",
            "speaker_name": "Mallory",
            "speaker_role": "guest",
            "claim_source": "voice_speaker_verification",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["claim_source"] == "dashboard_token"
        assert kwargs["speaker_role"] is None
        # The display label rides; it never feeds authorization.
        assert kwargs["speaker_name"] == "Mallory"

    def test_terminal_turn_declaring_no_claim_still_carries_the_token(self, client, fake_agent):
        resp = client.post("/api/agent/message", json={
            "message": "hello", "modality": "terminal",
        })
        assert resp.status_code == 200
        assert fake_agent.calls[0]["claim_source"] == "dashboard_token"


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

    @pytest.mark.asyncio
    async def test_terminal_turn_records_admin_role_and_the_channels_token_claim(self):
        """C5: a terminal turn's role is the channel's own admin default
        (the owner's shell on the owner's machine — the same dashboard
        token the door validated), and its recorded claim source is the
        channel's stamp — regardless of what the turn was handed, and
        regardless of whether it was handed anything: the channel's
        identity is not absent-able."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="terminal",
            speaker_role=None, claim_source=None,
        )
        assert ctx.speaker_role == "admin"
        assert ctx.claim_source == "dashboard_token"
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.ASSERTED

    @pytest.mark.asyncio
    async def test_terminal_turn_claims_derive_from_the_channel_not_the_wire(self):
        """Even a claim_source the ladder reads below ASSERTED cannot
        weaken a terminal turn: the claim is derived from the channel's
        own stamp, so the wire can neither raise nor lower the identity
        the server validated."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="terminal", claim_source="free_text_name",
        )
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.ASSERTED
        assert ctx.claim_source == "dashboard_token"


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

    @pytest.mark.asyncio
    async def test_terminal_turn_binds_the_terminal_channel_and_unbinds_after(self):
        """C5: a terminal-originated turn binds the terminal channel for
        the user row's provenance (metadata.channel == "terminal"),
        through the same one-registry seam as dashboard and voice."""
        agent = _make_agent()
        from halbert_core.agents.channels import (
            current_turn_channel, TERMINAL_CHANNEL,
        )
        bound = {}
        stream = agent.process(
            query="hello", session_id="s-ch-5", modality="terminal",
        )
        try:
            async for _event in stream:
                bound["channel"] = current_turn_channel.get()
                break
        finally:
            await stream.aclose()
        assert bound["channel"] is TERMINAL_CHANNEL
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


# ---------------------------------------------------------------------------
# C5's boundary: the terminal TOOL surface is not (and never becomes) a
# talk ingress — the founder's two-terminal caution, pinned
# ---------------------------------------------------------------------------

class TestTheTerminalToolSurfaceIsNotATalkIngress:
    """Two terminals are installed in the app (founder caution, ruled on
    2026-09-07), and the correct one was verified before wiring:

      * the Plan B watched-shell surface — routes/terminal.py's session
        lifecycle + streaming/pty.py + the terminal_blocks/
        terminal_sessions tables, rendered by TerminalTile /
        InlineTerminals / YourShellRegion in the agent chat. THE
        production terminal: the founder's terminal direction (shells
        watched by the machine, stage-into-shell, agent-reusable pool
        sessions) and the design C5 row's own "existing terminal
        subsystem".
      * the stale one-shot ``/terminal`` page (frontend pages/Terminal.tsx)
        — the MVP surface: simulated connection text, simulated AI
        (/explain, /dryrun are client-side canned strings), one PTY per
        command via POST /api/terminal/exec. It reaches the agent loop
        as a talk ingress exactly never.

    Neither is the talk channel's ingress. C5's channel is the
    *modality* a terminal-originated turn carries through the one talk
    door; the tool surface stays a tool surface (design C5 row: "pty
    spawn/exec/stage, routes/terminal.py ... stays one"). Pinned here
    so no terminal tool request can ever be admitted as a channel turn:

      * the tool routes' request models carry none of the talk-ingress
        fields, so a request through them cannot smuggle a modality;
      * the tool routes never import the channel layer;
      * the stale page's requests still route through the one-shot
        /exec endpoint, unchanged.
    """

    _TALK_FIELDS = {"modality", "speaker_name", "speaker_role", "claim_source"}

    def test_terminal_tool_requests_cannot_carry_talk_ingress_fields(self):
        from halbert_core.dashboard.routes import terminal as terminal_routes
        for model in (terminal_routes.CommandRequest,
                      terminal_routes.SpawnRequest,
                      terminal_routes.InputRequest,
                      terminal_routes.StageRequest,
                      terminal_routes.WatchedRequest):
            assert not self._TALK_FIELDS & set(model.model_fields), (
                f"{model.__name__} grew a talk-ingress field: the tool "
                f"surface must not become a talk ingress by request model"
            )

    def test_terminal_tool_routes_never_import_the_channel_layer(self):
        import inspect
        from halbert_core.dashboard.routes import terminal as terminal_routes
        source = inspect.getsource(terminal_routes)
        assert "agents.channels" not in source, (
            "routes/terminal.py resolves a channel: the tool surface has "
            "become a talk ingress"
        )

    def test_the_stale_terminal_page_still_posts_to_the_one_shot_endpoint(self):
        """The wrong terminal is left exactly as it is: the MVP /terminal
        page's requests still route through /api/terminal/exec — the
        one-shot spawn-drain-kill path — and nothing in it reaches the
        talk door."""
        from pathlib import Path
        import halbert_core
        page = (
            Path(halbert_core.__file__).parent
            / "dashboard" / "frontend" / "src" / "pages" / "Terminal.tsx"
        )
        source = page.read_text(encoding="utf-8")
        assert "apiUrl('/api/terminal/exec')" in source
        assert "/api/agent/message" not in source