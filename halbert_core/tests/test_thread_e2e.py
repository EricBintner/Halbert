# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""End to end over the real pieces: AgentStateMachine + ThreadManager +
SqliteConversationStore on a temp database, with a scripted LLM.

Spec §13: "two /message calls, the second sees the first"; pause -> grace ->
close -> receipt indexed; strong recall injects the receipt with no model
tool call. The route is not used (no agent TestClient fixture exists); the
state machine is driven with ``thread_manager=`` exactly as the route does.
"""

from types import SimpleNamespace

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.agents.thread_signals import GRACE_MINUTES
from halbert_core.agents.threads import ThreadManager
from halbert_core.prompts.agent_prompts import AgentPromptBuilder
from halbert_core.tools.executor import ToolExecutor
from halbert_core.tools.safety import ToolSafetyFramework


T0 = 1_750_000_000.0  # fixed epoch: relative dates in hints are deterministic

MSG_1 = "Set up a samba share for the family photos on the NAS"
REPLY_1 = ("I added [photos] to /etc/samba/smb.conf with path=/srv/photos and "
           "restarted smbd. Next, verify the mount from the laptop.")
MSG_2 = "Can you also make that share read-only for guests?"
REPLY_2 = "Set read only = yes under [photos] and restarted smbd."
MSG_3 = "Different topic: set up a nightly cron job that rotates the nginx logs"
REPLY_3 = "Added /etc/cron.daily/nginx-rotate calling logrotate."
MSG_4 = "Add another samba share for the scanner, same as we did for the photos one"
REPLY_4 = "Added [scanner] at /srv/scanner the same way as [photos]."

NEW_THREAD_TITLE = "Nightly nginx log rotation"


def _tool_call(name, args):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))


def _plain():
    return SimpleNamespace(content="", tool_calls=None, plan=None)


class ScriptedLLM:
    """Records every prompt it is given, tagged with the current turn.

    ``script[turn]`` is a list of chat() responses handed out in order for
    that turn; when it runs dry chat() returns a plain no-tool response.
    ``replies[turn]`` is the single chunk stream() yields.
    """

    def __init__(self):
        self.turn = 0
        self.script = {}
        self.replies = {}
        self.chat_prompts = []    # (turn, prompt)
        self.stream_prompts = []  # (turn, prompt)

    async def chat(self, messages, tools=None, **kwargs):
        prompt = messages[-1]["content"]
        self.chat_prompts.append((self.turn, prompt))
        queued = self.script.get(self.turn) or []
        if queued:
            return queued.pop(0)
        return _plain()

    async def stream(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.stream_prompts.append((self.turn, prompt))
        yield self.replies.get(self.turn, "ok")

    def planning_prompt(self, turn):
        return "\n".join(p for t, p in self.chat_prompts if t == turn)

    def responding_prompt(self, turn):
        return "\n".join(p for t, p in self.stream_prompts if t == turn)


def _tid(thread):
    return thread.get("thread_id") or thread.get("id")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clock():
    return {"now": T0}


@pytest.fixture
def store(tmp_path):
    s = SqliteConversationStore(str(tmp_path / "threads.db"))
    yield s
    s.close()


@pytest.fixture
def tm(store, clock):
    return ThreadManager(store, now=lambda: clock["now"])


@pytest.fixture
def llm():
    return ScriptedLLM()


@pytest.fixture
def agent(llm):
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        prompt_builder=AgentPromptBuilder(),
        max_loops=2,
    )


async def _turn(agent, llm, tm, n, message, reply):
    llm.turn = n
    llm.replies[n] = reply
    events = []
    async for event in agent.process(message, session_id=f"sess-{n}", thread_manager=tm):
        events.append(event)
    types = [e.type for e in events]
    assert "session_started" in types
    assert "response_complete" in types, types
    assert "session_ended" in types
    return events


async def _three_turns(agent, llm, tm, store):
    """Two turns on the Samba subject, then a model-declared switch."""
    await _turn(agent, llm, tm, 1, MSG_1, REPLY_1)
    await _turn(agent, llm, tm, 2, MSG_2, REPLY_2)
    first_id = _tid(store.current_open_thread())
    llm.script[3] = [SimpleNamespace(
        content="",
        tool_calls=[_tool_call("new_thread", {
            "title": NEW_THREAD_TITLE, "reason": "subject changed",
        })],
        plan=None,
    )]
    ev3 = await _turn(agent, llm, tm, 3, MSG_3, REPLY_3)
    started = [e for e in ev3 if e.type == "thread_started"]
    assert len(started) == 1, [e.type for e in ev3]
    return first_id, started[0].data["thread_id"], ev3


# ---------------------------------------------------------------------------
# (1) the second message sees the first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_second_message_sees_the_first(agent, llm, tm, store):
    ev1 = await _turn(agent, llm, tm, 1, MSG_1, REPLY_1)
    assert "turn_persisted" in [e.type for e in ev1]
    persisted = next(e for e in ev1 if e.type == "turn_persisted")
    assert persisted.data["thread_id"]
    assert persisted.data["turn_id"]

    await _turn(agent, llm, tm, 2, MSG_2, REPLY_2)

    # PLANNING on turn 2 carries the continuity hint; the thread is titled
    # from the first message, so the first exchange's text is in the prompt.
    planning_2 = llm.planning_prompt(2)
    assert "<continuity>" in planning_2, planning_2
    assert "family photos" in planning_2, planning_2
    assert planning_2.index("<continuity>") < planning_2.index("## Current Task")

    # RESPONDING on turn 2 sees the raw first exchange as history
    responding_2 = llm.responding_prompt(2)
    assert "## Earlier in this conversation" in responding_2, responding_2
    assert "/etc/samba/smb.conf" in responding_2
    assert "family photos" in responding_2

    # turn 1 did not see anything (nothing to see)
    assert "Earlier in this conversation" not in llm.responding_prompt(1)

    # storage: one open thread, four rows in order, all complete
    open_thread = store.current_open_thread()
    assert open_thread is not None and open_thread["status"] == "open"
    assert [_tid(t) for t in store.list_threads(status="open")] == [_tid(open_thread)]
    rows = store.recent_messages(_tid(open_thread), limit=12)
    assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]
    assert [r["content"] for r in rows] == [MSG_1, REPLY_1, MSG_2, REPLY_2]
    turns = store.list_turns(limit=10)
    assert len(turns) == 2
    assert all(t["user"]["status"] == "complete" for t in turns)
    assert all(t["assistant"]["status"] == "complete" for t in turns)
    assert turns[0]["user"]["content"] == MSG_1
    assert turns[1]["assistant"]["content"] == REPLY_2


# ---------------------------------------------------------------------------
# (2) new_thread from the model pauses the old thread and opens a new one
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_thread_tool_pauses_old_and_opens_new(agent, llm, tm, store):
    first_id, new_id, ev3 = await _three_turns(agent, llm, tm, store)
    types = [e.type for e in ev3]

    # handled inline: no tool card, no error, PLANNING re-ran once
    assert "tool_start" not in types
    assert "tool_complete" not in types
    assert "error" not in types
    assert len([t for t, _ in llm.chat_prompts if t == 3]) == 2

    started = next(e for e in ev3 if e.type == "thread_started")
    assert new_id != first_id
    assert started.data["title"] == NEW_THREAD_TITLE
    assert started.data["previous_thread_id"] == first_id

    old = store.get_thread(first_id)
    assert old["status"] == "paused"
    assert old["paused_at"] == T0
    new = store.get_thread(new_id)
    assert new["status"] == "open"
    assert new["title"] == NEW_THREAD_TITLE
    assert new["title_source"] == "model"
    assert [_tid(t) for t in store.list_threads(status="open")] == [new_id]

    # the switching turn belongs to the new thread; the old one keeps its four rows
    assert [r["content"] for r in store.recent_messages(new_id, limit=12)] == [MSG_3, REPLY_3]
    assert len(store.recent_messages(first_id, limit=12)) == 4


# ---------------------------------------------------------------------------
# (3) tick past the grace window closes the paused thread; recall finds it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tick_after_grace_closes_old_thread_and_recall_finds_it(
    agent, llm, tm, store, clock
):
    first_id, new_id, _ = await _three_turns(agent, llm, tm, store)

    # inside the grace window nothing closes
    assert tm.tick() == []
    assert store.get_thread(first_id)["status"] == "paused"

    clock["now"] = T0 + GRACE_MINUTES * 60 + 60
    closed = tm.tick()
    assert closed == [first_id]

    old = store.get_thread(first_id)
    assert old["status"] == "closed"
    assert old["receipt"].startswith("Title:")
    assert "Started with:" in old["receipt"]
    assert "Open loop:" in old["receipt"]
    assert "samba" in old["receipt"].lower()
    assert old["receipt_updated_at"] is not None

    hits = store.search_receipts("samba")
    assert [h["thread_id"] for h in hits] == [first_id]
    assert hits[0]["status"] == "closed"

    recalled = tm.recall("samba")
    assert recalled, "recall('samba') found nothing"
    assert recalled[0]["thread_id"] == first_id
    assert "samba" in recalled[0]["receipt"].lower()
    assert recalled[0]["title"]
    assert recalled[0]["date"]

    # idempotent; the open thread is untouched
    assert tm.tick() == []
    assert store.get_thread(new_id)["status"] == "open"
    assert _tid(tm.current()) == new_id


# ---------------------------------------------------------------------------
# (4) a past reference pulls the closed thread in with no model tool call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_past_reference_pulls_in_closed_thread_without_a_tool_call(
    agent, llm, tm, store, clock
):
    first_id, new_id, _ = await _three_turns(agent, llm, tm, store)
    clock["now"] = T0 + GRACE_MINUTES * 60 + 60
    assert tm.tick() == [first_id]

    ev4 = await _turn(agent, llm, tm, 4, MSG_4, REPLY_4)
    types = [e.type for e in ev4]

    # deterministic recall: no tool, no new thread, exactly one chat() call
    assert "tool_start" not in types
    assert "thread_started" not in types
    assert len([t for t, _ in llm.chat_prompts if t == 4]) == 1
    recalled = [e for e in ev4 if e.type == "thread_recalled"]
    assert len(recalled) == 1, types
    assert recalled[0].data["thread_id"] == first_id
    assert recalled[0].data["mode"] == "auto"
    assert "samba" in [t.lower() for t in recalled[0].data["match_terms"]]

    planning_4 = llm.planning_prompt(4)
    assert "<continuity>" in planning_4, planning_4
    assert "Pulled in:" in planning_4, planning_4
    assert "samba" in planning_4.lower()
    assert planning_4.index("Pulled in:") < planning_4.index("## Current Task")
    # the same block reaches RESPONDING
    assert "Pulled in:" in llm.responding_prompt(4)

    # persisted on the open thread; the closed thread stays closed (no reopen)
    open_thread = store.get_thread(new_id)
    assert open_thread["status"] == "open"
    assert [r["thread_id"] for r in open_thread["recalled_json"]] == [first_id]
    assert open_thread["recalled_json"][0]["status"] == "accepted"
    assert store.get_thread(first_id)["status"] == "closed"
    assert [r["content"] for r in store.recent_messages(new_id, limit=12)] == [
        MSG_3, REPLY_3, MSG_4, REPLY_4,
    ]

    # retracting the recall is recorded, not deleted
    assert tm.retract_recall(new_id, first_id) is True
    assert store.get_thread(new_id)["recalled_json"][0]["status"] == "retracted"
