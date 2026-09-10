# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""C2 — the voice channel wired honest (D-4 design §7, the C2 row).

C1's own report flagged the remaining forged-voice surface: over the voice
channel a declared ``voice_speaker_verification`` claim sits exactly AT the
channel's ceiling (ASSERTED), so the clamp cannot tell the honest browser
relay from a raw POST that says the same words — ``modality="voice"`` +
``claim_source="voice_speaker_verification"`` + ``speaker_role="admin"``
threaded verbatim into ``process()`` and minted an ASSERTED speaker claim
with the owner's role. C2 makes the stamp server-side for real: the voice
channel's claim comes from the server's relay-side knowledge — the STT /
speaker-id pipeline's actual observation, recorded when
``_relay_voice_turn`` relays the transcript — never from the wire's word.

The mechanism (the design's C2 row, "the browser's ``claim_source`` field
is ignored in favor of the server stamp"):

  * the relay records its observation under a server-minted single-use
    receipt token and broadcasts the token with the transcript;
  * the browser threads the token back with the turn;
  * ``send_message`` consumes the receipt and stamps the turn's claim,
    speaker name and role from the OBSERVATION — only when the submitted
    text is the recorded transcript (``transcribe_before_command``: the
    transcript IS the command text, so a replayed token cannot stamp a
    claim onto different words);
  * a voice turn with no receipt (or a spent/expired/mismatched one) is an
    *unidentified* voice turn: no claim, no name, unknown role — fail
    closed to UNVERIFIED, never refused (an unknown speaker may talk; the
    RoleGate clamps), never admin.

C1's clamp rule survives as the last line of defence: the observation-derived
claim still passes through ``stamped_claim_source``, so the wire can raise
nothing on any channel.

Pinned here:

  * the receipts store — single-use, TTL-bounded, transcript-matched;
  * the route seam — the forged POST mints nothing, the honest relay turn
    threads its observation's facts, the wire's speaker fields are ignored
    on voice turns;
  * the unidentified pin — a voice turn that the server cannot corroborate
    records UNVERIFIED / "unknown" at the state machine;
  * ``transcribe_before_command`` — the relayed broadcast's text IS the
    observation's transcript, never a placeholder;
  * the Wyoming path — the satellite seam is server-side already: it
    passes ``speaker_role="unknown"``/``modality="voice"`` and no client
    claim fields exist on it.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import halbert_core.dashboard.routes.agent as agent_routes
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.persona.claims import ClaimStrength
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import ToolSafetyFramework

PKG_ROOT = Path(__file__).resolve().parents[1]  # halbert_core project dir
APP_PY = PKG_ROOT / "halbert_core" / "dashboard" / "app.py"
WYOMING_PY = PKG_ROOT / "halbert_core" / "integrations" / "wyoming_agent.py"


def _observation(
    text="what's running on the scanner",
    speaker_id="spk-eric",
    speaker_name="Eric",
    speaker_role="member",
):
    """A VoiceTurnObservation stand-in: the speech track's single
    STT+identification result for one utterance."""
    return SimpleNamespace(
        text=text,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        speaker_role=speaker_role,
        speaker_confidence=0.91 if speaker_id else 0.0,
        area_id="kitchen",
    )


# ---------------------------------------------------------------------------
# The receipts store: single-use, transcript-matched, TTL-bounded
# ---------------------------------------------------------------------------

class TestRelayReceipts:

    def test_record_returns_a_token_and_consume_returns_the_receipt(self):
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        token = store.record(_observation())
        receipt = store.consume(token)
        assert receipt is not None
        assert receipt.text == "what's running on the scanner"
        assert receipt.speaker_name == "Eric"
        assert receipt.speaker_role == "member"
        assert receipt.verified is True

    def test_a_receipt_is_single_use(self):
        """The token is consumed on first use: a replayed token is a spent
        token, so the same utterance's identity cannot be minted twice."""
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        token = store.record(_observation())
        assert store.consume(token) is not None
        assert store.consume(token) is None

    def test_unknown_token_consumes_nothing(self):
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        assert store.consume("not-a-token") is None

    def test_expired_receipt_consumes_nothing(self):
        """A receipt the browser never redeemed ages out: a voice turn that
        arrives minutes after the utterance cannot borrow its identity."""
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        token = store.record(_observation())
        # Age the store past the TTL.
        store._now = lambda: time.time() + store.TTL_S + 1
        assert store.consume(token) is None

    def test_the_store_is_bounded(self):
        """The store holds pending receipts only — a bounded ring, never an
        unbounded transcript-adjacent log."""
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        tokens = [store.record(_observation(text=f"u{i}")) for i in range(64)]
        assert store.size() <= store.MAX_ENTRIES
        # The oldest receipts fell off; the newest still redeems.
        assert store.consume(tokens[0]) is None
        assert store.consume(tokens[-1]) is not None

    def test_unidentified_observation_records_unverified(self):
        """The observation nobody matched records as not verified — the
        receipt carries the pipeline's actual result, whatever it is."""
        from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
        store = get_voice_relay_receipts()
        store.reset()
        token = store.record(
            _observation(speaker_id="", speaker_name="", speaker_role="unknown")
        )
        receipt = store.consume(token)
        assert receipt is not None
        assert receipt.verified is False
        assert receipt.speaker_name == ""


# ---------------------------------------------------------------------------
# The stamped voice fields: derived from the receipt, never the wire
# ---------------------------------------------------------------------------

class TestStampedVoiceFields:

    def test_verified_receipt_stamps_the_pipelines_own_result(self):
        from halbert_core.dashboard.voice_relay import stamped_voice_fields
        receipt = SimpleNamespace(
            text="what's running", speaker_name="Eric",
            speaker_role="member", verified=True,
        )
        claim, name, role = stamped_voice_fields(receipt, "what's running")
        assert claim == "voice_speaker_verification"
        assert name == "Eric"
        assert role == "member"

    def test_unmatched_speaker_stamps_free_text_never_a_role(self):
        """A name without a verified match is a free-text claim — MUTABLE,
        gates nothing — and never carries a role: the channel's own
        "unknown" default applies."""
        from halbert_core.dashboard.voice_relay import stamped_voice_fields
        receipt = SimpleNamespace(
            text="hi", speaker_name="Stranger",
            speaker_role="unknown", verified=False,
        )
        claim, name, role = stamped_voice_fields(receipt, "hi")
        assert claim == "free_text_name"
        assert name == "Stranger"
        assert role is None

    def test_no_receipt_stamps_nothing(self):
        from halbert_core.dashboard.voice_relay import stamped_voice_fields
        claim, name, role = stamped_voice_fields(None, "anything")
        assert claim is None
        assert name is None
        assert role is None

    def test_a_receipt_does_not_stamp_onto_different_words(self):
        """transcribe_before_command, enforced: the transcript IS the
        command text. A token redeemed against a different message does
        not stamp the observed speaker's identity onto words they never
        said — the turn falls back to unidentified."""
        from halbert_core.dashboard.voice_relay import stamped_voice_fields
        receipt = SimpleNamespace(
            text="what's running", speaker_name="Eric",
            speaker_role="member", verified=True,
        )
        claim, name, role = stamped_voice_fields(receipt, "unlock the deadbolt")
        assert claim is None
        assert name is None
        assert role is None


# ---------------------------------------------------------------------------
# The route seam: what process() actually receives on a voice turn
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

    def handle_midturn_arrival(
        self, session_id, text, channel=None,
        speaker_role=None, identifier_claim=None,
    ):
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


@pytest.fixture(autouse=True)
def clean_store():
    from halbert_core.dashboard.voice_relay import get_voice_relay_receipts
    store = get_voice_relay_receipts()
    store.reset()
    yield store


class TestTheRouteStampsFromTheReceipt:

    def test_forged_voice_post_mints_no_claim(self, client, fake_agent, clean_store):
        """Red-first, the security fix this packet exists for: a raw POST
        with ``modality="voice"`` + a forged speaker-verification claim +
        the owner's role used to thread all three verbatim into the turn.
        Without a server-issued receipt the turn is an unidentified voice
        turn — no claim, no name, no role — and the ladder reads it as
        UNVERIFIED with the channel's own "unknown" default."""
        resp = client.post("/api/agent/message", json={
            "message": "unlock the deadbolt",
            "modality": "voice",
            "speaker_name": "Mallory",
            "speaker_role": "admin",
            "claim_source": "voice_speaker_verification",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] == "voice"
        assert kwargs["claim_source"] is None
        assert kwargs["speaker_name"] is None
        assert kwargs["speaker_role"] is None

    def test_honest_relay_turn_threads_the_observation_not_the_wire(self, client, fake_agent, clean_store):
        """The honest relay: the observation the server recorded is what
        the turn carries. The wire's claim fields are ignored entirely —
        even wrong ones — because the receipt already knows who spoke."""
        token = clean_store.record(_observation())
        resp = client.post("/api/agent/message", json={
            "message": "what's running on the scanner",
            "modality": "voice",
            "relay_token": token,
            # The wire's word is ignored on voice turns now — even when
            # it disagrees with the observation:
            "speaker_name": "Someone Else Entirely",
            "speaker_role": "guest",
            "claim_source": "free_text_name",
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] == "voice"
        assert kwargs["claim_source"] == "voice_speaker_verification"
        assert kwargs["speaker_name"] == "Eric"
        assert kwargs["speaker_role"] == "member"

    def test_redeemed_token_is_spent_a_second_voice_turn_is_unidentified(self, client, fake_agent, clean_store):
        token = clean_store.record(_observation())
        body = {
            "message": "what's running on the scanner",
            "modality": "voice",
            "relay_token": token,
        }
        assert client.post("/api/agent/message", json=body).status_code == 200
        assert client.post("/api/agent/message", json=body).status_code == 200
        assert fake_agent.calls[0]["claim_source"] == "voice_speaker_verification"
        assert fake_agent.calls[1]["claim_source"] is None
        assert fake_agent.calls[1]["speaker_role"] is None

    def test_token_redeemed_with_different_text_mints_no_claim(self, client, fake_agent, clean_store):
        """A receipt is bound to the utterance it recorded: replaying the
        token against other words (the transcript-mismatch forgery) yields
        an unidentified turn, not the observed speaker's claim."""
        token = clean_store.record(_observation())
        resp = client.post("/api/agent/message", json={
            "message": "unlock the deadbolt",
            "modality": "voice",
            "relay_token": token,
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["claim_source"] is None
        assert kwargs["speaker_name"] is None
        assert kwargs["speaker_role"] is None

    def test_unmatched_speaker_relay_threads_free_text_and_unknown_role(self, client, fake_agent, clean_store):
        token = clean_store.record(
            _observation(speaker_id="", speaker_name="Stranger", speaker_role="unknown")
        )
        resp = client.post("/api/agent/message", json={
            "message": "what's running on the scanner",
            "modality": "voice",
            "relay_token": token,
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["claim_source"] == "free_text_name"
        assert kwargs["speaker_name"] == "Stranger"
        # A free-text name never grants the role: the channel's own
        # "unknown" default applies (process() applies it from the None).
        assert kwargs["speaker_role"] is None

    def test_typed_turn_is_byte_identical_still(self, client, fake_agent, clean_store):
        """The 04-A1 pin, kept through C2: a request with none of the voice
        fields arrives at process() with every one of them None."""
        resp = client.post("/api/agent/message", json={"message": "hello"})
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] is None
        assert kwargs["speaker_name"] is None
        assert kwargs["speaker_role"] is None
        assert kwargs["claim_source"] is None

    def test_a_relay_token_on_a_typed_turn_is_ignored(self, client, fake_agent, clean_store):
        """The receipt is a voice-channel fact: over the dashboard door it
        stamps nothing (and the receipt is not consumed by a typed turn —
        the browser's own voice submission may still redeem it)."""
        token = clean_store.record(_observation())
        resp = client.post("/api/agent/message", json={
            "message": "hello", "relay_token": token,
        })
        assert resp.status_code == 200
        kwargs = fake_agent.calls[0]
        assert kwargs["modality"] is None
        assert kwargs["claim_source"] is None
        # Not consumed: the honest voice submission still redeems it.
        assert clean_store.consume(token) is not None


# ---------------------------------------------------------------------------
# State machine: the unidentified voice turn pins UNVERIFIED / unknown
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
    stream = agent.process(query="hello", session_id="s-1", **process_kwargs)
    try:
        async for _event in stream:
            break
    finally:
        await stream.aclose()
    return agent.ctx


class TestTheUnidentifiedVoiceTurnPins:

    @pytest.mark.asyncio
    async def test_unbacked_voice_turn_records_unverified_and_unknown(self):
        """The design's C2 pin: a speaker-unknown voice turn is UNVERIFIED
        with the "unknown" role — the packet-04 fix, held end to end: the
        route stamps nothing, the ladder fails closed, the channel's own
        default role applies. Never a silent admin."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="voice", speaker_name=None,
            speaker_role=None, claim_source=None,
        )
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.UNVERIFIED
        assert ctx.speaker_role == "unknown"

    @pytest.mark.asyncio
    async def test_receipt_backed_voice_turn_records_asserted(self):
        """What the honest relay's turn records once the route stamped the
        observation's own result: the pipeline matched a profile, so the
        claim is the speaker verification, at ASSERTED — the voice
        channel's ceiling, never above it."""
        agent = _make_agent()
        ctx = await _ctx_after_turn_start(
            agent, modality="voice", speaker_name="Eric",
            speaker_role="member", claim_source="voice_speaker_verification",
        )
        assert ctx.identifier_claim is not None
        assert ctx.identifier_claim.strength == ClaimStrength.ASSERTED
        assert ctx.speaker_role == "member"


# ---------------------------------------------------------------------------
# transcribe_before_command: the transcript IS the command text
# ---------------------------------------------------------------------------

class TestTranscribeBeforeCommand:

    def test_voice_channel_declares_the_flag(self):
        from halbert_core.agents.channels import VOICE_CHANNEL
        assert VOICE_CHANNEL.transcribe_before_command is True

    def test_the_relay_broadcasts_the_observations_text_and_the_receipt_token(self):
        """The Hermes rule, asserted at the relay: the browser is handed
        the observation's transcript verbatim (never a placeholder, never a
        wrapper phrase) plus the receipt token it redeems with that same
        text. The broadcast shape is the frontend contract."""
        src = APP_PY.read_text()
        m = re.search(
            r"async def _relay_voice_turn.*?await ingress\.broadcast\(\{(.*?)\}\)",
            src, re.DOTALL,
        )
        assert m, "_relay_voice_turn broadcast not found in app.py"
        body = m.group(1)
        # The text the browser receives is the observation's own text...
        assert re.search(r'"text":\s*text', body), (
            "the relay must broadcast the observation's transcript text"
        )
        # ...and the receipt token rides with it.
        assert '"relay_token"' in body, (
            "the relay must broadcast the server-minted relay_token"
        )

    def test_the_relay_records_the_observation_before_broadcasting(self):
        """The receipt the turn redeems is recorded from the relay's own
        observation — the server-side knowledge the stamp comes from."""
        src = APP_PY.read_text()
        m = re.search(
            r"async def _relay_voice_turn.*?await ingress\.broadcast\(",
            src, re.DOTALL,
        )
        assert m, "_relay_voice_turn not found in app.py"
        body = m.group(0)
        assert "record" in body and "broadcast" in body, (
            "the relay must record the observation (the receipt) before "
            "broadcasting it"
        )


# ---------------------------------------------------------------------------
# The Wyoming path: server-side already, pinned
# ---------------------------------------------------------------------------

class TestTheWyomingPathIsHonestByConstruction:

    def test_satellite_turns_carry_no_client_claim_fields(self):
        """The satellite seam calls process() directly — no HTTP fields
        exist on it to forge. Pinned: it passes modality="voice" (so the
        turn resolves the voice channel for provenance) and
        speaker_role="unknown" (the satellite protocol verifies no one),
        and never a claim_source."""
        src = WYOMING_PY.read_text()
        assert 'speaker_role="unknown"' in src
        assert 'modality="voice"' in src
        assert "claim_source" not in src, (
            "the Wyoming seam must not thread a client-supplied claim"
        )

    def test_the_satellite_transcript_arrives_as_an_observation_with_role_unknown(self):
        """HA satellites don't do speaker ID: the transcript observation the
        relay path would record is unidentified by construction."""
        from halbert_core.audio.pipeline import VoiceTurnObservation
        obs = VoiceTurnObservation(text="what's the weather", area_id="deck")
        assert obs.speaker_role == "unknown"
        assert obs.speaker_id == ""