"""Tests for ConversationStatus enum + ConversationStatusMachine (A2a)."""

import pytest

from halbert_core.agents.states import ConversationStatus
from halbert_core.agents.conversation_status import ConversationStatusMachine


class TestConversationStatusEnum:
    def test_terminal_states(self):
        terminal = ConversationStatus.terminal()
        assert ConversationStatus.SUCCESS in terminal
        assert ConversationStatus.ERROR in terminal
        assert ConversationStatus.CANCELLED in terminal
        assert ConversationStatus.IN_PROGRESS not in terminal

    def test_is_terminal(self):
        assert ConversationStatus.SUCCESS.is_terminal() is True
        assert ConversationStatus.IN_PROGRESS.is_terminal() is False
        assert ConversationStatus.BLOCKED.is_terminal() is False


class TestConversationStatusMachine:
    def test_initial_status_is_in_progress(self):
        m = ConversationStatusMachine()
        assert m.current() == ConversationStatus.IN_PROGRESS
        assert m.is_terminal() is False

    def test_valid_transition_to_blocked_stores_action(self):
        m = ConversationStatusMachine()
        action = {"action_id": "a1", "tool": "rm", "risk": "high"}
        m.transition(ConversationStatus.BLOCKED, blocked_action=action)
        assert m.current() == ConversationStatus.BLOCKED
        assert m.blocked_action() == action

    def test_blocked_to_in_progress_clears_action(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.BLOCKED, blocked_action={"action_id": "a1"})
        m.transition(ConversationStatus.IN_PROGRESS)
        assert m.current() == ConversationStatus.IN_PROGRESS
        assert m.blocked_action() is None

    def test_blocked_to_cancelled_on_rejection(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.BLOCKED, blocked_action={"action_id": "a1"})
        m.transition(ConversationStatus.CANCELLED)
        assert m.current() == ConversationStatus.CANCELLED
        assert m.is_terminal() is True

    def test_waiting_for_events_stores_subagent_id(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.WAITING_FOR_EVENTS, waiting_for="sub-123")
        assert m.current() == ConversationStatus.WAITING_FOR_EVENTS
        assert m.waiting_for() == "sub-123"

    def test_waiting_for_events_to_in_progress_clears(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.WAITING_FOR_EVENTS, waiting_for="sub-123")
        m.transition(ConversationStatus.IN_PROGRESS)
        assert m.waiting_for() is None

    def test_transient_error_increments_retry_count(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.TRANSIENT_ERROR)
        m.transition(ConversationStatus.IN_PROGRESS)
        m.transition(ConversationStatus.TRANSIENT_ERROR)
        assert m.retry_count == 2

    def test_transient_error_to_error_on_max_retries(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.TRANSIENT_ERROR)
        m.transition(ConversationStatus.ERROR)
        assert m.current() == ConversationStatus.ERROR
        assert m.is_terminal() is True

    def test_in_progress_to_success(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.SUCCESS)
        assert m.current() == ConversationStatus.SUCCESS
        assert m.is_terminal() is True

    def test_invalid_transition_raises(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.SUCCESS)
        with pytest.raises(ValueError):
            m.transition(ConversationStatus.IN_PROGRESS)  # terminal -> anything

    def test_invalid_edge_raises(self):
        m = ConversationStatusMachine()
        # IN_PROGRESS cannot go directly to... actually it can go to ERROR.
        # Test a genuinely invalid edge: BLOCKED -> WAITING_FOR_EVENTS
        m.transition(ConversationStatus.BLOCKED, blocked_action={"x": 1})
        with pytest.raises(ValueError):
            m.transition(ConversationStatus.WAITING_FOR_EVENTS)

    def test_idempotent_same_status_noop(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.IN_PROGRESS)  # no-op, no raise
        assert m.current() == ConversationStatus.IN_PROGRESS

    def test_to_dict_serializable(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.WAITING_FOR_EVENTS, waiting_for="sub-1")
        d = m.to_dict()
        assert d["status"] == "waiting_for_events"
        assert d["waiting_for"] == "sub-1"
        assert d["terminal"] is False

    def test_reset(self):
        m = ConversationStatusMachine()
        m.transition(ConversationStatus.TRANSIENT_ERROR)
        m.reset()
        assert m.current() == ConversationStatus.IN_PROGRESS
        assert m.retry_count == 0
        assert m.blocked_action() is None