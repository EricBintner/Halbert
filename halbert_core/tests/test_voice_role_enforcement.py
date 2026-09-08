# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""D-6 wave 3: voice claim strength caps the effective role at RoleGate.

Packet 04 A2 recorded the turn's identifier claim (strength derived from
claim_source, fail-closed to UNVERIFIED) but enforced nothing — a spoken
"this is the owner" arrived with speaker_role="admin" and RoleGate heard
the owner. This pass is the enforcement: at the RoleGate consumption
point (ToolExecutor.execute's classify call), a voice turn whose claim is
below ASSERTED has its stated role capped at member-class — an
unverified voice claiming to be the owner must not wield owner-class
tools.

Pinned here:

  * ``voice_role_ceiling`` — the explicit mapping, ASSERTED-or-stronger
    keeps the stated role, everything below caps at "member";
  * ``effective_voice_role`` — applies the ceiling, never loosens (a
    guest/restricted/unknown stays what it is), and logs one structured
    ``voice_role_capped`` line when it downgrades;
  * the executor seam — a stated-admin voice turn with an UNVERIFIED
    claim is gated as member (with the capped log line), an ASSERTED
    claim is unchanged, and a TYPED turn is byte-identical to today
    (no claim is ever bound for typed turns);
  * MUTABLE behaves like UNVERIFIED — both sit below the ASSERTED floor;
  * the state machine binds the claim for voice turns and (C5, the
    founder's terminal ruling) terminal turns, and unbinds it when the
    turn ends. A terminal turn's claim is the channel's own
    dashboard-token stamp — always ASSERTED — so the cap composes as a
    no-op: the gate hears the terminal turn's admin role exactly as
    stated.
"""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from halbert_core.agents.events import StreamEvent  # noqa: F401  (harness parity)
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.persona.claims import ClaimStrength, claim_from_source
from halbert_core.tools.executor import ToolExecutor, current_turn_claim
from halbert_core.tools.role_gate import (
    RoleGate,
    effective_voice_role,
    voice_role_ceiling,
)
from halbert_core.tools.safety import ToolSafetyFramework

#: The canonical critical-classified call (never executed here — the
#: gate/refusal happens first; same fixture as test_role_gate.py).
_CRITICAL_ARGS = {"command": "dd if=/dev/zero of=/dev/sda"}


# ---------------------------------------------------------------------------
# The explicit mapping (test-pinned, no scattered conditionals)
# ---------------------------------------------------------------------------

class TestVoiceRoleCeiling:

    def test_asserted_or_stronger_keeps_the_stated_role(self):
        """A corroborated voice claim earns the strongest class."""
        assert voice_role_ceiling(ClaimStrength.ASSERTED) == "admin"
        assert voice_role_ceiling(ClaimStrength.VERIFIED) == "admin"

    def test_below_asserted_caps_at_member(self):
        """UNVERIFIED and MUTABLE are both below the ASSERTED floor —
        member is the strongest class a claim below ASSERTED can earn."""
        assert voice_role_ceiling(ClaimStrength.UNVERIFIED) == "member"
        assert voice_role_ceiling(ClaimStrength.MUTABLE) == "member"


class TestEffectiveVoiceRole:

    def test_unverified_caps_stated_admin_to_member(self):
        assert effective_voice_role("admin", ClaimStrength.UNVERIFIED) == "member"

    def test_mutable_behaves_like_unverified(self):
        assert effective_voice_role("admin", ClaimStrength.MUTABLE) == "member"

    def test_asserted_leaves_stated_admin_unchanged(self):
        assert effective_voice_role("admin", ClaimStrength.ASSERTED) == "admin"

    def test_cap_never_loosens_a_weaker_role(self):
        """The ceiling caps, never grants: guest-class and restricted
        roles are already below member, so they stand as stated — the
        claim axis never lifts a speaker out of its own class (and a
        guest persona's own gate list stays authoritative for guests)."""
        for role in ("member", "guest", "unknown", "restricted"):
            assert effective_voice_role(role, ClaimStrength.UNVERIFIED) == role

    def test_downgrade_logs_one_structured_capped_line(self, caplog):
        with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
            effective_voice_role("admin", ClaimStrength.UNVERIFIED)
        capped = [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        assert len(capped) == 1
        line = capped[0].getMessage()
        assert "stated_role=admin" in line
        assert "capped_role=member" in line
        assert "claim_strength=unverified" in line

    def test_mutable_downgrade_logs_the_mutable_strength(self, caplog):
        with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
            effective_voice_role("admin", ClaimStrength.MUTABLE)
        capped = [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        assert len(capped) == 1
        assert "claim_strength=mutable" in capped[0].getMessage()

    def test_no_downgrade_no_capped_line(self, caplog):
        """ASSERTED, or a stated role already within the ceiling: silent."""
        with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
            effective_voice_role("admin", ClaimStrength.ASSERTED)
            effective_voice_role("member", ClaimStrength.UNVERIFIED)
        assert not [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]


# ---------------------------------------------------------------------------
# The executor seam (the RoleGate consumption point)
# ---------------------------------------------------------------------------

class _RecordingGate(RoleGate):
    """Records the speaker_role the executor actually hands the gate."""

    def __init__(self, safety):
        super().__init__(safety)
        self.seen_roles = []

    def classify(self, tool_name, args, speaker_role="unknown"):
        self.seen_roles.append(speaker_role)
        return super().classify(tool_name, args, speaker_role=speaker_role)


def _executor_with_gate():
    safety = ToolSafetyFramework()
    gate = _RecordingGate(safety)
    executor = ToolExecutor(safety=safety, role_gate=gate)
    # A stub handler: the critical classification is refused before any
    # handler could run, so nothing here ever executes.
    executor.tools["run_command"] = lambda args: {"ok": True}
    return executor, gate


def _bound_claim(source, value="Stranger"):
    """The ContextVar token a voice turn's process() would bind."""
    return current_turn_claim.set(claim_from_source(source, value=value))


class TestExecutorConsumesTheCap:

    @pytest.mark.asyncio
    async def test_stated_admin_unverified_voice_turn_gated_as_member(self, caplog):
        """The red-first pin: a voice turn claiming the owner with no
        corroborated claim runs its tools as member — the gate sees
        member, the refusal says member, and one structured capped line
        records why."""
        executor, gate = _executor_with_gate()
        token = _bound_claim(None)
        try:
            with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
                result = await executor.execute(
                    "run_command", dict(_CRITICAL_ARGS), speaker_role="admin"
                )
        finally:
            current_turn_claim.reset(token)
        assert gate.seen_roles == ["member"]
        assert result.success is False
        assert "speaker role 'member'" in (result.error or "")
        capped = [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        assert len(capped) == 1
        assert "stated_role=admin" in capped[0].getMessage()

    @pytest.mark.asyncio
    async def test_asserted_voice_turn_unchanged(self, caplog):
        """Speaker verification matched (voice_speaker_verification →
        ASSERTED): the stated role stands exactly as today."""
        executor, gate = _executor_with_gate()
        token = _bound_claim("voice_speaker_verification", value="Eric")
        try:
            with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
                result = await executor.execute(
                    "run_command", dict(_CRITICAL_ARGS), speaker_role="admin"
                )
        finally:
            current_turn_claim.reset(token)
        assert gate.seen_roles == ["admin"]
        assert not [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        # Same result shape as the typed-turn admin path below.
        assert result.success is False
        assert "speaker role 'member'" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_typed_admin_turn_byte_identical(self, caplog):
        """No claim bound (a typed turn binds nothing): today's behavior
        exactly — the gate sees the stated admin role and the base
        classification flows through unmodified."""
        executor, gate = _executor_with_gate()
        assert current_turn_claim.get() is None
        with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
            result = await executor.execute(
                "run_command", dict(_CRITICAL_ARGS), speaker_role="admin"
            )
        assert gate.seen_roles == ["admin"]
        assert not [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        assert result.success is False
        assert "speaker role" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_mutable_claim_behaves_like_unverified(self, caplog):
        """A free-text spoken name ("it's me, the owner") is MUTABLE —
        below the ASSERTED floor, so it caps like UNVERIFIED does."""
        executor, gate = _executor_with_gate()
        token = _bound_claim("free_text_name", value="the owner")
        try:
            with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
                await executor.execute(
                    "run_command", dict(_CRITICAL_ARGS), speaker_role="admin"
                )
        finally:
            current_turn_claim.reset(token)
        assert gate.seen_roles == ["member"]
        capped = [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        assert len(capped) == 1
        assert "claim_strength=mutable" in capped[0].getMessage()

    @pytest.mark.asyncio
    async def test_capped_role_is_what_nested_dispatch_inherits(self):
        """The cap lands before the current_speaker_role binding, so
        tool calls dispatched from inside a script (execute_code) inherit
        the capped role — never the stated one."""
        executor, gate = _executor_with_gate()
        token = _bound_claim(None)
        seen = {}
        executor.tools["read_sensor"] = lambda args: {"c": 21.0}
        try:
            from halbert_core.tools.executor import current_speaker_role

            def probe(args):
                seen["role"] = current_speaker_role.get()
                return {"ok": True}

            executor.tools["run_command"] = probe
            # A LOW-risk call: passes every cap; the handler observes the
            # ContextVar nested dispatch would read.
            await executor.execute(
                "run_command", {"command": "ls -la"}, speaker_role="admin"
            )
        finally:
            current_turn_claim.reset(token)
        assert seen.get("role") == "member"


# ---------------------------------------------------------------------------
# The turn binding (process(): voice turns only)
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


class TestTurnBindsTheClaim:

    @pytest.mark.asyncio
    async def test_voice_turn_binds_the_claim_for_the_executor(self):
        """The turn's derived claim is bound on the ContextVar the tool
        executor reads — the same copy-down-the-task mechanism turn
        digest uses — and unbound again when the turn ends."""
        agent = _make_agent()
        stream = agent.process(
            query="hello", session_id="s-cap-1",
            modality="voice", speaker_name="Stranger",
        )
        bound = None
        try:
            async for _event in stream:
                bound = current_turn_claim.get()
                break
        finally:
            await stream.aclose()
        assert bound is not None
        assert bound.strength == ClaimStrength.UNVERIFIED
        assert current_turn_claim.get() is None

    @pytest.mark.asyncio
    async def test_typed_turn_binds_nothing(self):
        """A typed turn's identity rides the dashboard session: no claim
        is bound, so the executor's consumption point is byte-identical
        to today for every typed turn."""
        agent = _make_agent()
        stream = agent.process(query="hello", session_id="s-cap-2")
        bound = "unset"
        try:
            async for _event in stream:
                bound = current_turn_claim.get()
                break
        finally:
            await stream.aclose()
        assert bound is None


# ---------------------------------------------------------------------------
# C5: the terminal talk channel composes with the cap — as a no-op
# ---------------------------------------------------------------------------

class TestTheTerminalTurnComposesWithTheCap:

    @pytest.mark.asyncio
    async def test_terminal_turn_binds_the_channels_asserted_token_claim(self):
        """C5 (founder ruling 2026-09-07: the terminal is a third talk
        channel, ASSERTED via the dashboard token): a terminal turn
        binds the channel's own claim on the executor's ContextVar —
        ASSERTED, derived from the channel's stamp, never from the
        wire's word — and unbinds it when the turn ends."""
        agent = _make_agent()
        stream = agent.process(
            query="hello", session_id="s-cap-3", modality="terminal",
        )
        bound = None
        try:
            async for _event in stream:
                bound = current_turn_claim.get()
                break
        finally:
            await stream.aclose()
        assert bound is not None
        assert bound.strength == ClaimStrength.ASSERTED
        assert current_turn_claim.get() is None

    @pytest.mark.asyncio
    async def test_the_cap_is_a_no_op_for_an_asserted_admin_terminal_turn(self, caplog):
        """The dispatch's required pin, at the consumption point: the
        terminal turn's bound dashboard-token claim flows through the
        same effective_voice_role composition as a voice claim, and at
        ASSERTED the ceiling is admin — the gate hears the terminal
        turn's admin role exactly as stated, with no capped line. The
        cap composes; for the ruling's terminal it changes nothing."""
        executor, gate = _executor_with_gate()
        token = _bound_claim("dashboard_token", value=None)
        try:
            with caplog.at_level(logging.WARNING, logger="halbert.tools.role_gate"):
                result = await executor.execute(
                    "run_command", dict(_CRITICAL_ARGS), speaker_role="admin"
                )
        finally:
            current_turn_claim.reset(token)
        assert gate.seen_roles == ["admin"]
        assert not [
            r for r in caplog.records if "voice_role_capped" in r.getMessage()
        ]
        # Critical-classified for admin, refused on the base risk axis —
        # the same shape as the typed-turn pin (the claim axis added
        # nothing and removed nothing).
        assert result.success is False
        assert "speaker role" not in (result.error or "")