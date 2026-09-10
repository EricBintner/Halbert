# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-09 Phase A: the stdio boundary between Halbert and an MCP server.

Three findings, all on the same seam -- what a configured server package
can reach, and what it can do to the transport:

- **A17-G1** (finding #2 of the whole solidity pass) -- the child
  inherited Halbert's entire environment, so any configured stdio server
  (an npx package) could read ``HALBERT_MCP_TOKEN``, ``HALBERT_PEER_TOKEN``,
  every other server's token and API key, and call back into Halbert's own
  authenticated MCP server as Halbert.
- **A17-G2 + bug 1** -- ``create_subprocess_exec`` was called with no
  ``limit=``, so any JSON-RPC line over asyncio's 64 KiB default killed
  the transport and failed every pending request. Reproduced with a
  200,000-character text result.
- **A17-G3 + bug 2** -- ``mcp_config.yml`` lives under
  ``~/Library/Application Support`` on macOS, which was not in
  ``SENSITIVE_PATHS``: the agent's own ``write_file`` to the real config
  path classified MEDIUM, no confirmation, and the health monitor
  relaunches on file-identity change within a tick. That is an
  unconfirmed arbitrary-command path.
"""

import asyncio
import os

import pytest

from halbert_core.mcp.client import MAX_STDIO_FRAME_BYTES, child_env
from halbert_core.tools.safety import RiskLevel, ToolSafetyFramework


# ---------------------------------------------------------------------------
# A17-G1: the child's environment is a whitelist
# ---------------------------------------------------------------------------

def test_halbert_tokens_never_reach_a_child_server(monkeypatch):
    monkeypatch.setenv("HALBERT_MCP_TOKEN", "secret-mcp")
    monkeypatch.setenv("HALBERT_PEER_TOKEN", "secret-peer")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    env = child_env(None)
    assert "HALBERT_MCP_TOKEN" not in env
    assert "HALBERT_PEER_TOKEN" not in env
    assert "OPENAI_API_KEY" not in env


def test_the_child_keeps_what_it_needs_to_run(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/Users/someone")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/Users/someone/.config")
    env = child_env(None)
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/Users/someone"
    assert env["XDG_CONFIG_HOME"] == "/Users/someone/.config"


def test_the_servers_own_config_env_is_passed_through(monkeypatch):
    env = child_env({"MY_SERVER_TOKEN": "abc"})
    assert env["MY_SERVER_TOKEN"] == "abc"


def test_loader_preload_variables_are_dropped(monkeypatch):
    """``DYLD_*``/``LD_*`` turn a launch into arbitrary code in-process."""
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/tmp/evil.dylib")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil.so")
    env = child_env(None)
    assert "DYLD_INSERT_LIBRARIES" not in env
    assert "LD_PRELOAD" not in env


def test_a_server_cannot_smuggle_a_loader_variable_through_its_config():
    """Config env is the server's own -- but not a way past the drop list."""
    env = child_env({"DYLD_INSERT_LIBRARIES": "/tmp/evil.dylib"})
    assert "DYLD_INSERT_LIBRARIES" not in env


# ---------------------------------------------------------------------------
# A17-G2 + bug 1: an oversized frame fails one request, not the transport
# ---------------------------------------------------------------------------

def test_the_frame_limit_is_bounded_and_generous():
    assert MAX_STDIO_FRAME_BYTES >= 1 << 20
    assert MAX_STDIO_FRAME_BYTES <= 64 << 20


@pytest.mark.asyncio
async def test_an_oversized_line_fails_that_request_and_keeps_the_loop():
    """A 200k-character result used to disconnect the whole server."""
    from halbert_core.mcp.client import MCPProtocolError, StdioTransport

    client = StdioTransport(name="big", command="/bin/true")
    huge = '{"jsonrpc":"2.0","id":1,"result":{"x":"' + "a" * 200_000 + '"}}\n'
    follow = '{"jsonrpc":"2.0","id":2,"result":{"ok":true}}\n'

    class _Reader:
        """A stream whose readline() raises on the oversized frame the way
        asyncio's LimitOverrunError-backed reader does."""

        def __init__(self):
            # What the drain reads past, then the next good frame.
            self.buffer = huge.encode()
            self.lines = [follow.encode()]
            self.raised = False

        def __post(self):
            pass

        async def readline(self):
            if not self.raised:
                self.raised = True
                raise ValueError(
                    "Separator is not found, and chunk exceed the limit"
                )
            if self.lines:
                return self.lines.pop(0)
            return b""            # EOF: the server exited

        async def read(self, n):
            chunk, self.buffer = self.buffer[:n], self.buffer[n:]
            return chunk

    class _Proc:
        returncode = None
        stdout = _Reader()
        stdin = None

    client._proc = _Proc()
    first = asyncio.get_event_loop().create_future()
    second = asyncio.get_event_loop().create_future()
    client._pending = {1: first, 2: second}

    reader = asyncio.ensure_future(client._read_loop())
    await asyncio.sleep(0.05)
    reader.cancel()

    assert first.done() and isinstance(first.exception(), MCPProtocolError)
    # The transport survived: the request that followed was still resolved.
    assert second.done() and second.exception() is None


# ---------------------------------------------------------------------------
# A17-G3 + bug 2: the MCP config path is not a MEDIUM write
# ---------------------------------------------------------------------------

def test_the_mcp_config_path_is_a_sensitive_write():
    from halbert_core.mcp.config import config_path

    safety = ToolSafetyFramework()
    result = safety.classify(
        "write_file", {"path": str(config_path()), "content": "x"}
    )
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert result.requires_confirmation or not result.allowed


def test_the_platform_config_dir_is_sensitive_on_this_host():
    from halbert_core.utils.platform import get_config_dir

    safety = ToolSafetyFramework()
    result = safety.classify(
        "write_file", {"path": str(get_config_dir() / "anything.yml"), "content": "x"}
    )
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
