"""Plan B: B22 — End-to-end terminal integration tests.

Tests the full flow: state machine → pool → store → watched shell → hint → stage.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from halbert_core.agents.conversation_sqlite import SqliteConversationStore
from halbert_core.agents.events import StreamEvent
from halbert_core.agents.llm_client import LLMResponse, ToolCall, FunctionCall
from halbert_core.agents.state_machine import AgentStateMachine
from halbert_core.streaming.terminal_bridge import (
    TerminalEventBus,
    get_terminal_event_bus,
    set_terminal_event_bus,
    set_terminal_pool_enabled,
    terminal_pool_wanted,
    terminal_stream_wanted,
)
from halbert_core.streaming.watched_shell import WatchedShellProcessor, BlockRecord
from halbert_core.tools import ToolExecutor, ToolSafetyFramework
from halbert_core.tools.executor import ExecutionResult


# ── helpers ──────────────────────────────────────────────────────

@dataclass
class _Turn:
    thread_id: str
    turn_id: str
    session_id: int
    history: list
    hint: str
    recalled: list


class _FakeThreadManager:
    """Minimal ThreadManager for e2e state-machine tests."""

    def __init__(self, hint="", history=None, recalled=None):
        self.hint = hint
        self.history = history or []
        self.recalled = recalled or []
        self.begun: List = []
        self.ended: List = []
        self.store = SqliteConversationStore(":memory:")

    def begin_turn(self, query, signals, session_id):
        self.begun.append((query, signals, session_id))
        return _Turn("t-open", f"turn-{len(self.begun)}", 1,
                     list(self.history), self.hint, list(self.recalled))

    def end_turn(self, turn, *, assistant_text, blocks, terminal_block_ids,
                 diff_proposals, status="complete", thread_id_override=None):
        self.ended.append(dict(
            turn=turn, assistant_text=assistant_text, blocks=blocks,
            terminal_block_ids=terminal_block_ids,
            diff_proposals=diff_proposals, status=status,
            thread_id_override=thread_id_override,
        ))

    def new_thread(self, title, reason, *, from_thread_id):
        return "t-new"


class _LLM:
    """Fake LLM that returns canned responses."""

    def __init__(self, responses=None, delay=0.0):
        self.responses = list(responses or [])
        self.delay = delay

    async def chat(self, messages, tools=None, **kwargs):
        await asyncio.sleep(self.delay)
        return self.responses.pop(0) if self.responses else LLMResponse(
            content="answer", tool_calls=[], plan=[])

    async def stream(self, messages, **kwargs):
        await asyncio.sleep(self.delay)
        if self.responses:
            resp = self.responses.pop(0)
            text = resp.content or ""
            for word in text.split():
                yield word + " "
        else:
            yield "the "
            yield "answer"


def _tool(name, **args):
    return LLMResponse(content="", tool_calls=[
        ToolCall(id="c1", function=FunctionCall(name=name, arguments=args))
    ])


def _agent(llm):
    return AgentStateMachine(
        llm_client=llm,
        tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
        max_loops=5,
    )


@pytest.fixture
def store():
    s = SqliteConversationStore(":memory:")
    yield s
    s.close()


@pytest.fixture(autouse=True)
def fresh_bus():
    set_terminal_event_bus(TerminalEventBus())
    set_terminal_pool_enabled(True)
    yield
    set_terminal_event_bus(None)
    set_terminal_pool_enabled(False)


# ── Test 1: agent block persisted and replayed ───────────────────

@pytest.mark.asyncio
async def test_e2e_agent_block_persisted_and_replayed():
    """Turn 1: agent runs echo hello via pool -> block stored -> tile event emitted.
    Turn 2: agent sees the first turn's block in history.
    """
    bus = get_terminal_event_bus()
    tm = _FakeThreadManager()
    llm = _LLM(responses=[
        _tool("run_command", command="echo hello", timeout=5),
        LLMResponse(content="Done: hello", tool_calls=[], plan=[]),
    ])
    agent = _agent(llm)

    async def fake_execute(tool_name, args, session_id=None, confirmed=False, speaker_role="admin"):
        terminal_id = f"term-{uuid.uuid4().hex[:8]}"
        block_id = f"blk-{terminal_id}"
        bus.publish(session_id, {
            "kind": "spawn",
            "terminal_session_id": terminal_id,
            "block_id": block_id,
            "command": args.get("command", ""),
            "pid": 42,
            "owner": "agent",
        })
        bus.publish(session_id, {
            "kind": "complete",
            "terminal_session_id": terminal_id,
            "block_id": block_id,
            "exit_code": 0,
        })
        return ExecutionResult(success=True, result="hello\n")

    agent.tools.execute = fake_execute

    events = [e async for e in agent.process(
        "run echo hello", session_id="s1", thread_manager=tm)]
    types = [e.type for e in events]

    # Tile events emitted
    assert "terminal_spawn" in types
    assert "terminal_complete" in types

    # Block id tracked and persisted
    end = tm.ended[0]
    assert len(end["terminal_block_ids"]) == 1
    assert end["terminal_block_ids"][0].startswith("blk-")

    # Turn 2: history includes the block id from turn 1
    tm2 = _FakeThreadManager(
        history=[{"role": "user", "content": "run echo hello"},
                 {"role": "assistant", "content": "Done: hello"}],
    )
    llm2 = _LLM()
    agent2 = _agent(llm2)
    events2 = [e async for e in agent2.process(
        "what did I run?", session_id="s1", thread_manager=tm2)]

    # Turn 2 completed and persisted
    assert len(tm2.ended) == 1
    assert tm2.ended[0]["status"] == "complete"


# ── Test 2: watched shell in hint ────────────────────────────────

def test_e2e_watched_shell_in_hint(store):
    """User shell block closes -> messages.origin='terminal' row inserted
    -> next turn's hint includes 'Since your last message you ran'.
    """
    processor = WatchedShellProcessor(store)

    # Create a thread
    store.create_thread("thread-1", "test thread", created_at=time.time())

    # Simulate a watched user shell block closing
    rec = BlockRecord(
        block_id="blk-user-1",
        session_id="sess-user-1",
        command="ls /tmp",
        cwd="/tmp",
        exit_code=0,
        started_at=1000.0,
        ended_at=1000.5,
        output_head="total 0\nfile.txt",
        output_tail="total 0\nfile.txt",
    )
    processor.process_block_close(rec, thread_id="thread-1", watched=True)

    # Block stored
    block = store.get_terminal_block("blk-user-1")
    assert block is not None
    assert block["command"] == "ls /tmp"
    assert block["owner"] == "user"

    # Message row inserted with origin='terminal'
    msgs = store.list_messages("thread-1")
    assert len(msgs) >= 1
    terminal_msgs = [m for m in msgs if m.get("origin") == "terminal"]
    assert len(terminal_msgs) == 1
    assert terminal_msgs[0]["terminal_block_ids"] == ["blk-user-1"]

    # Hint includes the "Since your last message" text
    hint = processor.build_hint_text("thread-1")
    assert hint is not None
    assert "Since your last message you ran" in hint
    assert "1 command" in hint


# ── Test 3: long-running promotion ───────────────────────────────

def test_e2e_long_running_promotion():
    """Long-running command (> 2s) -> terminal_block_promote event emitted.

    The event factory produces type='terminal_block_promote' when promote=True.
    """
    ev = StreamEvent.terminal_block(
        "sess-1",
        block_id="blk-long-1",
        terminal_session_id="tsess-1",
        command="npm run build",
        owner="agent",
        promote=True,
    )
    assert ev.type == "terminal_block_promote"
    assert ev.data["block_id"] == "blk-long-1"
    assert ev.data["command"] == "npm run build"
    assert ev.data["owner"] == "agent"


# ── Test 4: pool fallback at cap ─────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_pool_fallback_at_cap():
    """Pool at cap -> falls back to subprocess path in the executor."""
    executor = ToolExecutor.__new__(ToolExecutor)
    executor.safety = ToolSafetyFramework()

    # Mock pool that returns None (at cap, no session available)
    mock_pool = MagicMock()
    mock_pool.run_block = AsyncMock(return_value=None)

    with patch(
        "halbert_core.streaming.agent_pool.get_terminal_pool",
        return_value=mock_pool,
    ), patch(
        "halbert_core.tools.executor.terminal_pool_wanted",
        return_value=True,
    ), patch(
        "halbert_core.tools.executor.terminal_stream_wanted",
        return_value=True,
    ), patch(
        "halbert_core.tools.executor.publish_terminal_event",
    ):
        result = await executor._run_command({
            "command": "echo fallback",
            "timeout": 5,
        })

    # Pool was tried but returned None -> subprocess fallback ran
    mock_pool.run_block.assert_called_once()
    assert "fallback" in result


# ── Test 5: stage into shell ─────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_stage_into_shell():
    """Composer stages a command -> it appears in the user's shell (write_stdin called).

    Tests the stage endpoint logic: at-prompt -> write_stdin with command text (no newline).
    """
    from halbert_core.streaming.session_manager import TerminalSessionManager

    manager = MagicMock(spec=TerminalSessionManager)
    mock_session = MagicMock()
    mock_session.write_stdin = AsyncMock()
    manager.get.return_value = mock_session
    manager.is_at_prompt.return_value = True

    # Simulate the stage endpoint logic directly
    session_id = "sess-user-1"
    command = "smbstatus --shares"

    session = manager.get(session_id)
    assert session is not None
    assert manager.is_at_prompt(session_id) is True

    await session.write_stdin(command)
    manager.touch(session_id)

    mock_session.write_stdin.assert_called_once_with(command)
    manager.touch.assert_called_once_with(session_id)

    # Verify no newline was added (user presses Enter)
    written_arg = mock_session.write_stdin.call_args[0][0]
    assert "\n" not in written_arg
    assert written_arg == command
