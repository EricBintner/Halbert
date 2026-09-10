# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""R-09 Phase D: HTTP hygiene, bounded pagination, and an operator filter.

- **A17-G15** -- the HTTP transport never sent ``DELETE`` when it closed
  (so a server's session outlived Halbert's use of it), did not validate
  the URL's scheme (an ``mcp_config.yml`` ``url: file:///...`` or
  ``http://`` to a remote host was accepted), and followed redirects with
  the session id and bearer token still attached, so a redirect to
  another origin handed both away.
- **A17-G16** -- pagination was bounded by a page COUNT only: a hundred
  pages of a megabyte each is a hundred megabytes, and a server that
  answers slowly could hold the loop for a hundred timeouts. It is
  bounded by cursor set, bytes and a deadline too.
- **A17-G18** -- there was no way to say which of a server's tools to
  register: the first 64 in whatever order the server returned them, and
  the 65th dropped with a log line.
- **bug 3** -- the client never answered ``ping``, so a spec-compliant
  server's keepalive got method-not-found.
- **bug 4** -- ``initialize`` advertised capabilities the client does not
  implement.
"""

import asyncio

import pytest

from halbert_core.mcp.client import (
    MCPConnectionError,
    MAX_LIST_BYTES,
    HTTPTransport,
    validate_http_url,
)


# ---------------------------------------------------------------------------
# A17-G15: scheme, redirects, DELETE
# ---------------------------------------------------------------------------

def test_only_http_schemes_are_accepted():
    validate_http_url("srv", "https://example.test/mcp")
    validate_http_url("srv", "http://localhost:8080/mcp")
    for bad in ("file:///etc/passwd", "ftp://x.test/", "gopher://x", "/tmp/x"):
        with pytest.raises(MCPConnectionError):
            validate_http_url("srv", bad)


def test_the_post_does_not_follow_redirects(monkeypatch):
    import halbert_core.mcp.client as client_mod

    seen = {}

    class _Response:
        status_code = 200
        headers = {}
        text = '{"jsonrpc":"2.0","id":1,"result":{}}'

        def json(self):
            return {"jsonrpc": "2.0", "id": 1, "result": {}}

    def _post(url, **kwargs):
        seen.update(kwargs)
        return _Response()

    monkeypatch.setattr(client_mod.requests, "post", _post)
    transport = HTTPTransport(name="srv", url="https://example.test/mcp")
    transport._post_sync({"jsonrpc": "2.0", "id": 1, "method": "ping"}, 5.0)
    assert seen.get("allow_redirects") is False


@pytest.mark.asyncio
async def test_close_deletes_the_session(monkeypatch):
    import halbert_core.mcp.client as client_mod

    deleted = []

    def _delete(url, **kwargs):
        deleted.append((url, kwargs.get("headers", {})))

        class _R:
            status_code = 204
            headers = {}
        return _R()

    monkeypatch.setattr(client_mod.requests, "delete", _delete)
    transport = HTTPTransport(name="srv", url="https://example.test/mcp")
    transport._connected = True
    transport._session_id = "sess-1"
    await transport.close()
    assert deleted, "close() must release the server's session"
    assert deleted[0][1].get("Mcp-Session-Id") == "sess-1"


@pytest.mark.asyncio
async def test_close_without_a_session_sends_nothing(monkeypatch):
    import halbert_core.mcp.client as client_mod

    called = []
    monkeypatch.setattr(
        client_mod.requests, "delete",
        lambda *a, **k: called.append(1))
    transport = HTTPTransport(name="srv", url="https://example.test/mcp")
    transport._connected = True
    await transport.close()
    assert called == []


# ---------------------------------------------------------------------------
# A17-G16: pagination is bounded three ways
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_repeated_cursor_stops_the_walk():
    """A server echoing one cursor forever is a loop, not a long list."""
    from halbert_core.mcp.client import MCPClient, MCPProtocolError

    client = MCPClient(config_loader=lambda: None)

    class _Transport:
        async def request(self, method, params=None):
            return {"tools": [{"name": "x"}], "nextCursor": "same"}

    async def _ensure(name):
        class _C:
            transport = _Transport()
        return _C()

    client._ensure = _ensure
    with pytest.raises(MCPProtocolError) as excinfo:
        await client.list_tools("srv")
    assert "cursor" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_pagination_stops_at_the_byte_bound():
    from halbert_core.mcp.client import MCPClient, MCPProtocolError

    client = MCPClient(config_loader=lambda: None)
    pages = {"n": 0}

    class _Transport:
        async def request(self, method, params=None):
            pages["n"] += 1
            return {
                "tools": [{"name": "x", "description": "y" * 100_000}],
                "nextCursor": f"c{pages['n']}",
            }

    async def _ensure(name):
        class _C:
            transport = _Transport()
        return _C()

    client._ensure = _ensure
    with pytest.raises(MCPProtocolError) as excinfo:
        await client.list_tools("srv")
    assert "byte" in str(excinfo.value).lower() or "size" in str(excinfo.value).lower()
    assert pages["n"] * 100_000 < MAX_LIST_BYTES * 3


# ---------------------------------------------------------------------------
# A17-G18: the operator says which tools to register
# ---------------------------------------------------------------------------

def test_include_is_a_whitelist_and_empty_means_nothing():
    from halbert_core.mcp.config import make_tool_filter

    keep = make_tool_filter({"include": ["read_*"]})
    assert keep("read_file") is True
    assert keep("delete_file") is False
    assert make_tool_filter({"include": []})("read_file") is False


def test_exclude_is_a_blacklist():
    from halbert_core.mcp.config import make_tool_filter

    keep = make_tool_filter({"exclude": ["delete_*"]})
    assert keep("read_file") is True
    assert keep("delete_file") is False


def test_include_wins_over_exclude():
    from halbert_core.mcp.config import make_tool_filter

    keep = make_tool_filter({"include": ["read_file"], "exclude": ["read_*"]})
    assert keep("read_file") is True


def test_no_filter_keeps_everything():
    from halbert_core.mcp.config import make_tool_filter

    keep = make_tool_filter(None)
    assert keep("anything") is True


def test_the_filter_is_parsed_off_the_config_entry(tmp_path, monkeypatch):
    import halbert_core.mcp.config as config_mod

    cfg = tmp_path / "mcp_config.yml"
    cfg.write_text(
        "servers:\n"
        "  - name: fs\n"
        "    transport: stdio\n"
        "    command: npx\n"
        '    args: ["-y", "s"]\n'
        "    tools:\n"
        "      exclude: [\"delete_*\"]\n"
    )
    monkeypatch.setattr(config_mod, "config_path", lambda: cfg)
    server = config_mod.load_config().servers[0]
    assert server.tool_exclude == ("delete_*",)


# ---------------------------------------------------------------------------
# bugs 3 and 4: ping, and honest capabilities
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_server_ping_is_answered_not_refused():
    from halbert_core.mcp.client import StdioTransport

    written = []

    transport = StdioTransport(name="srv", command="/bin/true")

    async def _write(message):
        written.append(message)

    transport._write = _write

    class _Reader:
        def __init__(self):
            self.lines = [b'{"jsonrpc":"2.0","id":7,"method":"ping"}\n']

        async def readline(self):
            return self.lines.pop(0) if self.lines else b""

    class _Proc:
        returncode = None
        stdout = _Reader()
        stdin = None

    transport._proc = _Proc()
    await transport._read_loop()
    assert written, "a ping must be answered"
    assert written[0]["id"] == 7
    assert "result" in written[0], written[0]
    assert "error" not in written[0]


def test_initialize_advertises_only_what_this_client_implements():
    from halbert_core.mcp.client import _initialize_params

    capabilities = _initialize_params()["capabilities"]
    # The client implements no roots, no sampling and no elicitation --
    # advertising them invites a server to ask for something that will
    # come back method-not-found.
    assert "sampling" not in capabilities
    assert "elicitation" not in capabilities
    assert capabilities.get("roots", {}).get("listChanged") is not True


# ---------------------------------------------------------------------------
# bug 5: the server-side HA handlers are loop-safe
# ---------------------------------------------------------------------------

def test_a_sync_handler_can_await_from_inside_a_running_loop():
    """MCP-04's topology is open: the server may be hosted inside the
    dashboard's loop or run standalone. ``asyncio.run`` raises
    RuntimeError in the first case, so every HA handler failed there."""
    import asyncio as _asyncio

    from halbert_core.mcp.server import run_coroutine_blocking

    async def _work():
        await _asyncio.sleep(0)
        return "done"

    # Standalone: no loop running.
    assert run_coroutine_blocking(_work()) == "done"

    # Hosted: a loop IS running on this thread.
    async def _hosted():
        return run_coroutine_blocking(_work())

    assert _asyncio.run(_hosted()) == "done"
