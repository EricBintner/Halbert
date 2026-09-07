# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Packet 04 B1: turn-scoped mutation digest.

OpenClaw records every voice call with a digest of the tool effects that
happened during it — evidence for "what did you just do to my files?".
Halbert has the ingredients (hash-chained audit log, write-plane tools)
but no per-turn rollup a user can ask about afterwards.

The digest holds (tool, redacted target) pairs ONLY. Raw tool arguments
never enter it: a write_file call's ``contents`` is the loudest payload on
any turn, and the digest is spoken aloud and shown on the ribbon.
"""
from __future__ import annotations

import pytest

from halbert_core.security.turn_digest import (
    TurnDigest,
    current_turn_digest,
    record_effect,
    spoken_tail,
    target_for_tool,
)


class TestTurnDigestUnit:

    def test_empty_digest_reports_nothing(self):
        d = TurnDigest()
        assert d.summary() == "no side effects"
        assert len(d) == 0

    def test_effects_are_counted_and_redacted(self):
        d = TurnDigest()
        d.record(tool="write_file", target="~/notes/plan.md")
        d.record(tool="run_command", target="systemctl status halbert")
        s = d.summary()
        assert "write_file" in s and "run_command" in s and "2 effect" in s
        # per-effect lines name the (redacted) target
        assert "plan.md" in s and "systemctl" in s

    def test_raw_tool_args_never_enter_the_digest(self):
        d = TurnDigest()
        d.record(tool="write_file", target="x", raw_args={"contents": "SECRET"})
        assert "SECRET" not in d.summary()

    def test_targets_are_redacted_and_truncated(self):
        d = TurnDigest()
        d.record(tool="write_file", target="/home/alice/notes/plan.md")
        d.record(tool="run_command", target="curl password=hunter2example " + "x" * 500)
        s = d.summary()
        assert "/home/alice" not in s          # HOME_RE -> /home/<user>
        assert "hunter2example" not in s       # the redaction pass eats credentials
        for line in s.splitlines():
            assert len(line) < 200              # truncated, not a wall

    def test_repeated_tools_are_counted_not_repeated(self):
        d = TurnDigest()
        d.record(tool="run_command", target="ls")
        d.record(tool="run_command", target="df")
        s = d.summary()
        assert "run_command ×2" in s


class TestTargetExtraction:

    def test_run_command_target_is_argv_head_only(self):
        assert target_for_tool(
            "run_command", {"command": "systemctl status halbert"}
        ) == "systemctl"

    def test_file_tools_carry_the_path(self):
        assert target_for_tool("write_file", {"path": "/etc/hosts"}) == "/etc/hosts"
        assert target_for_tool("write_config", {"path": "/etc/samba/smb.conf"}) == "/etc/samba/smb.conf"

    def test_cron_carries_the_entry_name(self):
        assert target_for_tool(
            "schedule_cron", {"name": "nightly backup", "schedule": "@daily"}
        ) == "nightly backup"

    def test_missing_args_are_not_an_error(self):
        assert target_for_tool("write_file", {}) == ""
        assert target_for_tool("run_command", None) == ""


class TestExecutorWiring:

    def test_write_plane_success_records_into_the_current_digest(self):
        from halbert_core.tools.executor import ToolExecutor
        from halbert_core.tools.safety import ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        executor.tools["write_file"] = lambda args: "written"
        d = TurnDigest()
        token = current_turn_digest.set(d)
        try:
            import asyncio
            result = asyncio.run(
                executor.execute(
                    "write_file", {"path": "/tmp/x", "content": "SECRET"},
                    session_id="s", confirmed=True,
                )
            )
        finally:
            current_turn_digest.reset(token)
        assert result.success
        assert len(d) == 1
        assert "write_file" in d.summary()
        assert "SECRET" not in d.summary()

    def test_no_bound_digest_is_a_noop(self):
        from halbert_core.tools.executor import ToolExecutor
        from halbert_core.tools.safety import ToolSafetyFramework

        executor = ToolExecutor(safety=ToolSafetyFramework())
        executor.tools["write_file"] = lambda args: "written"
        import asyncio
        result = asyncio.run(
            executor.execute("write_file", {"path": "/tmp/x"}, confirmed=True)
        )
        assert result.success  # no digest bound: nothing recorded, no error

    def test_failed_tool_records_nothing(self):
        from halbert_core.tools.executor import ToolExecutor
        from halbert_core.tools.safety import ToolSafetyFramework

        def boom(args):
            raise RuntimeError("nope")

        executor = ToolExecutor(safety=ToolSafetyFramework())
        executor.tools["write_file"] = boom
        d = TurnDigest()
        token = current_turn_digest.set(d)
        try:
            import asyncio
            result = asyncio.run(
                executor.execute("write_file", {"path": "/tmp/x"}, confirmed=True)
            )
        finally:
            current_turn_digest.reset(token)
        assert not result.success
        assert len(d) == 0


class TestSpokenTail:

    def test_voice_turn_with_effects_gets_a_tail(self):
        d = TurnDigest()
        d.record(tool="write_file", target="/etc/hosts")
        assert spoken_tail(d, "voice") == d.summary()

    def test_text_turn_gets_no_tail(self):
        d = TurnDigest()
        d.record(tool="write_file", target="/etc/hosts")
        assert spoken_tail(d, "text") is None

    def test_empty_digest_gets_no_tail(self):
        assert spoken_tail(TurnDigest(), "voice") is None
        assert spoken_tail(None, "voice") is None


class TestTurnScope:

    @pytest.mark.asyncio
    async def test_process_creates_and_clears_the_per_turn_digest(self):
        from unittest.mock import AsyncMock, MagicMock
        from halbert_core.agents.state_machine import AgentStateMachine
        from halbert_core.tools.safety import ToolSafetyFramework
        from halbert_core.tools.executor import ToolExecutor

        llm = AsyncMock()
        llm.chat = AsyncMock(return_value=MagicMock(
            content="Test response", tool_calls=None, plan=None,
        ))
        agent = AgentStateMachine(
            llm_client=llm,
            tool_executor=ToolExecutor(safety=ToolSafetyFramework()),
            max_loops=1,
        )
        stream = agent.process(query="hello", session_id="s-digest", modality="voice")
        try:
            async for _event in stream:
                break
        finally:
            await stream.aclose()

        assert agent.ctx.turn_digest is not None
        assert len(agent.ctx.turn_digest) == 0
        # the ContextVar does not outlive the turn
        assert current_turn_digest.get() is None