# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-12 Phases B and C: compaction that writes something, under guards.

- **A16-G1 + bug 1** -- ``compact_boundaries`` shipped with a schema, an
  index and NO WRITER, and the typed tree columns were never populated.
  A long thread grew until its history was truncated by whatever budget
  it hit, and the part that fell off was the part that had scrolled away
  -- exactly what a person expects to be remembered.
- **FD-3** -- deterministic v0, no model. The summary extracts the exact
  command, path and error strings rather than composing a paraphrase:
  "it failed with permission denied on /etc/nginx/nginx.conf" is the
  fact, and "there was a permissions problem" is not the same sentence.
- **A16-G6 / A16-G10** -- the guards. Cooldown, merge-max, futility,
  empty summary and clock jump: each answers a way a rotation loop eats
  itself, and each REFUSES with a reason, because a rotation that
  quietly does not happen is indistinguishable from one that happened
  and lost everything.
- **A16-G3** -- ``context_included`` had no writer and no reader, so
  nothing could answer "did the model see this when it answered?".
"""

import time

import pytest

from halbert_core.continuity.rotation import (
    COOLDOWN_SECONDS,
    MAX_GENERATION,
    RotationPlan,
    RotationRefusal,
    build_summary,
    plan_rotation,
)


def _messages(n=30, start_id=1):
    """A thread shaped like a real one: a handful of distinct facts, and a
    great deal of output around them.

    That ratio is what makes compaction worth doing. A thread WITHOUT it
    is refused by the progress guard, which is the guard working rather
    than a fixture problem -- and there is a test below for exactly that.
    """
    out = []
    noise = "\n".join(
        "  reading configuration block %d ... ok" % j for j in range(20))
    for i in range(n):
        out.append({
            "id": start_id + i,
            "role": "assistant",
            "content": (
                "$ systemctl restart nginx\n"
                + noise + "\n"
                "Exit code 1\n"
                "error: permission denied on /etc/nginx/nginx.conf\n"
            ),
        })
    return out


# ---------------------------------------------------------------------------
# FD-3: deterministic, and it keeps the strings
# ---------------------------------------------------------------------------

def test_the_summary_keeps_the_exact_command():
    summary = build_summary(_messages(3), generation=1)
    assert "systemctl restart nginx" in summary


def test_the_summary_keeps_the_exact_path():
    assert "/etc/nginx/nginx.conf" in build_summary(_messages(3), 1)


def test_the_summary_keeps_the_error_text():
    assert "permission denied" in build_summary(_messages(3), 1)


def test_the_summary_names_its_generation():
    assert "generation 2" in build_summary(_messages(3), 2)


def test_the_summary_is_deterministic():
    messages = _messages(5)
    assert build_summary(messages, 1) == build_summary(messages, 1)


def test_nothing_worth_keeping_summarises_to_nothing():
    assert build_summary([{"id": 1, "content": "ok thanks"}], 1) == ""


def test_there_is_no_model_in_the_writer():
    """FD-3: deterministic v0 now, the LLM summary deferred to R5."""
    import inspect

    import halbert_core.continuity.rotation as rotation

    source = inspect.getsource(rotation)
    for forbidden in ("llm", "call_llm_chat", "resolve_aux_model", "chat("):
        assert forbidden not in source.lower().replace("the llm summary", "")


# ---------------------------------------------------------------------------
# A16-G6 / G10: the guards, each refusing with a reason
# ---------------------------------------------------------------------------

def test_a_short_thread_is_not_rotated():
    result = plan_rotation("t1", _messages(5))
    assert isinstance(result, RotationRefusal)
    assert result.reason == "nothing_to_rotate"


def test_a_thread_just_rotated_waits():
    now = 1_000_000.0
    result = plan_rotation(
        "t1", _messages(30), last_rotated_at=now - 10, now=now)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "cooldown"


def test_the_cooldown_expires():
    now = 1_000_000.0
    result = plan_rotation(
        "t1", _messages(30),
        last_rotated_at=now - COOLDOWN_SECONDS - 1, now=now)
    assert isinstance(result, RotationPlan)


def test_a_backwards_clock_is_not_a_licence_to_rotate():
    now = 1_000_000.0
    result = plan_rotation(
        "t1", _messages(30), last_rotated_at=now + 500, now=now)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "clock_jump"


def test_a_forward_clock_jump_refuses_too():
    now = 1_000_000.0
    result = plan_rotation(
        "t1", _messages(30), last_rotated_at=now - 100_000, now=now)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "clock_jump"


def test_folding_stops_at_the_generation_limit():
    result = plan_rotation("t1", _messages(30), generation=MAX_GENERATION + 1)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "merge_max"


def test_a_rotation_that_would_not_shrink_anything_is_refused():
    """Short turns that are all facts: the summary is as big as the
    material, so the rotation is churn."""
    messages = [
        {"id": i, "content": f"$ a{i}"} for i in range(1, 40)
    ]
    result = plan_rotation("t1", messages)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "no_progress"


def test_a_thread_of_pleasantries_writes_no_row():
    messages = [{"id": i, "content": "thanks!"} for i in range(1, 40)]
    result = plan_rotation("t1", messages)
    assert isinstance(result, RotationRefusal)
    assert result.reason == "empty_summary"


def test_every_refusal_carries_a_reason_a_person_can_read():
    for result in (
        plan_rotation("t1", _messages(5)),
        plan_rotation("t1", _messages(30), generation=99),
    ):
        assert isinstance(result, RotationRefusal)
        assert result.detail


# ---------------------------------------------------------------------------
# The plan itself
# ---------------------------------------------------------------------------

def test_the_recent_turns_are_preserved_verbatim():
    plan = plan_rotation("t1", _messages(30), keep_recent=10)
    assert len(plan.preserved_message_ids) == 10
    assert plan.preserved_message_ids[-1] == 30


def test_the_covered_turns_end_where_the_preserved_ones_begin():
    plan = plan_rotation("t1", _messages(30), keep_recent=10)
    assert plan.coverage_end_id == 20
    assert plan.covered_message_ids[-1] == 20


def test_the_plan_records_what_it_saved():
    plan = plan_rotation("t1", _messages(30))
    assert plan.pre_chars > plan.post_chars


# ---------------------------------------------------------------------------
# The store side: one transaction, and context_included has both halves
# ---------------------------------------------------------------------------

def _store(tmp_path):
    from halbert_core.agents.conversation_sqlite import SqliteConversationStore

    store = SqliteConversationStore(db_path=str(tmp_path / "c.db"))
    store.create_thread("t1", title="long thread")
    return store


def test_a_rotation_lands_as_one_transaction(tmp_path):
    store = _store(tmp_path)
    ids = []
    for message in _messages(30):
        ids.append(store.append_message(
            thread_id="t1", role="assistant", content=message["content"]))

    live = [dict(m) for m in store.list_messages("t1")]
    plan = plan_rotation("t1", [
        {"id": m["message_id"], "content": m["content"]} for m in live
    ], keep_recent=10)
    boundary_id = store.write_compact_boundary(plan)

    assert boundary_id
    # ``list_messages`` returns hidden rows too; the TIMELINE is what the
    # rotation changed, so read the visible set.
    visible = [m for m in store.list_messages("t1") if m["visible_in_timeline"]]
    # The preserved turns, plus the summary row.
    assert len(visible) == 11
    assert any("compacted generation 1" in str(m["content"]) for m in visible)


def test_the_boundary_is_readable_back(tmp_path):
    store = _store(tmp_path)
    for message in _messages(30):
        store.append_message(
            thread_id="t1", role="assistant", content=message["content"])
    live = [dict(m) for m in store.list_messages("t1")]
    store.write_compact_boundary(plan_rotation("t1", [
        {"id": m["message_id"], "content": m["content"]} for m in live
    ]))
    boundary = store.last_compact_boundary("t1")
    assert boundary["generation"] == 1
    assert boundary["thread_id"] == "t1"


def test_no_boundary_yet_reads_as_none(tmp_path):
    assert _store(tmp_path).last_compact_boundary("t1") is None


def test_context_included_has_a_writer_and_a_reader(tmp_path):
    store = _store(tmp_path)
    mid = store.append_message(thread_id="t1", role="user", content="hello")
    assert store.set_context_included(mid, False) is True
    assert store.context_included(mid) is False
    store.set_context_included(mid, True)
    assert store.context_included(mid) is True
