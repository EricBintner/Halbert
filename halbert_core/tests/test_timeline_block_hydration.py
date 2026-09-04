# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The timeline renders a stored command the way the live stream did.

Live, a fast command settles into `$ smbstatus · exit 1 · 0.3s`. After a
reload the timeline had only the stored tool block -- tool, args, result,
exit, execution_id -- so the same turn came back as a generic card with the
raw result underneath, and its terminal ids rendered as "terminal · ended"
chips. Two renderings of one turn, decided by whether the page had been
refreshed.

Everything needed was already stored: the terminal_blocks row holds the exit
code, both halves of the output, and the timestamps. It was never joined to
the tool block that ran it. Now it is, by execution_id.
"""

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from halbert_core.agents.conversation_sqlite import SqliteConversationStore  # noqa: E402
from halbert_core.agents.threads import ThreadManager  # noqa: E402
from halbert_core.intake.signals import analyze_message  # noqa: E402
import halbert_core.dashboard.routes.agent as agent_routes  # noqa: E402


@pytest.fixture
def tm():
    store = SqliteConversationStore(":memory:")
    yield ThreadManager(store)
    store.close()


@pytest.fixture
def client(monkeypatch, tm):
    monkeypatch.setattr(agent_routes, "_thread_manager", lambda: tm)
    monkeypatch.setattr(agent_routes, "_agent_instance", None)
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


def _terminal_block(store, block_id, **over):
    row = {
        "block_id": block_id,
        "session_id": "term-1",
        "thread_id": None,
        "turn_id": None,
        "command": "smbstatus",
        "cwd": None,
        "owner": "agent",
        "interactive": 0,
        "remote": 0,
        "redacted": 0,
        "started_at": 100.0,
        "ended_at": 100.34,
        "exit_code": 1,
        "output_head": "no shares",
        "output_tail": "no shares",
        "execution_id": None,
    }
    row.update(over)
    store.insert_terminal_block(row)


def _turn_with_command(tm, *, command="smbstatus", exec_id="exec-1", block_id="blk-1"):
    _terminal_block(tm.store, block_id, command=command)
    turn = tm.begin_turn("check the shares", analyze_message("check the shares"), "s1")
    tm.end_turn(
        turn,
        assistant_text="nothing is shared",
        blocks=[{
            "tool": "run_command",
            "args": {"command": command},
            "result": "Exit code 1\nno shares",
            "exit": 1,
            "execution_id": exec_id,
            "status": "success",
            "error": None,
        }],
        terminal_block_ids=[block_id],
        diff_proposals=[],
        block_executions={block_id: exec_id},
    )
    return turn


def test_a_stored_command_comes_back_with_its_blocks_result(client, tm):
    _turn_with_command(tm)

    turn = client.get("/api/agent/timeline").json()["turns"][0]
    block = turn["blocks"][0]

    assert block["block_id"] == "blk-1"
    assert block["exit"] == 1
    assert block["duration"] == pytest.approx(0.34, abs=0.001)
    assert block["output_head"] == "no shares"
    assert block["output_tail"] == "no shares"


def test_a_tool_that_never_ran_a_command_is_untouched(client, tm):
    turn = tm.begin_turn("read it", analyze_message("read it"), "s1")
    tm.end_turn(
        turn,
        assistant_text="here",
        blocks=[{
            "tool": "read_file",
            "args": {"path": "/etc/fstab"},
            "result": "contents",
            "exit": None,
            "execution_id": "exec-9",
            "status": "success",
            "error": None,
        }],
        terminal_block_ids=[],
        diff_proposals=[],
    )

    block = client.get("/api/agent/timeline").json()["turns"][0]["blocks"][0]
    assert "block_id" not in block
    assert "duration" not in block
    assert block["result"] == "contents"


def test_a_block_still_running_reports_no_duration(client, tm):
    _terminal_block(tm.store, "blk-1", ended_at=None, exit_code=None)
    turn = tm.begin_turn("build it", analyze_message("build it"), "s1")
    tm.end_turn(
        turn, assistant_text="running", blocks=[{
            "tool": "run_command", "args": {"command": "npm run build"},
            "result": "", "exit": None, "execution_id": "exec-1",
            "status": "success", "error": None,
        }],
        terminal_block_ids=["blk-1"], diff_proposals=[],
        block_executions={"blk-1": "exec-1"},
    )

    block = client.get("/api/agent/timeline").json()["turns"][0]["blocks"][0]
    assert block["block_id"] == "blk-1"
    # A duration of 0.0 would read as "it finished instantly".
    assert block.get("duration") is None


def test_two_commands_in_one_turn_do_not_swap_results(client, tm):
    _terminal_block(tm.store, "blk-1", command="ls", output_head="A", output_tail="A", exit_code=0, ended_at=100.1)
    _terminal_block(tm.store, "blk-2", command="df", output_head="B", output_tail="B", exit_code=2, ended_at=100.9)
    turn = tm.begin_turn("two things", analyze_message("two things"), "s1")
    tm.end_turn(
        turn, assistant_text="done",
        blocks=[
            {"tool": "run_command", "args": {"command": "ls"}, "result": "A",
             "exit": 0, "execution_id": "exec-1", "status": "success", "error": None},
            {"tool": "run_command", "args": {"command": "df"}, "result": "B",
             "exit": 2, "execution_id": "exec-2", "status": "success", "error": None},
        ],
        terminal_block_ids=["blk-1", "blk-2"], diff_proposals=[],
        block_executions={"blk-1": "exec-1", "blk-2": "exec-2"},
    )

    blocks = client.get("/api/agent/timeline").json()["turns"][0]["blocks"]
    by_exec = {b["execution_id"]: b for b in blocks}
    assert by_exec["exec-1"]["output_head"] == "A"
    assert by_exec["exec-2"]["output_head"] == "B"
    assert by_exec["exec-2"]["exit"] == 2


def test_a_hydration_failure_does_not_lose_the_page(client, tm, monkeypatch):
    """The turns are the page. Enriching them is an improvement on top, and
    an improvement that fails must not take the conversation with it."""
    _turn_with_command(tm)

    def boom(**kw):
        raise RuntimeError("blocks table gone")

    monkeypatch.setattr(tm.store, "list_terminal_blocks", boom)
    body = client.get("/api/agent/timeline").json()

    assert len(body["turns"]) == 1
    assert body["turns"][0]["blocks"][0]["tool"] == "run_command"
    assert "block_id" not in body["turns"][0]["blocks"][0]
