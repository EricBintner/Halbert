# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A recorded change knows which turn made it.

The review's F12, ledger half. "Jump to the conversation where this config
changed" needs a turn id, and the ledger stored thread_id and request_id and
nothing that ``loadAround(turnId)`` could aim at.

Unlike a terminal block -- whose row is written by the pool before the turn
is persisted -- the turn id exists from ``begin_turn``. So it can travel with
the write rather than being stamped on afterwards, and it travels the way the
agent session id already does: in a ContextVar, because tool handlers take
only their args dict and threading a parameter through every one of them to
reach ``record_file_change`` would be a change to every tool in the registry
for the benefit of one field.
"""

import pytest

from halbert_core.continuity.provenance import (
    FILE_CONTENT_PREDICATE,
    current_turn,
    record_file_change,
)
from halbert_core.continuity.state_store import ACTOR_AGENT, StateStore


@pytest.fixture
def store(tmp_path):
    s = StateStore(db_path=str(tmp_path / "ledger.db"))
    yield s
    s.close()


def _current(store, path):
    rows = store.current_state(subject=f"file:{path}", predicate=FILE_CONTENT_PREDICATE)
    return rows[0] if rows else None


def _write(store, path, text, **extra):
    record_file_change(
        path=str(path), reason="because", actor=ACTOR_AGENT, request_id="r1",
        tool="test", after_text=text, store=store, **extra,
    )


def test_a_write_inside_a_turn_records_that_turn(store, tmp_path):
    f = tmp_path / "smb.conf"
    token = current_turn.set("turn-42")
    try:
        _write(store, f, "[global]\n")
    finally:
        current_turn.reset(token)

    assert _current(store, f).turn_id == "turn-42"


def test_a_write_outside_a_turn_records_none(store, tmp_path):
    """The config watcher and the editor both write with no turn in scope.
    An invented id would point the timeline at a conversation that never
    happened."""
    f = tmp_path / "watched.conf"
    _write(store, f, "changed on disk\n")

    assert _current(store, f).turn_id is None


def test_an_explicit_turn_id_beats_the_ambient_one(store, tmp_path):
    f = tmp_path / "x.conf"
    token = current_turn.set("ambient")
    try:
        _write(store, f, "a\n", turn_id="explicit")
    finally:
        current_turn.reset(token)

    assert _current(store, f).turn_id == "explicit"


def test_the_turn_travels_into_a_nested_call(store, tmp_path):
    """The point of the ContextVar: a tool handler four layers down records
    the turn without anyone passing it one."""
    f = tmp_path / "deep.conf"

    def inner():
        _write(store, f, "written deep\n")

    def outer():
        inner()

    token = current_turn.set("turn-7")
    try:
        outer()
    finally:
        current_turn.reset(token)

    assert _current(store, f).turn_id == "turn-7"


def test_history_carries_the_turn_of_each_change(store, tmp_path):
    f = tmp_path / "x.conf"
    for turn, text in (("t-1", "one\n"), ("t-2", "two\n")):
        token = current_turn.set(turn)
        try:
            _write(store, f, text)
        finally:
            current_turn.reset(token)

    history = store.state_history(f"file:{f}", FILE_CONTENT_PREDICATE)
    assert [t.turn_id for t in history] == ["t-1", "t-2"]


class TestTheStateMachineSetsIt:
    """The wiring. A ContextVar nobody sets is a field that is always None."""

    def test_starting_a_turn_puts_its_id_in_scope(self):
        from halbert_core.agents.state_machine import AgentStateMachine

        machine = AgentStateMachine(llm_client=None, tool_executor=None)
        assert current_turn.get() is None

        machine._enter_turn_scope("turn-9")
        try:
            assert current_turn.get() == "turn-9"
        finally:
            machine._leave_turn_scope()

    def test_leaving_restores_what_was_there_before(self):
        """Turns nest in tests and in a confirmation resume. Setting the var
        without keeping the token leaks the id into whatever runs next,
        which would put a later write on an earlier turn."""
        from halbert_core.agents.state_machine import AgentStateMachine

        machine = AgentStateMachine(llm_client=None, tool_executor=None)
        outer = current_turn.set("outer")
        try:
            machine._enter_turn_scope("inner")
            machine._leave_turn_scope()
            assert current_turn.get() == "outer"
        finally:
            current_turn.reset(outer)

    def test_leaving_without_entering_is_not_an_error(self):
        """_end_turn runs from an outer finally that may fire for a turn that
        was abandoned before it ever began."""
        from halbert_core.agents.state_machine import AgentStateMachine

        machine = AgentStateMachine(llm_client=None, tool_executor=None)
        machine._leave_turn_scope()  # must not raise
        assert current_turn.get() is None
