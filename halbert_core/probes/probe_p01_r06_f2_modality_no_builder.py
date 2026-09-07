#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""P-01 — R06-F2: response modality resolved for BOTH prompt arms.

The seam (found 2026-08-30, fixed at 2f595bc0): ``response_modality`` was
resolved only inside the "we have a prompt builder" arm of RESPONDING but
read by both arms, so every turn taken by a machine built without a prompt
builder (Wyoming voice, any non-dashboard embedder) died with an
UnboundLocalError.  The dashboard always wires a builder, which is why the
path shipped dark.

Probe: build a machine with NO prompt builder and NO tooling, drive one
turn, and assert (a) no error event, (b) the turn ends idle, (c) the
simple-response prompt received the resolved modality ("text" is the floor
with no channel capability).
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _env import bootstrap  # noqa: E402

bootstrap()

from halbert_core.agents.state_machine import AgentStateMachine  # noqa: E402

PROBE_ID = "P-01"


def _mk_llm():
    """An LLM that plans nothing and streams one chunk."""
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
    if agent.prompts is not None:
        print(f"PROBE {PROBE_ID} r06-f2-modality: OBSERVED -- prompt builder unexpectedly wired")
        return 0

    events = asyncio.run(_run(agent, "what is sshd_config"))
    errors = [e for e in events if e.type == "error"]
    states = [e.data["state"] for e in events if e.type == "state_change"]
    last_state = states[-1] if states else "<none>"

    if errors or last_state != "idle":
        print(
            f"PROBE {PROBE_ID} r06-f2-modality: RED -- "
            f"no-builder turn errored ({[e.data for e in errors]}) / last state {last_state}"
        )
        return 0

    # Modality must reach the simple-response prompt resolved, not just not crash.
    seen = []
    real = agent._build_simple_response_prompt

    def _spy(response_modality="text"):
        seen.append(response_modality)
        return real(response_modality=response_modality)

    agent._build_simple_response_prompt = _spy
    events2 = asyncio.run(_run(agent, "what is sshd_config"))
    errors2 = [e for e in events2 if e.type == "error"]

    if errors2:
        print(f"PROBE {PROBE_ID} r06-f2-modality: RED -- second turn errored: {errors2}")
        return 0
    if seen != ["text"]:
        print(f"PROBE {PROBE_ID} r06-f2-modality: RED -- modality seen: {seen}")
        return 0

    print(
        "PROBE P-01 r06-f2-modality: FIXED -- no-builder turn ends idle and "
        "the simple prompt received the resolved modality (text)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # probe harness broke
        print(f"PROBE {PROBE_ID} r06-f2-modality: HARNESS-ERROR -- {exc!r}")
        raise SystemExit(3)