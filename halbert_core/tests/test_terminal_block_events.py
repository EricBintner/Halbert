# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Block lifecycle on the SSE stream (Plan B: B12).

``StreamEvent.terminal_block`` and its promote variant were written, and the
frontend has handled both since the day it was written -- ``useAgentStream``
adds a block record on one and flips ``isTaskCard`` on the other. Nothing on
the backend ever emitted either, so a command was only ever a spawn and a
complete, and the conversation had no way to tell a 200ms `ls` from a
20-minute rsync.

These tests pin the two seams that carry a block from the pool to the stream:
the bridge payload kinds, and the state machine's translation of them.
"""

import asyncio

import pytest

from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.streaming.agent_pool import TerminalPool
from halbert_core.streaming.session_manager import TerminalSessionManager


def _make_manager_with_pool(cap=3, max_sessions=8):
    m = TerminalSessionManager(
        max_sessions=max_sessions,
        kind_caps={"user": 3, "agent-pool": cap, "oneshot": 2},
    )
    return m, TerminalPool(m, cap=cap)


class TestBlockPayloadTranslation:
    """A bridge payload becomes the SSE event the frontend already handles."""

    def test_a_block_payload_becomes_a_terminal_block_event(self):
        event = AgentStateMachine._terminal_event("sess-1", {
            "kind": "block",
            "terminal_session_id": "term-1",
            "block_id": "blk-1",
            "command": "systemctl status smbd",
            "owner": "agent",
        })

        assert event is not None
        assert event.type == "terminal_block"
        assert event.data["block_id"] == "blk-1"
        assert event.data["terminal_session_id"] == "term-1"
        assert event.data["command"] == "systemctl status smbd"
        assert event.data["owner"] == "agent"

    def test_a_promote_payload_becomes_the_promote_event(self):
        event = AgentStateMachine._terminal_event("sess-1", {
            "kind": "block_promote",
            "terminal_session_id": "term-1",
            "block_id": "blk-1",
            "command": "rsync -a /mnt/a /mnt/b",
            "owner": "agent",
        })

        assert event is not None
        # The frontend switches on this exact string to flip isTaskCard.
        assert event.type == "terminal_block_promote"
        assert event.data["block_id"] == "blk-1"

    def test_an_unknown_kind_is_ignored_rather_than_guessed(self):
        assert AgentStateMachine._terminal_event("sess-1", {"kind": "nonsense"}) is None

    def test_a_block_without_an_id_is_not_emitted(self):
        # A block event whose id is empty would create an unaddressable block
        # record in the store: nothing could ever promote it, complete it, or
        # jump to it. Dropping it is the honest outcome.
        assert AgentStateMachine._terminal_event("sess-1", {
            "kind": "block",
            "terminal_session_id": "term-1",
            "block_id": "",
            "command": "ls",
        }) is None


class TestPoolPublishesBlockOpen:
    """The pool announces the block, not just the session."""

    @pytest.mark.asyncio
    async def test_run_block_publishes_a_block_payload_with_the_spawn(self, monkeypatch):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)

        m, pool = _make_manager_with_pool()
        try:
            result = await pool.run_block("printf hello", timeout=10.0)
            assert result is not None
        finally:
            await pool.shutdown()

        kinds = [p.get("kind") for p in published]
        assert "spawn" in kinds
        assert "block" in kinds, f"no block payload published; got {kinds}"

        block = next(p for p in published if p.get("kind") == "block")
        assert block["block_id"] == result["block_id"]
        assert block["terminal_session_id"] == result["session_id"]
        assert block["command"] == "printf hello"
        assert block["owner"] == "agent"

    @pytest.mark.asyncio
    async def test_the_block_payload_follows_the_spawn(self, monkeypatch):
        """Order matters: the frontend creates the session on spawn and
        attaches the block to it. A block for a session it has not seen is
        dropped, so publishing them the other way round loses the block."""
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)

        m, pool = _make_manager_with_pool()
        try:
            assert await pool.run_block("printf hi", timeout=10.0) is not None
        finally:
            await pool.shutdown()

        kinds = [p.get("kind") for p in published]
        assert kinds.index("spawn") < kinds.index("block")


class TestLongRunningPromotion:
    """A block still open after the threshold becomes a task card.

    This is the whole fast/slow distinction. Without it the conversation
    treats a 200ms `ls` and a 20-minute rsync identically: both spawn a live
    tile the instant they start, and neither ever settles.
    """

    @pytest.mark.asyncio
    async def test_a_slow_block_is_promoted(self, monkeypatch):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)
        monkeypatch.setattr(pool_mod, "PROMOTE_AFTER_SECONDS", 0.15)

        m, pool = _make_manager_with_pool()
        try:
            result = await pool.run_block("sleep 0.6", timeout=10.0)
            assert result is not None
        finally:
            await pool.shutdown()

        promotes = [p for p in published if p.get("kind") == "block_promote"]
        assert len(promotes) == 1, f"expected one promotion, got {published}"
        assert promotes[0]["block_id"] == result["block_id"]
        assert promotes[0]["command"] == "sleep 0.6"

    @pytest.mark.asyncio
    async def test_a_fast_block_is_never_promoted(self, monkeypatch):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)
        monkeypatch.setattr(pool_mod, "PROMOTE_AFTER_SECONDS", 5.0)

        m, pool = _make_manager_with_pool()
        try:
            assert await pool.run_block("printf quick", timeout=10.0) is not None
        finally:
            await pool.shutdown()

        assert [p for p in published if p.get("kind") == "block_promote"] == []

    @pytest.mark.asyncio
    async def test_the_promotion_timer_does_not_outlive_its_block(self, monkeypatch):
        """A finished block must not promote afterwards.

        The timer is a task racing the command. If it is not cancelled when
        the D marker arrives, a fast command promotes two seconds after it
        already printed its result -- a task card for something that is over.
        """
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)
        monkeypatch.setattr(pool_mod, "PROMOTE_AFTER_SECONDS", 0.2)

        m, pool = _make_manager_with_pool()
        try:
            assert await pool.run_block("printf quick", timeout=10.0) is not None
        finally:
            await pool.shutdown()

        # Well past the threshold, with the block long closed.
        await asyncio.sleep(0.5)
        assert [p for p in published if p.get("kind") == "block_promote"] == []

    @pytest.mark.asyncio
    async def test_a_timed_out_block_leaves_no_stray_promotion(self, monkeypatch):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)
        monkeypatch.setattr(pool_mod, "PROMOTE_AFTER_SECONDS", 10.0)

        m, pool = _make_manager_with_pool()
        try:
            await pool.run_block("sleep 5", timeout=0.3)
        finally:
            await pool.shutdown()

        await asyncio.sleep(0.3)
        assert [p for p in published if p.get("kind") == "block_promote"] == []


class TestBlockCarriesItsToolCall:
    """A block says which tool call ran it.

    The conversation renders a card per tool call and a tile per block, and
    until now nothing connected the two: the card had an execution id, the
    block had a session id and a command, and no field was common to both.
    Matching them on the command string is what open-claude-code does
    (ui/app.mjs matches a result to a running card by *tool name*), and it
    breaks the moment two commands run in one turn.

    The state machine is the one place that knows both, because it drains the
    bridge while one specific tool call is running.
    """

    def test_a_block_event_carries_the_execution_id_it_was_given(self):
        event = AgentStateMachine._terminal_event(
            "sess-1",
            {
                "kind": "block",
                "terminal_session_id": "term-1",
                "block_id": "blk-1",
                "command": "ls",
                "owner": "agent",
            },
            execution_id="exec-42",
        )

        assert event.data["execution_id"] == "exec-42"

    def test_without_one_the_field_is_absent_rather_than_empty(self):
        """An empty string would join to nothing while looking like an id.
        A missing key is the honest shape for "this block has no tool call"
        -- a watched user shell block, for instance."""
        event = AgentStateMachine._terminal_event("sess-1", {
            "kind": "block",
            "terminal_session_id": "term-1",
            "block_id": "blk-1",
            "command": "ls",
        })

        assert event.data.get("execution_id") is None

    @pytest.mark.asyncio
    async def test_run_tool_streaming_stamps_the_running_tool_call(self):
        from halbert_core.agents.states import StateContext
        from halbert_core.streaming.terminal_bridge import (
            TerminalEventBus,
            current_agent_session,
            publish_terminal_event,
            set_terminal_event_bus,
        )

        set_terminal_event_bus(TerminalEventBus())
        try:
            machine = AgentStateMachine(llm_client=None, tool_executor=None)
            machine.ctx = StateContext(
                session_id="sess-1", request_id="req-1", user_query="ls"
            )

            class _Tools:
                async def execute(self, name, args, **kwargs):
                    token = current_agent_session.set("sess-1")
                    try:
                        publish_terminal_event({
                            "kind": "block",
                            "terminal_session_id": "term-1",
                            "block_id": "blk-1",
                            "command": "ls",
                            "owner": "agent",
                        })
                        await asyncio.sleep(0.05)
                        return "done"
                    finally:
                        current_agent_session.reset(token)

            machine.tools = _Tools()
            sink = []
            events = [
                e async for e in machine._run_tool_streaming(
                    "run_command", {"command": "ls"}, True, sink,
                    execution_id="exec-42",
                )
            ]
        finally:
            set_terminal_event_bus(None)

        blocks = [e for e in events if e.type == "terminal_block"]
        assert len(blocks) == 1
        assert blocks[0].data["execution_id"] == "exec-42"


class TestCompleteCarriesTheBlocksResult:
    """The card cannot render a result it is never sent.

    Every block branch in ToolExecutionCard needs three things beyond the
    block id: the exit code, how long it took, and the block's own output.
    The complete payload carried only the exit code, so `isShortBlock` and
    `suppressResult` -- both gated on the other two -- stayed false and the
    one-line result remained unreachable even after the id was wired.

    Output has to come from here rather than from the session's scrollback:
    a pool session is REUSED across blocks, so its buffer holds every
    command it has ever run. Rendering that as "this block's output" would
    be wrong in the most confusing possible way.
    """

    @pytest.mark.asyncio
    async def test_complete_carries_duration_exit_and_this_blocks_output(self, monkeypatch):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)

        m, pool = _make_manager_with_pool()
        try:
            result = await pool.run_block("printf 'one\\ntwo\\n'", timeout=10.0)
            assert result is not None
        finally:
            await pool.shutdown()

        done = [p for p in published if p.get("kind") == "complete"]
        assert len(done) == 1
        payload = done[0]
        assert payload["block_id"] == result["block_id"]
        assert payload["exit_code"] == 0
        assert payload["duration"] == pytest.approx(result["duration"], abs=0.01)
        assert payload["output_head"] == result["output_head"]
        assert payload["output_tail"] == result["output_tail"]
        assert "one" in payload["output_head"]

    @pytest.mark.asyncio
    async def test_a_reused_session_reports_only_the_second_blocks_output(self, monkeypatch):
        """The trap this exists to prevent: block two's payload must not
        carry block one's output."""
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        monkeypatch.setattr(pool_mod, "publish_terminal_event", published.append)

        m, pool = _make_manager_with_pool(cap=1)
        try:
            first = await pool.run_block("printf FIRSTMARKER", timeout=10.0)
            second = await pool.run_block("printf SECONDMARKER", timeout=10.0)
            assert first is not None and second is not None
            # Same session, reused -- which is the whole point of the pool.
            assert first["session_id"] == second["session_id"]
        finally:
            await pool.shutdown()

        done = [p for p in published if p.get("kind") == "complete"]
        assert len(done) == 2
        assert "SECONDMARKER" in done[1]["output_head"]
        assert "FIRSTMARKER" not in done[1]["output_head"]

    def test_the_complete_event_relays_what_the_payload_carries(self):
        event = AgentStateMachine._terminal_event("sess-1", {
            "kind": "complete",
            "terminal_session_id": "term-1",
            "block_id": "blk-1",
            "exit_code": 1,
            "duration": 0.42,
            "output_head": "nope",
            "output_tail": "nope",
        })

        assert event.type == "terminal_complete"
        assert event.data["exit_code"] == 1
        assert event.data["block_id"] == "blk-1"
        assert event.data["duration"] == 0.42
        assert event.data["output_head"] == "nope"
        assert event.data["output_tail"] == "nope"


class TestPromotionLooksBeforeItSpeaks:
    """Cancelling the timer is not enough on its own.

    Between the D marker arriving and the finally that cancels the timer, the
    pool decodes the output, splits head and tail, and redacts both. A timer
    expiring inside that window has already been scheduled: cancel() comes too
    late, and a block that finished promotes to a task card for something that
    is over. The timer therefore checks whether the block is still open at the
    moment it wakes, not only at the moment it was armed.
    """

    @pytest.mark.asyncio
    async def test_it_does_not_publish_for_a_block_that_closed_while_it_slept(self):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        pool = pool_mod.TerminalPool.__new__(pool_mod.TerminalPool)
        original = pool_mod.publish_terminal_event
        pool_mod.publish_terminal_event = published.append
        try:
            await pool._promote_after(0, lambda: False, {"kind": "block_promote"})
        finally:
            pool_mod.publish_terminal_event = original

        assert published == []

    @pytest.mark.asyncio
    async def test_it_publishes_while_the_block_is_still_open(self):
        from halbert_core.streaming import agent_pool as pool_mod

        published = []
        pool = pool_mod.TerminalPool.__new__(pool_mod.TerminalPool)
        original = pool_mod.publish_terminal_event
        pool_mod.publish_terminal_event = published.append
        try:
            await pool._promote_after(0, lambda: True, {"kind": "block_promote"})
        finally:
            pool_mod.publish_terminal_event = original

        assert published == [{"kind": "block_promote"}]

    @pytest.mark.asyncio
    async def test_a_publish_failure_does_not_surface_as_an_unretrieved_task(self):
        """The timer is a fire-and-forget task nobody awaits. An exception
        inside it would only ever appear as asyncio's "exception was never
        retrieved" at interpreter shutdown."""
        from halbert_core.streaming import agent_pool as pool_mod

        def _boom(_payload):
            raise RuntimeError("bus is gone")

        pool = pool_mod.TerminalPool.__new__(pool_mod.TerminalPool)
        original = pool_mod.publish_terminal_event
        pool_mod.publish_terminal_event = _boom
        try:
            await pool._promote_after(0, lambda: True, {"kind": "block_promote"})
        finally:
            pool_mod.publish_terminal_event = original
