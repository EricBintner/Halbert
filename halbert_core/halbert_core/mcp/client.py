# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""Halbert MCP client — connects to external MCP servers.

The mirror image of ``mcp/server.py``: where the server HAND-ROLLS MCP
JSON-RPC 2.0 over stdio with pure stdlib, this client does the same on
the other side of the wire. No ``mcp`` PyPI package (Haloysius
Subtractive Contract — the client is stdlib + ``requests`` only, and it
must stay importable with zero side effects so it can never become a
hard dependency of the agent).

Transports:
  * stdio — ``asyncio.create_subprocess_exec``, line-delimited JSON-RPC
    over stdin/stdout (server logs belong on stderr and are discarded).
  * http  — Streamable HTTP: POST each JSON-RPC message to the server
    URL, accept ``application/json`` or ``text/event-stream`` (SSE)
    responses. ``requests`` is a hard dep of the project but
    synchronous, so calls run in ``asyncio.to_thread``. The legacy
    HTTP+SSE transport (GET a stream, POST to a different endpoint) is
    NOT supported and fails with a clear error naming it.

Protocol: ``initialize`` → ``notifications/initialized`` handshake, then
``tools/list``, ``tools/call``, ``resources/list``, ``resources/read`` —
the same wire shapes ``mcp/server.py`` speaks on the other side. The
initialize result is VALIDATED: a server that omits or misstates its
``protocolVersion`` fails the handshake instead of being silently
accepted, and a version the client does not support is a clear error.
``tools/list`` and ``resources/list`` follow ``nextCursor`` pagination
with a page cap. A Streamable HTTP server's ``Mcp-Session-Id`` response
header is captured and echoed on every request; a 404 while holding a
session id means the session expired and triggers ONE transparent
re-handshake + retry — SERIALIZED, so concurrent expiries recover with a
single handshake and in-flight requests never see a spurious disconnect
(a 404 with no session id held is the legacy-transport error).

Security model:
  * Tokens never logged. Config carries env var NAMES (``token_env``);
    a resolved token is used in the Authorization header and nothing
    else. Every error message that could carry a requests exception (and
    therefore a URL or anything the peer echoes back) is scrubbed of the
    token value and run through ``redact_text``; every message that
    interpolates a configured URL goes through ``redact_url`` — a URL is
    user input and can embed ``?key=`` or ``user:pass@`` credentials.
  * Results from MCP tools flow into the agent's own context — that is
    the agent's trusted internal path, exactly like the server's internal
    reads. The egress boundary lives in server.py's response choke point;
    the client does not duplicate it. A tool result with ``isError``
    raises :class:`MCPToolError` — a failed call never surfaces as a
    normal result (what happens to the content after that is B3).
  * Every operation is timeout-bounded (default 30s, per-server
    ``timeout_seconds``). A hung, crashed, or garbage-spewing server
    produces a clean ``MCPClientError``, never a hang.

Lifecycle: ``MCPClient`` manages connections to multiple servers. The
config is re-read on EVERY call; a live connection whose config
signature changed is disconnected and rebuilt, so config edits (and
deletions) take effect without a restart. A crashed stdio server is
detected on the next call and relaunched — basic reconnection only;
background health monitoring and backoff are B4. Connection setup per
server is serialized by an asyncio lock, so concurrent first calls
launch exactly one subprocess.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from .config import (
    DEFAULT_TIMEOUT_SECONDS,
    MCPServerConfig,
    load_config,
    redact_url,
)

logger = logging.getLogger("halbert.mcp.client")

#: Protocol revisions this client can speak, newest first — the one it
#: SENDS in initialize, and the set it will accept back. The server's
#: answer wins if it is in this set (negotiation); anything else fails
#: the handshake. ``mcp/server.py`` answers ``2024-11-05``.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")

#: The revision this client proposes in ``initialize``.
PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

_CLIENT_INFO = {"name": "halbert-mcp-client", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class MCPClientError(Exception):
    """Base class for every failure in this module. A misbehaving server
    produces one of these, never a hang or an unhandled exception."""


class MCPConnectionError(MCPClientError):
    """Could not establish a connection: launch failure, process death,
    handshake timeout, handshake refusal, unreachable/unusable HTTP
    endpoint."""


class MCPTimeoutError(MCPClientError):
    """A request exceeded its timeout. The server may still be alive;
    the request result (if any ever arrives) is discarded."""


class MCPProtocolError(MCPClientError):
    """The server answered with a JSON-RPC error object."""


class MCPDisconnectedError(MCPClientError):
    """The server connection is gone (process exited / stream closed)."""


class MCPToolError(MCPClientError):
    """The server executed the tool and the tool itself failed — the
    result carried ``isError: true``. Carries ``.result`` (the raw MCP
    result) and ``.text`` (the joined text content), so the caller can
    show what went wrong. A failed call never surfaces as a normal
    result; what happens to the content after this is B3."""

    def __init__(self, message: str, result: Any = None, text: str = "") -> None:
        super().__init__(message)
        self.result = result
        self.text = text


class _SessionExpired(MCPConnectionError):
    """Internal: HTTP 404 while a session id was held — the server
    expired the session. Recovery consumes or re-types it (a double
    expiry becomes a plain MCPConnectionError), so this class never
    reaches the public error surface. Carries the session id that was
    rejected, so concurrent recoveries can tell "another coroutine
    already re-handshook" from "still stale"."""

    def __init__(self, message: str, session_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.session_id = session_id


def _validate_initialize_result(result: Any, server_name: str) -> str:
    """Require a well-formed initialize result and return the negotiated
    protocol version. Silent acceptance of a missing/mismatched version
    is the fail-unsafe path: everything downstream would be speaking
    protocol shapes neither side agreed on."""
    if not isinstance(result, dict):
        raise MCPProtocolError(
            f"MCP server '{server_name}': initialize result is not an object")
    version = result.get("protocolVersion")
    if not isinstance(version, str) or not version:
        raise MCPProtocolError(
            f"MCP server '{server_name}': initialize result has no "
            f"protocolVersion")
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise MCPProtocolError(
            f"MCP server '{server_name}': server speaks protocol version "
            f"'{version}', which this client does not support "
            f"(supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)})")
    return version


def _join_text_content(content: Any) -> str:
    """Join a result's text content items into one string."""
    parts: List[str] = []
    if isinstance(content, list):
        for item in content:
            if (isinstance(item, dict)
                    and item.get("type") == "text"
                    and isinstance(item.get("text"), str)):
                parts.append(item["text"])
    return "\n".join(parts)


def _redact(text: str) -> str:
    """Last-ditch redaction of any message leaving this module (see
    server.py's dispatch catch-all for the same pattern)."""
    try:
        from ..ingestion.redaction import redact_text
        return redact_text(text, prose=True)
    except Exception:
        return text


def _scrub(text: str, secrets: List[str]) -> str:
    """Replace known secret values, then run the house redactor. The
    known values make the test exact; the redactor covers shapes we
    did not anticipate."""
    for s in secrets:
        if s:
            text = text.replace(s, "<redacted>")
    return _redact(text)


def _initialize_params() -> Dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}, "resources": {}},
        "clientInfo": _CLIENT_INFO,
    }


# ---------------------------------------------------------------------------
# stdio transport
# ---------------------------------------------------------------------------

class StdioTransport:
    """JSON-RPC 2.0 over a launched subprocess's stdin/stdout.

    One reader task drains stdout and resolves pending request futures
    by id, so concurrent requests to the same server are safe. Server
    lines that are not valid JSON, not objects, or not answers to a
    pending request are dropped with a debug log — a server that logs to
    stdout (contrary to the MCP convention) does not wedge the client;
    the affected request fails via its timeout instead.
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        # Extra env merged OVER os.environ so config vars can override,
        # with every parent var (PATH above all) still present.
        self.env = {**os.environ, **(env or {})}
        self.timeout = float(timeout)
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.Task] = None
        self._pending: Dict[Any, "asyncio.Future"] = {}
        self._next_id = 0
        #: The protocol version the SERVER answered initialize with (only
        #: set after a validated handshake).
        self.negotiated_protocol_version: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def alive(self) -> bool:
        return (
            self._proc is not None
            and self._proc.returncode is None
            and self._reader is not None
            and not self._reader.done()
        )

    async def connect(self) -> None:
        """Launch the server and run the MCP handshake."""
        if self.alive:
            return
        try:
            self._proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    self.command, *self.args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    # stderr is the server's log channel, not ours to
                    # relay; DEVNULL so a chatty server can't fill a pipe
                    # nobody drains.
                    stderr=asyncio.subprocess.DEVNULL,
                    env=self.env,
                ),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            raise MCPConnectionError(
                f"MCP server '{self.name}': launch timed out") from None
        except (OSError, ValueError) as e:
            raise MCPConnectionError(
                f"MCP server '{self.name}': failed to launch "
                f"'{self.command}': {e}") from None

        self._pending = {}
        self._reader = asyncio.get_running_loop().create_task(self._read_loop())
        try:
            result = await self.request("initialize", _initialize_params())
            self.negotiated_protocol_version = _validate_initialize_result(
                result, self.name)
        except asyncio.CancelledError:
            # Cancellation is not an MCPClientError — without this branch
            # the cleanup below never ran and the transport was left
            # half-alive (reader running, process up, no negotiated
            # version) with no reference anywhere: _ensure stores the
            # connection only after connect() returns, so the subprocess
            # was orphaned, and a later connect() believed itself already
            # connected. Reap, then re-raise.
            await self.close()
            raise
        except MCPClientError as e:
            await self.close()
            raise MCPConnectionError(
                f"MCP server '{self.name}': handshake failed: {e}") from None
        await self.notify("notifications/initialized")
        logger.info("MCP server '%s' connected (stdio)", self.name)

    async def close(self) -> None:
        """Terminate the subprocess. Idempotent; never raises."""
        reader, self._reader = self._reader, None
        if reader is not None:
            reader.cancel()
            try:
                await asyncio.wait_for(reader, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                if proc.returncode is None:
                    # Close stdin first: a well-behaved server sees EOF
                    # and exits on its own, no SIGTERM needed.
                    if proc.stdin is not None:
                        proc.stdin.close()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
            except Exception:
                logger.debug("MCP server '%s': error during close", self.name,
                             exc_info=True)
        self._fail_pending(MCPDisconnectedError(
            f"MCP server '{self.name}': connection closed"))

    # -- protocol ----------------------------------------------------------

    async def _read_loop(self) -> None:
        """Drain stdout, resolving pending futures by response id.

        Only a RESPONSE — no ``method``, and a ``result`` or ``error``
        member — may resolve a pending future. A server-initiated message
        carrying a ``method`` is never the answer to our request, even
        when its id collides with one of ours: resolving on id alone let
        a colliding server request steal a pending future and silently
        misattribute it (the true response was then dropped as an
        unknown id). Server requests get a JSON-RPC error back (this
        client implements no server-facing handlers, and a server left
        waiting on a reply would hang); server notifications are dropped.
        """
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break  # EOF: the server exited
                try:
                    message = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    logger.debug(
                        "MCP server '%s': dropping unparseable stdout line",
                        self.name)
                    continue
                if not isinstance(message, dict):
                    continue
                if message.get("method") is not None:
                    # Server-initiated request (method + id) or
                    # notification (method, no id). NEVER a response.
                    if "id" in message:
                        await self._reject_server_request(message["id"])
                    continue
                if "result" not in message and "error" not in message:
                    continue  # neither request nor response: drop
                future = self._pending.pop(message.get("id"), None)
                if future is not None and not future.done():
                    future.set_result(message)
                # else: notification, server log, or unsolicited message
        finally:
            self._fail_pending(MCPDisconnectedError(
                f"MCP server '{self.name}': stream closed"))

    async def _reject_server_request(self, req_id: Any) -> None:
        """Answer a server-initiated request with method-not-found, so
        the server is not left hanging on a reply we will never send."""
        try:
            await self._write({
                "jsonrpc": "2.0", "id": req_id,
                "error": {
                    "code": -32601,
                    "message": (
                        "Halbert MCP client does not accept "
                        "server-initiated requests"),
                },
            })
        except MCPClientError as e:
            logger.debug(
                "MCP server '%s': could not reject server request: %s",
                self.name, e)

    def _fail_pending(self, exc: MCPClientError) -> None:
        pending = list(self._pending.values())
        self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(exc)

    async def _write(self, message: Dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None or not self.alive:
            raise MCPDisconnectedError(
                f"MCP server '{self.name}': not connected")
        try:
            self._proc.stdin.write(
                (json.dumps(message) + "\n").encode("utf-8"))
            await asyncio.wait_for(self._proc.stdin.drain(), timeout=self.timeout)
        except (BrokenPipeError, ConnectionResetError) as e:
            raise MCPDisconnectedError(
                f"MCP server '{self.name}': pipe closed: {e}") from None
        except asyncio.TimeoutError:
            raise MCPTimeoutError(
                f"MCP server '{self.name}': stdin write timed out") from None

    async def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Send a request and return its ``result``. Raises:
        MCPTimeoutError (no answer in time), MCPDisconnectedError (stream
        gone), MCPProtocolError (JSON-RPC error object)."""
        self._next_id += 1
        req_id = self._next_id
        message: Dict[str, Any] = {
            "jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            message["params"] = params
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        try:
            await self._write(message)
        except MCPClientError:
            self._pending.pop(req_id, None)
            raise
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise MCPTimeoutError(
                f"MCP server '{self.name}': no response to '{method}' "
                f"within {self.timeout}s") from None
        if "error" in response:
            err = response["error"] or {}
            raise MCPProtocolError(
                f"MCP server '{self.name}' rejected '{method}': "
                f"[{err.get('code', '?')}] {err.get('message', '')}")
        return response.get("result")

    async def notify(self, method: str) -> None:
        """Send a notification (no id, no response expected)."""
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        try:
            await self._write(message)
        except MCPClientError as e:
            # A lost notification after a successful initialize means the
            # server died mid-handshake; the next request will surface it.
            logger.debug("MCP server '%s': %s notification failed: %s",
                         self.name, method, e)


# ---------------------------------------------------------------------------
# HTTP transport (Streamable HTTP)
# ---------------------------------------------------------------------------

def _parse_sse(body: str, req_id: Any) -> Optional[Dict[str, Any]]:
    """Extract the JSON-RPC response for *req_id* from an SSE body.

    Events are separated by blank lines; a single event may carry its
    data across multiple ``data:`` lines (joined with ``\\n``, per the SSE
    spec). The first event whose parsed message answers *req_id* wins.
    """
    data_lines: List[str] = []
    for line in body.splitlines():
        if line == "":
            candidate = "\n".join(data_lines)
            data_lines = []
            if not candidate:
                continue
            try:
                message = json.loads(candidate)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if (isinstance(message, dict)
                    and message.get("id") == req_id
                    and ("result" in message or "error" in message)):
                return message
        elif line.startswith("data:"):
            # Per the SSE spec, strip exactly ONE leading space after
            # the colon — ``data:  x`` (two spaces) keeps one space of
            # payload. lstrip() would eat significant whitespace.
            data = line[len("data:"):]
            if data.startswith(" "):
                data = data[1:]
            data_lines.append(data)
    # A body without a trailing blank line still deserves a look.
    candidate = "\n".join(data_lines)
    if candidate:
        try:
            message = json.loads(candidate)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if (isinstance(message, dict)
                and message.get("id") == req_id
                and ("result" in message or "error" in message)):
            return message
    return None


class HTTPTransport:
    """Streamable HTTP transport: one POST per JSON-RPC message.

    Stateless after the handshake — ``requests`` calls run in
    ``asyncio.to_thread`` so the event loop is never blocked. ``close()``
    only marks the transport closed; there is no socket to hold.
    """

    def __init__(
        self,
        name: str,
        url: str,
        token_provider=None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.name = name
        self.url = url
        self.token_provider = token_provider  # () -> Optional[str]
        self.timeout = float(timeout)
        self._connected = False
        self._next_id = 0
        #: The Mcp-Session-Id the server assigned at initialize (if any),
        #: echoed on every subsequent request. Without it, a spec-
        #: compliant Streamable HTTP server that assigns session ids 404s
        #: every request after the first.
        self._session_id: Optional[str] = None
        #: The protocol version the SERVER answered initialize with (only
        #: set after a validated handshake).
        self.negotiated_protocol_version: Optional[str] = None
        #: Serializes session-expiry recovery: concurrent 404s must
        #: produce exactly one re-handshake, not interleaved ones.
        self._handshake_lock = asyncio.Lock()

    @property
    def alive(self) -> bool:
        return self._connected

    def _headers(self, token: Optional[str]) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post_sync(self, message: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        """The synchronous core, run in a worker thread."""
        token = self.token_provider() if self.token_provider else None
        headers = self._headers(token)
        if message.get("method") == "initialize":
            # initialize STARTS a session: never echo a stale session id
            # on it. This also means an initialize POST can never be
            # misread as session expiry (it carries no session id), so
            # recovery's internal handshake cannot recurse into recovery.
            headers.pop("Mcp-Session-Id", None)
        session_sent = "Mcp-Session-Id" in headers
        try:
            response = requests.post(
                self.url, json=message,
                headers=headers, timeout=timeout)
        except requests.RequestException as e:
            # The exception (and the URL inside it) can carry credentials
            # — a user:pass@ URL, or anything a proxy echoes back. Scrub
            # the token value, then run the house redactor.
            raise MCPConnectionError(
                f"MCP server '{self.name}': request failed: "
                f"{_scrub(str(e), [token or ''])}") from None

        # Capture (or update) the session id whenever the server sends
        # one — assigning it at initialize and rotating it later are both
        # legal.
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id

        # A notification (no id) is ACKed by 200/202 with no body — that
        # is the Streamable HTTP spec's success path for notifications,
        # not an error.
        if "id" not in message and response.status_code in (200, 202):
            return {}

        if response.status_code == 404 and session_sent:
            # The endpoint exists (initialize worked) and we sent a
            # session id — the server expired the session. Recovery
            # consumes this before it can escape.
            raise _SessionExpired(
                f"MCP server '{self.name}': HTTP 404 with a session id "
                f"held — session expired",
                session_id=self._session_id)
        if response.status_code in (404, 405):
            # Streamable HTTP POSTs to the message endpoint; a server
            # answering 404/405 to the POST is either the wrong URL or a
            # server speaking only the LEGACY HTTP+SSE transport (GET a
            # stream, POST elsewhere). We do not support the legacy
            # transport — say so, clearly, once. The URL is redacted: it
            # is user input and can embed ?key= or user:pass@ secrets.
            raise MCPConnectionError(
                f"MCP server '{self.name}': HTTP {response.status_code} at "
                f"{redact_url(self.url)} — the endpoint does not accept "
                f"Streamable HTTP POSTs. If this server speaks only the "
                f"legacy HTTP+SSE transport, it is not supported.")
        if response.status_code in (401, 403):
            raise MCPConnectionError(
                f"MCP server '{self.name}': HTTP {response.status_code} "
                f"(unauthorized — check the auth token)")
        if response.status_code == 202 and "id" in message:
            # 202 Accepted for a REQUEST (not a notification) means the
            # server answers requests on a long-lived GET stream —
            # spec-legal server-initiated streaming, but this client
            # expects each POST to return its own response. Name the
            # mode instead of a generic status complaint.
            raise MCPConnectionError(
                f"MCP server '{self.name}': HTTP 202 for a request — the "
                f"server appears to answer requests via a long-lived GET "
                f"stream (server-initiated streaming), which this client "
                f"does not support")
        if response.status_code != 200:
            raise MCPConnectionError(
                f"MCP server '{self.name}': unexpected HTTP status "
                f"{response.status_code}")

        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in content_type:
            parsed = _parse_sse(response.text, message.get("id"))
            if parsed is None:
                raise MCPProtocolError(
                    f"MCP server '{self.name}': event-stream response "
                    f"contained no JSON-RPC answer for this request")
            return parsed
        try:
            parsed = response.json()
        except ValueError:
            raise MCPProtocolError(
                f"MCP server '{self.name}': response is not JSON "
                f"(Content-Type: {content_type or 'none'})") from None
        if not isinstance(parsed, dict):
            raise MCPProtocolError(
                f"MCP server '{self.name}': response is not a JSON-RPC object")
        if (parsed.get("id") != message.get("id")
                or ("result" not in parsed and "error" not in parsed)):
            # Same guard the SSE path has always had: a JSON body that is
            # not the ANSWER to this request (wrong id, or neither result
            # nor error) must not be mistaken for one.
            raise MCPProtocolError(
                f"MCP server '{self.name}': response does not answer this "
                f"request (id {message.get('id')!r} expected, got "
                f"{parsed.get('id')!r})")
        return parsed

    async def _exchange(
        self,
        message: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        effective = float(timeout if timeout is not None else self.timeout)
        if not self._connected and message.get("method") != "initialize":
            raise MCPDisconnectedError(
                f"MCP server '{self.name}': not connected")
        return await asyncio.wait_for(
            asyncio.to_thread(self._post_sync, message, effective),
            timeout=effective + 5.0,  # wall-clock margin over the requests timeout
        )

    async def connect(self) -> None:
        if self._connected:
            return
        await self._handshake()

    async def _handshake(self) -> None:
        """initialize + initialized notification. Also the re-entry point
        after a session expiry.

        The STALE session id is deliberately kept until the initialize
        response replaces it: requests in flight during a recovery keep
        sending it, so their 404s read as session expiry (they queue on
        the recovery lock) instead of the legacy-transport error they
        would get with no session id at all.
        """
        result = await self.request("initialize", _initialize_params())
        self.negotiated_protocol_version = _validate_initialize_result(
            result, self.name)
        # The initialized notification: a Streamable HTTP server answers a
        # notification with 202/200 and no body. Fire it (timeout-bounded
        # like every other POST), ignore failures — a server that rejects
        # notifications but serves requests is still usable (and the next
        # request will surface real problems).
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self._post_sync,
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    self.timeout),
                timeout=self.timeout + 5.0)
        except asyncio.TimeoutError:
            logger.debug(
                "MCP server '%s': initialized notification timed out",
                self.name)
        except MCPClientError as e:
            logger.debug(
                "MCP server '%s': initialized notification rejected: %s",
                self.name, e)
        self._connected = True
        logger.info("MCP server '%s' connected (http)", self.name)

    async def close(self) -> None:
        self._connected = False

    async def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        self._next_id += 1
        message: Dict[str, Any] = {
            "jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        try:
            response = await self._exchange(message)
        except _SessionExpired as expiry:
            # 404 with a session id held: the server expired the
            # session. Recover transparently — serialized.
            response = await self._recover_session(message, expiry.session_id)
        except asyncio.TimeoutError:
            raise MCPTimeoutError(
                f"MCP server '{self.name}': no response to '{method}' "
                f"within {self.timeout}s") from None
        if "error" in response:
            err = response["error"] or {}
            raise MCPProtocolError(
                f"MCP server '{self.name}' rejected '{method}': "
                f"[{err.get('code', '?')}] {err.get('message', '')}")
        return response.get("result")

    async def _recover_session(
        self,
        message: Dict[str, Any],
        expired_session_id: Optional[str],
    ) -> Dict[str, Any]:
        """Recover from an expired session: one re-handshake, then retry
        the original request — and return its response.

        Serialized by ``_handshake_lock`` so concurrent 404s produce
        exactly ONE re-handshake: waiters re-check the session id after
        acquiring the lock and, if another coroutine already rotated it,
        just retry on the new session. ``_connected`` is never flipped
        here — in-flight requests must not trip the not-connected guard
        and fail with a spurious MCPDisconnectedError. A second expiry
        (immediately after a successful re-handshake) is re-typed to a
        plain MCPConnectionError, keeping _SessionExpired off the
        public surface.
        """
        async with self._handshake_lock:
            if self._session_id != expired_session_id:
                # Another coroutine re-handshook while we queued: the
                # session was already rotated — just retry. That retry
                # can 404 too (a server expiring sessions faster than we
                # can rotate them); re-type it here so _SessionExpired
                # never escapes to a caller on the waiter branch (B1
                # residual, folded into B2).
                try:
                    return await self._exchange(message)
                except _SessionExpired as e:
                    raise MCPConnectionError(
                        f"MCP server '{self.name}': session expired again "
                        f"after another recovery ({e})") from None
            logger.info(
                "MCP server '%s': session expired, re-handshaking", self.name)
            try:
                await self._handshake()
            except _SessionExpired as e:
                raise MCPConnectionError(
                    f"MCP server '{self.name}': session expired again "
                    f"during re-handshake ({e})") from None
            try:
                return await self._exchange(message)
            except _SessionExpired as e:
                raise MCPConnectionError(
                    f"MCP server '{self.name}': session expired again "
                    f"immediately after re-handshake ({e})") from None

    async def notify(self, method: str) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    self._post_sync,
                    {"jsonrpc": "2.0", "method": method},
                    self.timeout),
                timeout=self.timeout + 5.0)
        except asyncio.TimeoutError:
            logger.debug("MCP server '%s': %s notification timed out",
                         self.name, method)
        except MCPClientError as e:
            logger.debug("MCP server '%s': %s notification failed: %s",
                         self.name, method, e)


# ---------------------------------------------------------------------------
# Transport factory
# ---------------------------------------------------------------------------

def build_transport(config: MCPServerConfig):
    """Build the transport for one configured server. Pure — no I/O."""
    if config.transport == "stdio":
        return StdioTransport(
            name=config.name,
            command=config.command,
            args=config.args,
            env=config.env,
            timeout=config.timeout_seconds,
        )
    if config.transport == "http":
        return HTTPTransport(
            name=config.name,
            url=config.url,
            token_provider=(config.auth.resolve_token
                            if config.auth is not None else None),
            timeout=config.timeout_seconds,
        )
    raise MCPClientError(
        f"MCP server '{config.name}': unsupported transport "
        f"'{config.transport}'")


# ---------------------------------------------------------------------------
# The client facade
# ---------------------------------------------------------------------------

class _Connection:
    """A live transport plus the config signature that produced it."""

    def __init__(self, signature: Tuple, transport) -> None:
        self.signature = signature
        self.transport = transport

    @property
    def alive(self) -> bool:
        return self.transport.alive

    async def close(self) -> None:
        try:
            await self.transport.close()
        except Exception:
            logger.debug("MCP connection close failed", exc_info=True)


class MCPClient:
    """Manages connections to multiple MCP servers.

    Config is re-read on EVERY operation (``load_config`` — the
    applescript_config pattern), and each live connection is compared
    against its server's current config signature:

      * no connection  → connect on demand
      * signature same → reuse the live connection
      * signature changed → disconnect, rebuild (config edits apply
        without a restart)
      * connection dead (crashed subprocess) → disconnect, relaunch
        (basic reconnection; monitoring/backoff is B4)

    Connection setup is serialized PER SERVER by an asyncio lock: two
    concurrent first calls launch exactly one subprocess, not one each
    with the loser's transport orphaned.
    """

    #: Safety cap on tools/list and resources/list pagination. A hostile
    #: server that echoes a cursor forever must produce a clear error,
    #: not an infinite loop.
    MAX_LIST_PAGES = 100

    def __init__(self, config_loader=load_config) -> None:
        self._load = config_loader
        self._connections: Dict[str, _Connection] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    # -- lifecycle ---------------------------------------------------------

    async def _ensure(self, server_name: str) -> _Connection:
        lock = self._locks.setdefault(server_name, asyncio.Lock())
        async with lock:
            # Config is re-read INSIDE the lock too: a coroutine that
            # waited may find the config changed while it queued.
            config = self._load()
            server_config = config.server(server_name)
            if server_config is None:
                # Removing a server from the config tears down its live
                # connection, not just future calls — otherwise a stdio
                # subprocess outlives its own configuration forever.
                connection = self._connections.pop(server_name, None)
                if connection is not None:
                    logger.info(
                        "MCP server '%s' removed from config, disconnecting",
                        server_name)
                    await connection.close()
                raise MCPClientError(
                    f"MCP server '{server_name}' is not configured "
                    f"(see {__name__}.config.config_path())")
            signature = server_config.signature()
            connection = self._connections.get(server_name)
            if connection is not None:
                if connection.signature == signature and connection.alive:
                    return connection
                reason = ("configuration changed"
                          if connection.signature != signature
                          else "connection lost")
                logger.info(
                    "MCP server '%s': %s, reconnecting",
                    server_name, reason)
                await connection.close()
                del self._connections[server_name]
            transport = build_transport(server_config)
            await transport.connect()
            connection = _Connection(signature, transport)
            self._connections[server_name] = connection
            return connection

    async def connect(self, server_name: Optional[str] = None) -> None:
        """Connect one server by name, or every configured server
        (name=None). Failures are logged and collected — one dead server
        never prevents the others from connecting, and never raises."""
        config = self._load()
        names = ([server_name] if server_name is not None
                 else [s.name for s in config.servers])
        failures: List[str] = []
        for name in names:
            try:
                await self._ensure(name)
            except MCPClientError as e:
                failures.append(f"{name}: {e}")
                self._connections.pop(name, None)
        for failure in failures:
            logger.warning("MCP server failed to connect: %s", failure)

    async def disconnect(self, server_name: Optional[str] = None) -> None:
        """Disconnect one server by name, or everything (name=None).
        Never raises. Takes the same per-server lock as _ensure, so a
        connect that is in flight cannot land after this call and
        resurrect the connection it just killed.

        With no name, EVERY server ever touched is torn down — iterating
        the locks (not just live connections), because a server whose
        connect is mid-flight is not in ``_connections`` yet but its
        landing must still be beaten.
        """
        names = ([server_name] if server_name is not None
                 else list(self._locks))
        for name in names:
            lock = self._locks.setdefault(name, asyncio.Lock())
            async with lock:
                connection = self._connections.pop(name, None)
                if connection is not None:
                    await connection.close()

    async def reconnect(self, server_name: str) -> None:
        """Force-close and re-establish a connection (with the CURRENT
        config — this is also how a hung/crashed server is recovered)."""
        await self.disconnect(server_name)
        try:
            await self._ensure(server_name)
        except MCPClientError:
            self._connections.pop(server_name, None)
            raise

    def connected_servers(self) -> List[str]:
        return sorted(
            name for name, conn in self._connections.items() if conn.alive)

    # -- protocol surface ----------------------------------------------------

    async def _list_paginated(
        self,
        server_name: str,
        method: str,
        key: str,
    ) -> List[Dict[str, Any]]:
        """``tools/list`` / ``resources/list`` with cursor pagination.

        A server may split its answer into pages (``nextCursor``);
        stopping after the first page silently drops every later page.
        Follow the cursor until the server stops sending one, with a
        page cap so a hostile cursor echo fails with a clear error
        instead of looping forever.
        """
        connection = await self._ensure(server_name)
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        for _page in range(self.MAX_LIST_PAGES):
            params = {"cursor": cursor} if cursor else None
            result = await connection.transport.request(method, params)
            result = result if isinstance(result, dict) else {}
            batch = result.get(key)
            if isinstance(batch, list):
                items.extend(batch)
            cursor = result.get("nextCursor")
            if not cursor:
                return items
        raise MCPProtocolError(
            f"MCP server '{server_name}': {method} pagination exceeded "
            f"{self.MAX_LIST_PAGES} pages — the server keeps returning a "
            f"nextCursor (hostile or broken cursor echo)")

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """``tools/list`` → the server's tool schemas, all pages."""
        return await self._list_paginated(server_name, "tools/list", "tools")

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """``tools/call`` → the raw MCP result.

        The result is the agent's trusted internal input (server-side
        redaction does not apply here — that boundary is ours to enforce
        when WE serve, not when we call out); B3 owns what happens to it
        next. A result carrying ``isError: true`` is the tool FAILING —
        it raises :class:`MCPToolError` (carrying the content and the
        raw result) instead of surfacing as a normal result. Like every
        other operation, call_tool may raise ANY MCPClientError subclass
        (connection/timeout/protocol/disconnected for transport
        failures, MCPToolError for a failed tool) — B2's UX maps the
        error type to the user-facing message.
        """
        connection = await self._ensure(server_name)
        result = await connection.transport.request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })
        if isinstance(result, dict) and result.get("isError"):
            text = _join_text_content(result.get("content"))
            raise MCPToolError(
                f"MCP server '{server_name}' tool '{tool_name}' reported "
                f"an error: {text or '(no detail)'}",
                result=result, text=text)
        return result

    async def list_resources(self, server_name: str) -> List[Dict[str, Any]]:
        """``resources/list`` → the server's resources, all pages."""
        return await self._list_paginated(
            server_name, "resources/list", "resources")

    async def read_resource(
        self, server_name: str, uri: str
    ) -> Any:
        """``resources/read`` → the raw MCP result for *uri*."""
        connection = await self._ensure(server_name)
        return await connection.transport.request("resources/read", {
            "uri": uri,
        })


# A convenience module-level single connection isn't provided on purpose:
# B2 owns when (and whether) a client instance is created and wired into
# the tool registry.