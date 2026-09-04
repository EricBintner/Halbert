# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A terminal block knows which turn ran it.

``terminal_blocks`` has had ``thread_id`` and ``turn_id`` columns, and an
index on the latter, since the table was created -- and the executor wrote
``None`` into both. So the row that records a command could not be traced
back to the conversation turn that ran it, and "jump to where this happened"
had no join key. Timeline's ``loadAround`` takes a turn id; the block had
none to give.

The turn id does not exist while the command runs -- it is assigned when the
turn is persisted -- so the block cannot be born with it. ``end_turn`` stamps
it on afterwards, from the block ids the turn already carries.
"""

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


def _turn(store, text):
    """A ThreadManager with an open turn, the way the routes build one."""
    from halbert_core.intake.signals import analyze_message
    from halbert_core.agents.threads import ThreadManager

    tm = ThreadManager(store=store)
    return tm, tm.begin_turn(text, analyze_message(text), "sess-1")


def _block(store, block_id, session_id="term-1"):
    store.insert_terminal_block({
        "block_id": block_id,
        "session_id": session_id,
        "thread_id": None,
        "turn_id": None,
        "command": "systemctl status smbd",
        "cwd": None,
        "owner": "agent",
        "interactive": 0,
        "remote": 0,
        "redacted": 0,
        "started_at": 1.0,
        "ended_at": 2.0,
        "exit_code": 0,
        "output_head": "active",
        "output_tail": "active",
    })


class TestUpdatableColumns:
    def test_a_block_can_be_stamped_with_its_turn(self, store):
        _block(store, "blk-1")

        assert store.update_terminal_block(
            "blk-1", thread_id="thread-9", turn_id="turn-7"
        ) is True

        row = store.get_terminal_block("blk-1")
        assert row["turn_id"] == "turn-7"
        assert row["thread_id"] == "thread-9"

    def test_stamping_an_unknown_block_reports_failure(self, store):
        assert store.update_terminal_block("nope", turn_id="turn-7") is False


class TestEndTurnStampsItsBlocks:
    def test_end_turn_anchors_every_block_it_carries(self, store):
        _block(store, "blk-1")
        _block(store, "blk-2")

        tm, turn = _turn(store, "check the shares")
        tm.end_turn(
            turn,
            assistant_text="two shares are up",
            blocks=[],
            terminal_block_ids=["blk-1", "blk-2"],
            diff_proposals=[],
        )

        for bid in ("blk-1", "blk-2"):
            row = store.get_terminal_block(bid)
            assert row["turn_id"] == turn.turn_id, f"{bid} was not anchored"
            assert row["thread_id"] == turn.thread_id

    def test_an_id_with_no_block_row_does_not_break_the_turn(self, store):
        """Plan A tracked terminal *session* ids in the same field. One of
        those has no block row, and a turn that failed to persist because a
        stale id could not be stamped would lose the conversation."""
        _block(store, "blk-1")

        tm, turn = _turn(store, "check the shares")
        tm.end_turn(
            turn,
            assistant_text="done",
            blocks=[],
            terminal_block_ids=["blk-1", "a-session-id-not-a-block"],
            diff_proposals=[],
        )

        assert store.get_terminal_block("blk-1")["turn_id"] == turn.turn_id
        # The turn itself still landed.
        assert store.get_thread(turn.thread_id) is not None


class TestBlocksRecordTheirToolCall:
    """The anchor the historical timeline needs.

    Live, the conversation joins a tool card to its terminal block through
    the ``execution_id`` on the block event. After a reload there is no
    stream: the timeline reads stored rows, and the stored tool block (which
    has an execution_id) had nothing in common with the stored terminal block
    (which did not). So the same turn rendered one way live and another way
    after F5 -- a one-line result became a generic card and a "terminal ·
    ended" chip.

    The execution id cannot be written when the block row is inserted: the
    executor does not know it. It is stamped at end_turn, the same one moment
    that already supplies turn_id.
    """

    def test_a_block_row_can_record_its_execution(self, store):
        _block(store, "blk-1")

        assert store.update_terminal_block("blk-1", execution_id="exec-7") is True
        assert store.get_terminal_block("blk-1")["execution_id"] == "exec-7"

    def test_a_fresh_row_reports_no_execution_rather_than_failing(self, store):
        _block(store, "blk-1")
        assert store.get_terminal_block("blk-1")["execution_id"] is None

    def test_blocks_for_a_turn_come_back_with_their_executions(self, store):
        _block(store, "blk-1")
        _block(store, "blk-2")
        store.update_terminal_block("blk-1", turn_id="turn-1", execution_id="exec-1")
        store.update_terminal_block("blk-2", turn_id="turn-1", execution_id="exec-2")

        rows = store.list_terminal_blocks(turn_id="turn-1")
        assert {r["execution_id"] for r in rows} == {"exec-1", "exec-2"}

    def test_end_turn_stamps_the_execution_the_state_machine_recorded(self, store):
        _block(store, "blk-1")
        _block(store, "blk-2")

        tm, turn = _turn(store, "check the shares")
        tm.end_turn(
            turn,
            assistant_text="two shares",
            blocks=[],
            terminal_block_ids=["blk-1", "blk-2"],
            diff_proposals=[],
            block_executions={"blk-1": "exec-1", "blk-2": "exec-2"},
        )

        assert store.get_terminal_block("blk-1")["execution_id"] == "exec-1"
        assert store.get_terminal_block("blk-2")["execution_id"] == "exec-2"
        # The turn anchor still lands alongside it.
        assert store.get_terminal_block("blk-1")["turn_id"] == turn.turn_id

    def test_a_block_with_no_recorded_execution_still_gets_its_turn(self, store):
        """A watched user shell block belongs to a turn but to no tool call."""
        _block(store, "blk-1")

        tm, turn = _turn(store, "check the shares")
        tm.end_turn(
            turn, assistant_text="ok", blocks=[], terminal_block_ids=["blk-1"],
            diff_proposals=[], block_executions={},
        )

        row = store.get_terminal_block("blk-1")
        assert row["turn_id"] == turn.turn_id
        assert row["execution_id"] is None
