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
