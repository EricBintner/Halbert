# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-12 — the session tree, wired to the turn loop.

T1 shipped ``move_leaf`` with a docstring that says it plainly: "T1 ships
the primitive unwired: no caller in this repo uses it yet". T3 shipped the
rotation writer the same way. Both halves were built, reviewed and merged;
neither was ever called. That is the defect shape the whole OSS pass exists
to stop recreating — *module ported, consumer never wired* — and it survived
two packets in the tree that was auditing it.

What the wiring needs first is Phase A, because ``move_leaf`` cannot be
trusted with a tree whose typed columns nothing writes:

- **bug 1** — ``_open_new_thread`` recorded provenance in ``metadata`` and
  never passed ``parent_thread_id``, so every row is ``parent_thread_id
  NULL / edge_kind 'root'``. ``move_leaf`` stamps parent and edge exactly
  when the column is NULL, so the first real move would stamp the *wrong*
  parent — permanently, since rows never re-parent — and the column and the
  metadata would disagree forever.
- **bug 3** — ``_reopen_thread`` trusts the caller's ``from_thread_id``,
  which ``new_thread`` was already fixed not to (A6b). With the one-leaf
  index that stale belief is no longer a logic bug: the reopen raises
  IntegrityError and the admin is told a perfectly resumable thread could
  not be resumed.
- **G5** — an interrupted turn left a bare user row with nothing after it.
- **G2** — and nothing anywhere carried the question it had asked.
"""

from datetime import datetime

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.threads import ThreadManager
from halbert_core.intake.signals import analyze_message

NOW = datetime(2026, 9, 10, 12, 0).timestamp()


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture()
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


@pytest.fixture()
def clock():
    return Clock(NOW)


@pytest.fixture()
def mgr(store, clock):
    m = ThreadManager(store, now=clock)
    m.clock = clock
    return m


def _begin(mgr, text, session="s"):
    return mgr.begin_turn(text, analyze_message(text), session)


def _turn(mgr, text, assistant="ok", session="s", status="complete", thread_id=None):
    turn = _begin(mgr, text, session)
    mgr.end_turn(
        turn, assistant_text=assistant, blocks=[], terminal_block_ids=[],
        diff_proposals=[], status=status, thread_id_override=thread_id,
    )
    return turn


def _root(mgr):
    """Open the first thread the way a conversation does — by speaking."""
    _turn(mgr, "the camera keeps dropping frames", assistant="Looking at it.")
    return mgr.current()["thread_id"]


def _open_leaf(store):
    t = store.current_open_thread()
    return t["thread_id"] if t else None


# ---------------------------------------------------------------------------
# bug 1 — the typed columns, written by the writer that knows the answer
# ---------------------------------------------------------------------------

class TestTheTreeColumnsAreWritten:
    def test_a_switch_stamps_parent_and_edge_on_the_row(self, store, mgr):
        first = _root(mgr)
        second = mgr.new_thread("Camera", "topic switch", from_thread_id=first)
        row = store.get_thread(second)
        assert row["parent_thread_id"] == first, "the column is still NULL"
        assert row["edge_kind"] != "root", "every thread claims to be a root"

    def test_the_column_and_the_metadata_agree(self, store, mgr):
        """The disagreement is the damage, not the missing column.

        ``_predecessor_id`` prefers metadata; the §2.1 path projection walks
        the column. While one is NULL they cannot contradict each other —
        the moment ``move_leaf`` stamps one, they can, and 'rows never
        re-parent' means nothing repairs it.
        """
        first = _root(mgr)
        second = mgr.new_thread("Camera", "topic switch", from_thread_id=first)
        row = store.get_thread(second)
        assert row["parent_thread_id"] == (row["metadata"] or {}).get(
            "previous_thread_id"
        )

    def test_the_first_thread_is_a_root(self, store, mgr):
        first = _root(mgr)
        row = store.get_thread(first)
        assert row["parent_thread_id"] is None
        assert row["edge_kind"] == "root"


# ---------------------------------------------------------------------------
# bug 3 — resume resolves the real leaf, the way new_thread already does
# ---------------------------------------------------------------------------

class TestResumeResolvesTheRealLeaf:
    def test_a_stale_from_thread_id_still_resumes(self, store, mgr):
        first = _root(mgr)
        second = mgr.new_thread("Camera", "switch", from_thread_id=first)
        assert _open_leaf(store) == second

        # What the store-outage path hands the tool bridge: a uuid4 no row
        # backs. Today this pauses nothing, the leaf stays open, and the
        # target's status='open' UPDATE violates idx_one_open_leaf.
        assert mgr.resume_thread(first, from_thread_id="deadbeef" * 4) is True
        assert _open_leaf(store) == first
        assert store.get_thread(second)["status"] == "paused"

    def test_one_leaf_survives_a_stale_resume(self, store, mgr):
        first = _root(mgr)
        second = mgr.new_thread("Camera", "switch", from_thread_id=first)
        mgr.resume_thread(first, from_thread_id="deadbeef" * 4)
        opens = [
            t for t in store.list_threads(limit=50) if t.get("status") == "open"
        ]
        assert len(opens) == 1, f"{len(opens)} open leaves"
        assert second is not None


# ---------------------------------------------------------------------------
# G5 — an interrupted turn leaves a fact behind
# ---------------------------------------------------------------------------

class TestAnInterruptedTurnSaysSo:
    def test_a_cut_turn_leaves_a_row(self, store, mgr):
        turn = _turn(mgr, "delete the old backups in /Volumes/old",
                     assistant="", status="interrupted")
        rows = store.recent_messages(turn.thread_id, limit=10)
        assert rows, "no rows at all"
        assert rows[-1]["role"] != "user", (
            "the transcript ends on an unanswered question with nothing "
            "saying it was cut"
        )

    def test_the_next_turn_does_not_see_two_bare_questions(self, store, mgr):
        """The failure a local model turns into an action.

        [user: delete the old backups…, user: what time is it?] reads as one
        request still outstanding. A model that answers the first one stages
        the deletion again.
        """
        _turn(mgr, "delete the old backups in /Volumes/old",
              assistant="", status="interrupted")
        _turn(mgr, "delete the old backups now please",
              assistant="Which ones did you mean?")
        third = _begin(mgr, "the old backups on the array")
        roles = [h["role"] for h in third.history]
        doubled = [
            i for i in range(len(roles) - 1)
            if roles[i] == "user" and roles[i + 1] == "user"
        ]
        assert not doubled, f"two consecutive user rows: {roles}"

    def test_a_completed_turn_gets_no_marker(self, store, mgr):
        turn = _turn(mgr, "what time is it?", assistant="Half past four.")
        rows = store.recent_messages(turn.thread_id, limit=10)
        assert rows[-1]["content"] == "Half past four."


# ---------------------------------------------------------------------------
# G2 — the question that was never answered is carried
# ---------------------------------------------------------------------------

class TestTheUnresolvedRequestIsCarried:
    def test_the_store_can_name_it(self, store, mgr):
        turn = _turn(mgr, "rotate the nginx logs and then tell me the disk usage",
                     assistant="", status="interrupted")
        assert "rotate the nginx logs" in (
            store.unresolved_request(turn.thread_id) or ""
        )

    def test_an_answered_question_is_not_unresolved(self, store, mgr):
        turn = _turn(mgr, "what time is it?", assistant="Half past four.")
        assert not store.unresolved_request(turn.thread_id)

    def test_it_survives_the_history_window(self, store, mgr):
        """The whole point: it outlives the rows that carried it.

        The cut turn is deliberately *not* the first one, so a receipt that
        happens to quote the thread's opening line cannot pass this by
        accident — "Started with" is a different fact.
        """
        opening = _turn(mgr, "the nginx logs are getting large",
                        assistant="They are, about 4 GB.")
        thread_id = opening.thread_id
        _turn(mgr, "rotate the nginx logs and then tell me the disk usage",
              assistant="", status="interrupted", thread_id=thread_id)
        for i in range(13):
            _turn(mgr, f"and what about the nginx error log, round {i}",
                  assistant=f"answer {i}", thread_id=thread_id)
        receipt = store.get_thread(thread_id).get("receipt") or ""
        assert "Started with: the nginx logs are getting large" in receipt
        assert "rotate the nginx logs" in receipt, (
            "the ask scrolled out of the window and nothing kept it"
        )

    def test_a_rotation_records_it_on_the_boundary(self, store, mgr):
        turn = _turn(mgr, "rotate the nginx logs", assistant="",
                     status="interrupted")

        class _Plan:
            thread_id = turn.thread_id
            generation = 1
            summary = "$ nginx -t\nExit code 0"
            covered_message_ids = ()
            preserved_message_ids = ()
            coverage_end_id = 1
            pre_chars = 100
            post_chars = 20
            trigger = "budget"
            trigger_detail = ""

        assert store.write_compact_boundary(_Plan()) is not None
        row = store.last_compact_boundary(turn.thread_id)
        assert "rotate the nginx logs" in (row["unresolved_request"] or ""), (
            "the column has a schema, an index and still no writer"
        )


# ---------------------------------------------------------------------------
# The wiring the opus batch named and could not do
# ---------------------------------------------------------------------------

class TestTheLeafMovesThroughMoveLeaf:
    """A topic switch mints the branch summaries, because it goes through
    the one transaction that mints them."""

    def _branch_rows(self, store, thread_id):
        return [
            m for m in store.list_messages(thread_id)
            if (m.get("origin") or "") == "branch"
        ]

    def test_a_switch_mints_a_departure_row(self, store, mgr):
        first = _root(mgr)
        mgr.new_thread("Disks", "topic switch", from_thread_id=first)
        assert self._branch_rows(store, first), (
            "the thread that was left was never told it was left"
        )

    def test_a_return_mints_a_return_row(self, store, mgr):
        first = _root(mgr)
        second = mgr.new_thread("Disks", "topic switch", from_thread_id=first)
        _turn(mgr, "how full is the array", assistant="Eighty percent.")
        mgr.resume_thread(first, from_thread_id=second)
        assert self._branch_rows(store, first), "no return row on the thread returned to"

    def test_a_thread_nobody_spoke_in_is_not_told_it_was_left(self, store, mgr):
        """One of ``move_leaf``'s two deliberate silences.

        There is no subject there to have been interrupted, so a divider
        above nothing reconciles nothing.
        """
        assert store.create_thread("empty-leaf", "Nothing yet", status="open")
        mgr.new_thread("Disks", "topic switch", from_thread_id="empty-leaf")
        assert not self._branch_rows(store, "empty-leaf")
        assert store.get_thread("empty-leaf")["status"] == "paused"


class TestTheRotationWriterHasACaller:
    def test_a_long_thread_rotates(self, store, mgr, clock):
        """Enough turns with real commands in them, and the thread folds.

        The guards in ``plan_rotation`` are the interesting part of this
        test passing: cooldown, merge-max, progress ratio and the
        empty-summary refusal all have to let it through for a boundary to
        appear at all.
        """
        turn = _turn(mgr, "start", assistant="ok")
        thread_id = turn.thread_id
        for i in range(40):
            clock.advance(600)
            _turn(
                mgr, f"check {i} on /var/log/nginx/access.log",
                assistant=(
                    f"$ tail -n 100 /var/log/nginx/access.log\n"
                    f"Exit code 0\nline {i} " + ("padding " * 40)
                ),
                thread_id=thread_id,
            )
        assert store.last_compact_boundary(thread_id) is not None, (
            "forty turns and the rotation writer was never called"
        )

    def test_a_short_thread_does_not(self, store, mgr):
        turn = _turn(mgr, "hello", assistant="hello")
        assert store.last_compact_boundary(turn.thread_id) is None


# ---------------------------------------------------------------------------
# The create_thread message, which sent operators to look for the wrong thing
# ---------------------------------------------------------------------------

def test_a_one_leaf_violation_is_not_reported_as_a_duplicate_id(store, mgr, caplog):
    _root(mgr)  # something is open
    with caplog.at_level("WARNING"):
        assert store.create_thread("NEWID", "Beta") is False
    text = caplog.text
    assert "NEWID already exists" not in text, (
        "the log sends the operator to look for a duplicate id that does "
        "not exist, instead of at the open leaf"
    )
