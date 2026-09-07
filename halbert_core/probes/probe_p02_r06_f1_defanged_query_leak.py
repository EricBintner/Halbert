#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-02 — R06-F1: the defanged query must not survive into the next turn.

The seam (found 2026-08-30, fixed at 0a2c3dfd): the defanged query lived on
the machine and was reset at the *start of RESPONDING* rather than at the
start of the turn, so turn N+1 planned against turn N's question for the
whole stretch between PLANNING and RESPONDING.

Probe (direct, no pytest): run turn 1; plant the stale value the pre-fix
RESPONDING used to leave behind (on ctx AND the pre-fix instance attribute);
spy on ``_build_messages``; run turn 2; assert turn 2's planning prompt
carries turn 2's question and NOT turn 1's, and that the field no longer
lives as machine state that a new turn inherits.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

from halbert_core.agents.state_machine import AgentStateMachine  # noqa: E402

PROBE_ID = "P-02"


def _mk_llm():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=MagicMock(content="ok", tool_calls=None, plan=None))

    async def _stream(messages, **kwargs):
        yield "hello"

    llm.stream = _stream
    return llm


async def _run(agent, query):
    return [e async for e in agent.process(query)]


def main() -> int:
    agent = AgentStateMachine(llm_client=_mk_llm(), max_loops=5)

    turn_one = "Set up a samba share for the media drive"
    turn_two = "What port does it listen on?"

    asyncio.run(_run(agent, turn_one))
    # As the pre-fix RESPONDING left it: the stale value survives the turn
    # boundary, on both the context and (pre-fix) the machine itself.
    agent.ctx.defanged_query = turn_one
    agent._defanged_query = turn_one

    captured = []
    real_build = agent._build_messages

    def _spy(prompt, tail=None, **kwargs):
        msgs = real_build(prompt, tail=tail, **kwargs)
        captured.append(msgs)
        return msgs

    agent._build_messages = _spy
    first_ctx = agent.ctx
    asyncio.run(_run(agent, turn_two))

    if not captured:
        print(f"PROBE {PROBE_ID} r06-f1-defanged-query: OBSERVED -- _build_messages never called")
        return 0

    planning = captured[0]
    last_user = [m for m in planning if m.get("role") == "user"][-1]
    two_ok = turn_two in last_user["content"]
    one_leaked = turn_one in last_user["content"]
    ctx_is_fresh = agent.ctx is not first_ctx

    if not two_ok or one_leaked:
        print(
            f"PROBE {PROBE_ID} r06-f1-defanged-query: RED -- turn 2 planning: "
            f"carries turn-2 query: {two_ok}; turn-1 query leaked: {one_leaked}"
        )
        return 0
    if not ctx_is_fresh:
        print(f"PROBE {PROBE_ID} r06-f1-defanged-query: RED -- turn 2 reused turn 1's context object")
        return 0

    print(
        "PROBE P-02 r06-f1-defanged-query: FIXED -- turn 2 planned against "
        "turn 2's question; turn 1's question did not leak"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        print(f"PROBE {PROBE_ID} r06-f1-defanged-query: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)