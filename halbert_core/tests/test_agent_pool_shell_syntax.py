# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""A command is arbitrary shell text, and the block line is one line.

``run_block`` splices the command, the closing paren and the D-marker
``printf`` onto a single line written to a PTY. Any command whose text can
swallow the rest of that line swallows the marker with it: ``echo hi # note``
left bash at a continuation prompt, so the block hung for the whole timeout,
returned exit -1 with no output, and destroyed its pool session.

These run REAL bash through a REAL PTY. The substrate that replaced
``create_subprocess_shell`` for every agent command had no test that ran a
command with a comment, a heredoc, a quote or a newline in it -- which is why
this shipped.
"""

import asyncio

import pytest

from halbert_core.streaming.agent_pool import TerminalPool
from halbert_core.streaming.session_manager import TerminalSessionManager


@pytest.fixture
async def pool():
    manager = TerminalSessionManager(max_sessions=4, idle_ttl_seconds=600)
    p = TerminalPool(manager, cap=2)
    try:
        yield p
    finally:
        await p.shutdown()


# Each case: (label, command, expected exit code, a string the output must hold)
SURVIVES = [
    ("a trailing comment", "echo hi  # a note", 0, "hi"),
    ("a comment on its own", "# just a comment", 0, ""),
    ("a heredoc", "cat <<EOF\nhello\nEOF", 0, "hello"),
    ("a quoted hash", "echo 'a # b'", 0, "a # b"),
    ("a multi-line command", "echo one\necho two", 0, "two"),
]

# Unbalanced text is a real syntax error. It must REPORT, not hang.
REPORTS = [
    ("an unterminated quote", 'echo "unterminated'),
    ("an unbalanced paren", "echo )"),
]

# These already worked. They are here so a fix cannot buy the cases above by
# breaking the ordinary ones.
UNCHANGED = [
    ("a pipeline", "echo one | tr a-z A-Z", 0, "ONE"),
    ("exit does not kill the pool shell", "exit 3", 3, ""),
    ("a paren inside a string", "echo 'a ) b'", 0, "a ) b"),
    ("ANSI-C quoting", r"echo $'x\ty'", 0, "x"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,command,code,needle", SURVIVES + UNCHANGED,
                         ids=[c[0] for c in SURVIVES + UNCHANGED])
async def test_the_block_completes(pool, label, command, code, needle):
    """It finishes, with the right exit code, well inside the timeout."""
    result = await asyncio.wait_for(pool.run_block(command, timeout=5.0), timeout=15.0)
    assert result is not None, "no pool session could be acquired"
    assert result["exit_code"] == code, f"{label}: {result}"
    if needle:
        assert needle in result["output_head"] + result["output_tail"], result
    # The timeout is the failure mode: a hang returns after `timeout` with -1.
    assert result["duration"] < 4.0, f"{label} took {result['duration']}s"


@pytest.mark.asyncio
@pytest.mark.parametrize("label,command", REPORTS, ids=[c[0] for c in REPORTS])
async def test_broken_syntax_reports_instead_of_hanging(pool, label, command):
    result = await asyncio.wait_for(pool.run_block(command, timeout=5.0), timeout=15.0)
    assert result is not None
    assert result["exit_code"] not in (0, -1), f"{label}: {result}"
    assert result["duration"] < 4.0, f"{label} took {result['duration']}s"


@pytest.mark.asyncio
async def test_the_session_survives_a_broken_command(pool):
    """A hang used to take the session with it, and the pool with the session.

    ``acquire`` is capped; a session left with an open block is never
    reclaimed. Three of those and a cap-3 pool is dead for the life of the
    process, which is how one bad command became a permanent fallback to
    subprocess.
    """
    first = await asyncio.wait_for(pool.run_block("echo hi  # note", timeout=5.0), timeout=15.0)
    second = await asyncio.wait_for(pool.run_block("echo still here", timeout=5.0), timeout=15.0)
    assert first["exit_code"] == 0
    assert second["exit_code"] == 0
    assert "still here" in second["output_head"] + second["output_tail"]
    assert second["session_id"] == first["session_id"], "the session was not reused"


class TestTheHostSaysWhetherItOnlyLooked:
    """The feed folds runs of inspection into one row, and that decision has
    to be about what a command DID. `rm -rf` returns in milliseconds, so
    duration cannot answer it. The pool asks the same safety classification
    that gates approval and puts the answer on the block, rather than the
    frontend learning to parse shell.
    """

    @pytest.mark.asyncio
    async def test_a_read_is_marked_read_only(self, pool):
        result = await asyncio.wait_for(pool.run_block("echo hi", timeout=5.0), timeout=15.0)
        assert result["read_only"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", [
        "rm -rf /tmp/halbert-test-victim-does-not-exist",
        "echo pwned > /tmp/halbert-test-wiped.txt",
        "true && echo x | tee /tmp/halbert-test-tee.txt",
    ], ids=["delete", "redirect", "piped write"])
    async def test_a_write_is_not(self, pool, command):
        result = await asyncio.wait_for(pool.run_block(command, timeout=5.0), timeout=15.0)
        assert result["read_only"] is False, command

    @pytest.mark.asyncio
    async def test_the_verdict_reaches_the_published_event(self, pool, monkeypatch):
        """The card reads the event, not the return value."""
        seen = []
        import halbert_core.streaming.agent_pool as ap

        monkeypatch.setattr(ap, "publish_terminal_event", lambda p: seen.append(p))
        await asyncio.wait_for(pool.run_block("echo hi", timeout=5.0), timeout=15.0)
        completes = [e for e in seen if e.get("kind") == "complete"]
        assert completes, seen
        assert completes[0]["read_only"] is True
